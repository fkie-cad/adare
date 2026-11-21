"""Write run screenshots to disk and shrink them losslessly in the background.

Screenshots arrive as PNGs encoded quickly by the guest agent (Pillow's default
level 6) or the host QMP path (level 1). Re-encoding at zlib level 9 keeps every
pixel and cuts the file by roughly 25-50%, but costs about 1 s of CPU per 1080p
frame. Doing that inline would add that time to every action, so
:func:`store_screenshot` writes the original bytes at once (the file is valid
immediately, also if the process dies) and a worker thread re-encodes it and
swaps it in atomically, only when the result is smaller.

``ADARE_SCREENSHOT_PNG_LEVEL`` picks the zlib level (0-9, default 9);
``off`` keeps the bytes exactly as captured.
"""

from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor, wait
from pathlib import Path

from PIL import Image

log = logging.getLogger(__name__)

ENV_VAR = 'ADARE_SCREENSHOT_PNG_LEVEL'
DEFAULT_LEVEL = 9
_WORKERS = 2

_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None
_pending: set[Future] = set()


def png_level() -> int | None:
    """zlib level for recompression, or None when recompression is off."""
    raw = os.environ.get(ENV_VAR, '').strip().lower()
    if not raw:
        return DEFAULT_LEVEL
    if raw in ('off', 'none', 'false', 'no'):
        return None
    try:
        level = int(raw)
    except ValueError:
        level = -1
    if 0 <= level <= 9:
        return level
    log.warning(f"{ENV_VAR}={raw!r} is not 0-9 or 'off'; using level {DEFAULT_LEVEL}")
    return DEFAULT_LEVEL


def recompress_png(path: Path, level: int) -> bool:
    """Re-encode the PNG at ``path`` losslessly at ``level``; replace it only if smaller.

    Returns True when the file was replaced. Pixels, mode and ICC profile are kept.
    """
    tmp = path.with_name(f".{path.name}.recompress.tmp")
    try:
        original_size = path.stat().st_size
        with Image.open(path) as img:
            if img.format != 'PNG':
                return False
            img.load()
            save_kwargs: dict = {'compress_level': level}
            if img.info.get('icc_profile'):
                save_kwargs['icc_profile'] = img.info['icc_profile']
            img.save(tmp, format='PNG', **save_kwargs)
        if tmp.stat().st_size >= original_size:
            tmp.unlink()
            return False
        os.replace(tmp, path)
        return True
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        log.warning(f"Screenshot recompression skipped for {path} (original kept): {exc}")
        tmp.unlink(missing_ok=True)
        return False


def _submit(path: Path, level: int) -> None:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=_WORKERS, thread_name_prefix='png-recompress')
        future = _executor.submit(recompress_png, path, level)
        _pending.add(future)
    future.add_done_callback(_discard)


def _discard(future: Future) -> None:
    with _lock:
        _pending.discard(future)


def store_screenshot(path: Path, png_bytes: bytes) -> None:
    """Write ``png_bytes`` to ``path`` now; schedule lossless recompression.

    Raises OSError when the write itself fails (as a plain write would).
    """
    path.write_bytes(png_bytes)
    level = png_level()
    if level is not None:
        _submit(path, level)


def wait_for_pending(timeout: float | None = None) -> int:
    """Block until queued recompressions finish; returns how many are still running."""
    with _lock:
        pending = set(_pending)
    if not pending:
        return 0
    _, not_done = wait(pending, timeout=timeout)
    return len(not_done)
