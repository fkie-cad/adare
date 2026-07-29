"""Vendored torch/MPS grounding server for LocateAnything-3B.

Exposes the tiny JSON contract that :class:`LocateAnythingClient` speaks
(``GET /health``, ``POST /locate {prompt, screenshot_base64, mode}`` ->
``{detections: [{label, box, center}]}``) backed by NVIDIA's
``nvidia/LocateAnything-3B`` vision-language grounding model, loaded locally on
Apple Silicon (MPS, falling back to CPU). It replaces the need for a pre-running
external endpoint: ``adare dev agent --ground`` auto-spawns this process and
tears it down at run end (see :mod:`.locate_process_manager`).

The worker is adapted from the external local test app
(``~/Documents/Projects/LocateAnything/app.py``), stripped of Gradio/FastAPI —
only the model load, the GUI-grounding prompt builder, and the ``<box>`` parser
remain. torch/transformers are imported **lazily inside the worker**, so merely
importing this module (or a base ``adare`` install without the ``grounding``
extra) never pulls in the heavy stack.

Kept free of any ``adare.*`` import on purpose: it can therefore be launched by
a *foreign* interpreter (one whose venv already has torch + the model's
``trust_remote_code`` deps) via its file path — see ``ADARE_LOCATE_PYTHON`` in
the process manager. Run directly:

    python -m adare.backend.experiment.grounding.locate_server --port 13111

License: **NVIDIA LocateAnything is non-commercial** — local testing only.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import logging
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('locate_server')

DEFAULT_MODEL = 'nvidia/LocateAnything-3B'

# GUI-grounding (box) prompt template, from the model card / external app.py.
_BUILD = lambda q: f'Locate the region that matches the following description: {q}.'  # noqa: E731

# Sequentially parse `<ref>label</ref><box><x1><y1><x2><y2></box>...` — a label
# then a 4-coord box or a 2-coord point. Coordinates are normalized [0, 1000].
_TOKEN_RE = re.compile(
    r'<ref>(.*?)</ref>'
    r'|<box><(\d+)><(\d+)><(\d+)><(\d+)></box>'
    r'|<box><(\d+)><(\d+)></box>'
)


def parse_output(answer: str, w: int, h: int) -> list[tuple]:
    """Parse the model answer into labeled pixel boxes ``(label, x1, y1, x2, y2)``."""
    boxes: list[tuple] = []
    label = ''
    for m in _TOKEN_RE.finditer(answer):
        if m.group(1) is not None:
            label = m.group(1).strip()
        elif m.group(2) is not None:
            x1, y1, x2, y2 = (int(m.group(i)) for i in (2, 3, 4, 5))
            boxes.append((label, x1 / 1000 * w, y1 / 1000 * h, x2 / 1000 * w, y2 / 1000 * h))
        # 2-coord points (group 6/7) are ignored: the client contract is boxes.
    return boxes


def _ensure_decord_importable() -> None:
    """Register a stub ``decord`` module when the real one can't be imported.

    LocateAnything's ``trust_remote_code`` processor does a hard top-level
    ``import decord``, but only *uses* it to read video files (guarded by
    ``is_decord_available()`` with a torchvision fallback). ADARE only ever
    grounds still screenshots, so that video path never runs — the bare import
    is the sole obstacle. ``decord`` ships no macOS-arm64 wheel, so on Apple
    Silicon the import fails and blocks image grounding for no real reason.

    If ``decord`` imports for real (e.g. Linux), do nothing. Otherwise inject a
    minimal placeholder into ``sys.modules`` so the import succeeds. It carries a
    real ``ModuleSpec`` (a bare ``__spec__ = None`` makes ``find_spec`` *raise*,
    not return None), so the processor's ``is_decord_available()`` reads True and
    picks the decord backend for video — but ``fetch_video`` wraps that call in a
    try/except and falls back to torchvision when the stub's ``VideoReader``
    raises, so video would still work and image grounding is untouched.
    """
    import importlib.machinery
    import importlib.util

    if importlib.util.find_spec('decord') is not None:
        return  # real decord is installed — use it

    import types

    stub = types.ModuleType('decord')
    stub.__spec__ = importlib.machinery.ModuleSpec('decord', loader=None)

    def _unavailable(*_args, **_kwargs):
        raise NotImplementedError(
            'decord is a stub on this platform (no macOS-arm64 wheel); ADARE '
            'grounds still images, not video.'
        )

    stub.VideoReader = _unavailable
    sys.modules['decord'] = stub
    log.info('decord unavailable — registered a stub (image grounding only)')


class GroundingExtraMissing(RuntimeError):
    """Raised when the optional ``grounding`` extra (torch/transformers) is absent."""


class LocateAnythingWorker:
    """Loads LocateAnything-3B once and serves GUI-grounding queries (MPS/CPU)."""

    def __init__(self, model_path: str = DEFAULT_MODEL, device: str | None = None):
        try:
            import torch
            from transformers import AutoModel, AutoProcessor, AutoTokenizer
        except ImportError as exc:  # extra not installed in this interpreter
            raise GroundingExtraMissing(
                f'grounding backend needs torch/transformers ({exc}). '
                'Install the extra:  uv sync --extra grounding  — or point '
                'ADARE_LOCATE_PYTHON at an interpreter that already has them.'
            ) from exc

        # The model's trust_remote_code processor hard-imports decord (video
        # only). Satisfy it with a stub where no wheel exists (macOS-arm64) so
        # image grounding loads. No-op when real decord is present.
        _ensure_decord_importable()

        self.dtype = torch.bfloat16
        self.device = device or ('mps' if torch.backends.mps.is_available() else 'cpu')
        log.info('loading %s on %s (%s) ...', model_path, self.device, self.dtype)
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        self.processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
        self.model = (
            AutoModel.from_pretrained(
                model_path, dtype=self.dtype, trust_remote_code=True,
                _attn_implementation='sdpa',
            )
            .to(self.device)
            .eval()
        )
        log.info('worker ready on %s', self.device)

    def predict(self, image, question: str, mode: str = 'hybrid',
                max_new_tokens: int = 2048, temperature: float = 0.7,
                top_p: float = 0.9, repetition_penalty: float = 1.1) -> str:
        import torch

        messages = [{'role': 'user', 'content': [
            {'type': 'image', 'image': image},
            {'type': 'text', 'text': question},
        ]}]
        text = self.processor.py_apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        images, videos = self.processor.process_vision_info(messages)
        inputs = self.processor(
            text=[text], images=images, videos=videos, return_tensors='pt'
        ).to(self.device)

        do_sample = temperature is not None and temperature > 0
        with torch.no_grad():
            response = self.model.generate(
                pixel_values=inputs['pixel_values'].to(self.dtype),
                input_ids=inputs['input_ids'],
                attention_mask=inputs['attention_mask'],
                image_grid_hws=inputs.get('image_grid_hws', None),
                tokenizer=self.tokenizer,
                max_new_tokens=int(max_new_tokens),
                use_cache=True,
                generation_mode=mode,
                temperature=float(temperature),
                do_sample=do_sample,
                top_p=float(top_p),
                repetition_penalty=float(repetition_penalty),
                verbose=False,
            )
        return response[0] if isinstance(response, tuple) else response


_WORKER: LocateAnythingWorker | None = None
_MODEL_PATH = os.environ.get('ADARE_LOCATE_MODEL_PATH', '') or DEFAULT_MODEL

# The model load is expensive (~7 GB) and happens exactly once. `_LOAD_LOCK`
# serializes it so that concurrent callers (the readiness prober reconnecting in
# fresh ThreadingHTTPServer threads, plus /locate requests) never kick off a
# second `from_pretrained` — stacked loads used to thrash MPS and could stop the
# load ever completing. `_LOADING` / `_LOAD_ERROR` let /health answer instantly.
_LOAD_LOCK = threading.Lock()
_LOADING = False
_LOAD_ERROR: str | None = None


def get_worker() -> LocateAnythingWorker:
    """Build the singleton worker under a lock (blocks on first call: model load).

    Serialized by ``_LOAD_LOCK`` so only one ``from_pretrained`` ever runs even
    though the server is threaded and several callers may race here at once.
    """
    global _WORKER, _LOADING, _LOAD_ERROR
    if _WORKER is not None:
        return _WORKER
    with _LOAD_LOCK:
        if _WORKER is None:  # re-check: another thread may have loaded it
            _LOADING = True
            try:
                _WORKER = LocateAnythingWorker(_MODEL_PATH)
                _LOAD_ERROR = None
            except (GroundingExtraMissing, OSError, ValueError, RuntimeError, ImportError) as exc:
                _LOAD_ERROR = str(exc)
                raise
            finally:
                _LOADING = False
    return _WORKER


def _load_image(body: dict):
    from PIL import Image

    b64 = body.get('screenshot_base64')
    if b64:
        return Image.open(io.BytesIO(base64.b64decode(b64))).convert('RGB')
    path = body.get('image_path')
    if path:
        return Image.open(path).convert('RGB')
    raise ValueError('request needs screenshot_base64 or image_path')


def _locate(prompt: str, image, mode: str) -> list[dict]:
    """Run one grounding query, returning ADARE-contract detections."""
    w, h = image.size
    answer = get_worker().predict(image, _BUILD(prompt), mode=mode)
    dets = []
    for label, x1, y1, x2, y2 in parse_output(answer, w, h):
        dets.append({
            'label': label or prompt,
            'box': [x1, y1, x2, y2],
            'center': [(x1 + x2) / 2, (y1 + y2) / 2],
        })
    return dets


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict) -> None:
        data = json.dumps(payload).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):  # route through logging
        log.info('%s - %s', self.address_string(), fmt % args)

    def do_GET(self):
        if self.path.rstrip('/') == '/health':
            # Non-blocking: report the state of the background load rather than
            # driving it. The model is loaded once by the daemon thread started
            # in main(); probes must return instantly so the manager sees clean
            # 503s (loading) until the single load finishes, not 5 s stalls.
            if _WORKER is not None:
                self._send(200, {'status': 'ok', 'model': _MODEL_PATH})
            elif _LOAD_ERROR is not None:
                self._send(503, {'status': 'error', 'error': _LOAD_ERROR})
            else:
                self._send(503, {'status': 'loading', 'model': _MODEL_PATH})
        else:
            self._send(404, {'error': f'no route {self.path}'})

    def do_POST(self):
        if self.path.rstrip('/') != '/locate':
            self._send(404, {'error': f'no route {self.path}'})
            return
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length) or b'{}')
            prompt = body.get('prompt') or ''
            mode = body.get('mode') or 'hybrid'
            image = _load_image(body)
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            self._send(400, {'error': f'bad request: {exc}'})
            return
        try:
            dets = _locate(prompt, image, mode)
        except GroundingExtraMissing as exc:
            self._send(503, {'error': str(exc)})
            return
        except (RuntimeError, ValueError, OSError) as exc:
            # A locate miss must never abort the agent: return empty -> the
            # client degrades to its fixed-crop / VLM-point fallback.
            log.warning('locate failed for %r: %s', prompt, exc)
            self._send(200, {'detections': []})
            return
        log.info('locate %r mode=%s -> %d detections', prompt, mode, len(dets))
        self._send(200, {'detections': dets})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=13111)
    ap.add_argument('--model', default=None,
                    help='HF id or local path (default: ADARE_LOCATE_MODEL_PATH or '
                         f'{DEFAULT_MODEL}). Use a local path + HF_HUB_OFFLINE=1 for offline.')
    args = ap.parse_args(argv)

    global _MODEL_PATH
    if args.model:
        _MODEL_PATH = args.model

    # Fail fast with a clear message if the heavy stack isn't importable here,
    # rather than only surfacing it on the first /health.
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError as exc:
        log.error('grounding backend unavailable: %s', exc)
        log.error('run:  uv sync --extra grounding  (or set ADARE_LOCATE_PYTHON)')
        return 1

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    log.info('LocateAnything grounding server on http://%s:%d (model=%s, loading in background)',
             args.host, args.port, _MODEL_PATH)

    # Bind the port first (above), then load the model once in the background so
    # /health can answer immediately while the weights load. Failures are
    # captured into _LOAD_ERROR so /health reports status:"error" (the manager
    # then fails fast instead of waiting out the whole timeout).
    def _preload():
        try:
            get_worker()
        except (GroundingExtraMissing, OSError, ValueError, RuntimeError, ImportError) as exc:
            log.error('model load failed: %s', exc)

    threading.Thread(target=_preload, name='locate-preload', daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info('shutting down')
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
