"""HTTP client for the standalone LocateAnything grounding sidecar.

:class:`LocateAnythingClient` turns a natural-language element description +
screenshot into precise bounding boxes by calling the sidecar
(``scripts/locate_anything_sidecar.py``), which wraps the ``locate-anything-cli``
binary. Kept dependency-free (stdlib ``urllib``) so the ``adare`` package stays
free of torch/ggml; the heavy model lives entirely in the sidecar process.

Used at *record* time to tighten the recorded image crop to the true element
box (vs the fixed ~220x90 fallback), and as a reusable described-element
grounding entry point (see :meth:`MCPTargetResolver.find_element`).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class Detection:
    """One detected element: its label, box ``[x1, y1, x2, y2]`` and centre."""
    label: str
    box: tuple[float, float, float, float]
    center: tuple[float, float]

    @property
    def area(self) -> float:
        x1, y1, x2, y2 = self.box
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)

    def contains(self, x: float, y: float) -> bool:
        x1, y1, x2, y2 = self.box
        return x1 <= x <= x2 and y1 <= y <= y2

    def distance_to(self, x: float, y: float) -> float:
        cx, cy = self.center
        return ((cx - x) ** 2 + (cy - y) ** 2) ** 0.5


class LocateAnythingError(RuntimeError):
    """Raised when the grounding sidecar cannot be reached or errors out."""


class LocateAnythingClient:
    """Thin HTTP client for the LocateAnything grounding sidecar."""

    def __init__(self, base_url: str, *, timeout: float = 130.0, mode: str = 'hybrid'):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.mode = mode

    def health(self) -> dict:
        """Return the sidecar health payload (raises on unreachable)."""
        return self._get('/health')

    def locate(self, screenshot_b64: str, prompt: str) -> list[Detection]:
        """Return all detections for ``prompt`` on the screenshot (may be empty)."""
        payload = {
            'prompt': prompt,
            'screenshot_base64': screenshot_b64,
            'mode': self.mode,
        }
        data = self._post('/locate', payload)
        dets: list[Detection] = []
        for d in data.get('detections', []):
            box = d.get('box')
            if not box or len(box) != 4:
                continue
            x1, y1, x2, y2 = (float(v) for v in box)
            center = d.get('center') or [(x1 + x2) / 2, (y1 + y2) / 2]
            dets.append(Detection(
                label=d.get('label', prompt),
                box=(x1, y1, x2, y2),
                center=(float(center[0]), float(center[1])),
            ))
        return dets

    def best_for(
        self,
        screenshot_b64: str,
        prompt: str,
        *,
        near: tuple[float, float] | None = None,
        max_distance: float | None = None,
    ) -> Detection | None:
        """Pick the single best detection for ``prompt``.

        With ``near`` (e.g. the VLM's own click point), prefer a box that
        *contains* the point, then the closest box centre; ties break to the
        smaller (tighter) box. Without ``near``, return the smallest box.
        Returns ``None`` if nothing is found or all are beyond ``max_distance``.
        """
        dets = self.locate(screenshot_b64, prompt)
        if not dets:
            return None
        if near is None:
            return min(dets, key=lambda d: d.area)

        x, y = near
        containing = [d for d in dets if d.contains(x, y)]
        pool = containing or dets
        if not containing and max_distance is not None:
            pool = [d for d in pool if d.distance_to(x, y) <= max_distance]
            if not pool:
                return None
        return min(pool, key=lambda d: (d.distance_to(x, y), d.area))

    # -- transport ----------------------------------------------------------

    def _get(self, path: str) -> dict:
        return self._request('GET', path, None)

    def _post(self, path: str, payload: dict) -> dict:
        return self._request('POST', path, json.dumps(payload).encode('utf-8'))

    def _request(self, method: str, path: str, body: bytes | None) -> dict:
        url = f'{self.base_url}{path}'
        req = urllib.request.Request(url, data=body, method=method)
        if body is not None:
            req.add_header('Content-Type', 'application/json')
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read() or b'{}')
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', 'replace')[:500]
            raise LocateAnythingError(f'sidecar {method} {path} -> {exc.code}: {detail}') from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LocateAnythingError(f'sidecar unreachable at {url}: {exc}') from exc
        except (ValueError, json.JSONDecodeError) as exc:
            raise LocateAnythingError(f'sidecar returned invalid JSON: {exc}') from exc
        if isinstance(data, dict) and data.get('error'):
            raise LocateAnythingError(str(data['error']))
        return data
