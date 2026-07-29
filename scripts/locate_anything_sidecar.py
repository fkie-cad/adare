#!/usr/bin/env python3
"""Standalone LocateAnything grounding sidecar (stdlib only).

Wraps the ``locate-anything-cli`` binary (ggml/Metal port of NVIDIA
LocateAnything-3B) behind a tiny HTTP endpoint so the ADARE package can request
open-vocabulary GUI-element bounding boxes *without* taking on any heavy VLM
dependency (no torch / ggml / llama-cpp in the Python 3.13-pinned ``adare``
package). This script shells out to the binary per request; the model weights
are mmap'd, so warm calls are ~2.5 s on Apple-Silicon Metal.

Run it next to the built binary + GGUF weights, e.g.::

    LA_CLI_BIN=/path/to/locate-anything-cli \\
    LA_MODEL=/path/to/locate-anything-q8_0.gguf \\
    python3 scripts/locate_anything_sidecar.py --host 127.0.0.1 --port 13111

Then point ADARE at it: ``export ADARE_LOCATE_URL=http://127.0.0.1:13111``.

Endpoints:
  GET  /health  -> {"status": "ok", "model": "...", "bin": "..."}
  POST /locate  -> body {"prompt": "<text>", "screenshot_base64": "<png b64>"}
                   (or {"image_path": "/abs/file.png"}); optional "mode".
                   returns {"detections": [{"label": str, "box": [x1,y1,x2,y2],
                            "center": [cx, cy]}]}
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import logging
import os
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

log = logging.getLogger('locate_sidecar')

# Resolved once at startup from the environment / CLI flags.
CLI_BIN = ''
MODEL = ''
DEFAULT_MODE = 'hybrid'
THREADS = '0'
TIMEOUT_S = 120


def _run_detect(image_path: str, prompt: str, mode: str) -> dict:
    """Invoke ``locate-anything-cli detect`` and return the parsed JSON."""
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
        out_json = tmp.name
    try:
        cmd = [
            CLI_BIN, 'detect',
            '--model', MODEL,
            '--input', image_path,
            '--prompt', prompt,
            '--output', out_json,
            '--mode', mode,
            '--threads', THREADS,
        ]
        log.info('detect prompt=%r mode=%s', prompt, mode)
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=TIMEOUT_S, check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f'locate-anything-cli exited {proc.returncode}: '
                f'{proc.stderr.strip()[:500]}'
            )
        raw = Path(out_json).read_text() or proc.stdout
        data = json.loads(raw)
    finally:
        try:
            os.unlink(out_json)
        except OSError:
            pass

    detections = []
    for det in data.get('detections', []):
        box = det.get('box')
        if not box or len(box) != 4:
            continue
        x1, y1, x2, y2 = (float(v) for v in box)
        detections.append({
            'label': det.get('label', prompt),
            'box': [x1, y1, x2, y2],
            'center': [round((x1 + x2) / 2, 2), round((y1 + y2) / 2, 2)],
        })
    log.info(
        'detect prompt=%r mode=%s -> %d detections: %s',
        prompt, mode, len(detections),
        [(d['label'], d['box']) for d in detections],
    )
    return {'detections': detections}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):  # noqa: A003 - quiet the default stderr spam
        log.debug('%s - %s', self.address_string(), fmt % args)

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - stdlib handler name
        if self.path.rstrip('/') == '/health':
            self._send(200, {'status': 'ok', 'model': MODEL, 'bin': CLI_BIN})
            return
        self._send(404, {'error': 'not found'})

    def do_POST(self):  # noqa: N802 - stdlib handler name
        if self.path.rstrip('/') != '/locate':
            self._send(404, {'error': 'not found'})
            return

        length = int(self.headers.get('Content-Length', 0) or 0)
        try:
            req = json.loads(self.rfile.read(length) or b'{}')
        except (ValueError, json.JSONDecodeError) as exc:
            self._send(400, {'error': f'bad JSON body: {exc}'})
            return

        prompt = (req.get('prompt') or req.get('description') or '').strip()
        if not prompt:
            self._send(400, {'error': 'missing "prompt"'})
            return
        mode = req.get('mode') or DEFAULT_MODE

        tmp_img = None
        try:
            image_path = req.get('image_path')
            if not image_path:
                b64 = req.get('screenshot_base64')
                if not b64:
                    self._send(400, {'error': 'provide "screenshot_base64" or "image_path"'})
                    return
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tf:
                    tf.write(base64.b64decode(b64))
                    tmp_img = tf.name
                image_path = tmp_img
            result = _run_detect(image_path, prompt, mode)
            self._send(200, result)
        except (binascii.Error, ValueError) as exc:
            self._send(400, {'error': f'bad image data: {exc}'})
        except subprocess.TimeoutExpired:
            self._send(504, {'error': f'detect timed out after {TIMEOUT_S}s'})
        except (RuntimeError, OSError, json.JSONDecodeError) as exc:
            self._send(500, {'error': str(exc)})
        finally:
            if tmp_img:
                try:
                    os.unlink(tmp_img)
                except OSError:
                    pass


def main() -> int:
    ap = argparse.ArgumentParser(description='LocateAnything grounding sidecar')
    ap.add_argument('--host', default=os.environ.get('LA_HOST', '127.0.0.1'))
    ap.add_argument('--port', type=int, default=int(os.environ.get('LA_PORT', '13111')))
    ap.add_argument('--bin', default=os.environ.get('LA_CLI_BIN', ''))
    ap.add_argument('--model', default=os.environ.get('LA_MODEL', ''))
    ap.add_argument('--mode', default=os.environ.get('LA_MODE', 'hybrid'))
    ap.add_argument('--threads', default=os.environ.get('LA_THREADS', '0'))
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

    global CLI_BIN, MODEL, DEFAULT_MODE, THREADS
    CLI_BIN = args.bin
    MODEL = args.model
    DEFAULT_MODE = args.mode
    THREADS = str(args.threads)

    if not CLI_BIN or not Path(CLI_BIN).exists():
        log.error('locate-anything-cli not found: set --bin / LA_CLI_BIN (got %r)', CLI_BIN)
        return 2
    if not MODEL or not Path(MODEL).exists():
        log.error('GGUF model not found: set --model / LA_MODEL (got %r)', MODEL)
        return 2

    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    log.info('LocateAnything sidecar on http://%s:%d  (model=%s)', args.host, args.port, MODEL)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info('shutting down')
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
