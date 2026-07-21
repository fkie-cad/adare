"""CLI handler for `adare vm gui-doctor` — vision-LLM preflight for GUI automation.

Confirms the configured vLLM endpoint (ADARE_VLLM_*; e.g. Ollama Cloud) is
reachable and — the important part — detects which coordinate convention the
model returns clicks in, so a wrong ``ADARE_VLLM_COORD_SPACE`` guess can't
silently derail a record/install run.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import math

from adare.console import console, print_error_message, print_success_message

log = logging.getLogger(__name__)

# Synthetic calibration screen + a known target-box centre.
_IMG_W, _IMG_H = 1000, 800
_TARGET = (740, 250)  # centre of the drawn button, in pixels
_TOL = 120.0  # generous — grounding models are not pixel-perfect


def _classify_coords(rx: float, ry: float) -> tuple[str | None, float, float]:
    """Classify a returned (rx, ry) as 'absolute' vs 'normalized_1000'.

    Returns (detected_or_None, err_absolute_px, err_normalized_px). ``None`` when
    neither convention lands within tolerance of the known target.
    """
    def _err(px: float, py: float) -> float:
        return math.hypot(px - _TARGET[0], py - _TARGET[1])

    err_abs = _err(rx, ry)
    err_norm = _err(rx / 1000.0 * _IMG_W, ry / 1000.0 * _IMG_H)
    if min(err_abs, err_norm) > _TOL:
        return None, err_abs, err_norm
    return ('normalized_1000' if err_norm < err_abs else 'absolute'), err_abs, err_norm


def _calibration_png_b64() -> str:
    from PIL import Image, ImageDraw

    img = Image.new('RGB', (_IMG_W, _IMG_H), (32, 34, 40))
    draw = ImageDraw.Draw(img)
    # A single obvious button centred on _TARGET.
    bw, bh = 220, 90
    x0, y0 = _TARGET[0] - bw // 2, _TARGET[1] - bh // 2
    draw.rectangle([x0, y0, x0 + bw, y0 + bh], fill=(220, 60, 60))
    draw.text((x0 + 40, y0 + 35), 'CLICK HERE', fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


async def _run_checks() -> tuple[bool, str | None]:
    """Return (reachable, detected_coord_space). detected is None if unclear."""
    from adare.backend.experiment.vlm.actions import _extract_json_object
    from adare.backend.experiment.vlm.client import VLMClient
    from adare.backend.experiment.vlm.exceptions import VLMError
    from adare.config.server import VLLM_API_KEY, VLLM_BASE_URL, VLLM_MODEL

    client = VLMClient(base_url=VLLM_BASE_URL, model=VLLM_MODEL, api_key=VLLM_API_KEY)

    # 1) Text reachability / auth / model.
    try:
        reply = await client.chat(
            [{'role': 'user', 'content': 'Reply with the single word: OK'}],
            max_tokens=10,
        )
    except VLMError as exc:
        console.print(f'[red]✗ endpoint unreachable / auth failed[/red]: {exc}')
        return False, None
    console.print(f'[green]✓ endpoint reachable[/green] ({VLLM_BASE_URL}, model {VLLM_MODEL}) — replied: {reply.strip()[:40]!r}')

    # 2) Coordinate calibration.
    b64 = _calibration_png_b64()
    prompt = (
        f'The image is {_IMG_W}x{_IMG_H} pixels. Return the coordinates to click the '
        'red button labelled "CLICK HERE" as a single JSON object: {"x": <int>, "y": <int>}.'
    )
    reply = None
    try:
        reply = await client.chat(
            [{'role': 'user', 'content': [
                client.text_content(prompt), client.image_content(b64)]}],
            max_tokens=100,
        )
        obj = _extract_json_object(reply)
        rx, ry = float(obj['x']), float(obj['y'])
    except (VLMError, KeyError, ValueError, TypeError) as exc:
        console.print(f'[yellow]! could not parse a click from the model[/yellow]: {exc}')
        if reply is not None:
            console.print(f'  raw reply: {reply!r}')
        return True, None

    detected, err_abs, err_norm = _classify_coords(rx, ry)
    console.print(f'  model returned ({rx:.0f}, {ry:.0f}); target is {_TARGET}')
    console.print(f'  error as absolute pixels: {err_abs:.0f}px | as normalized_1000: {err_norm:.0f}px')

    if detected is None:
        console.print('[yellow]! neither convention matched well — the model may not be '
                      'grounding-capable, or the reply was off.[/yellow]')
        return True, None
    console.print(f'[green]✓ coordinate convention detected[/green]: {detected}')
    return True, detected


def exec_vm_gui_doctor(arguments):
    """Preflight the vLLM endpoint used for GUI automation."""
    import shutil

    from adare.config.server import FFMPEG, VLLM_BASE_URL, VLLM_COORD_SPACE, VLLM_MODEL

    if not VLLM_BASE_URL:
        print_error_message(
            title='No vLLM endpoint configured',
            next_steps=[
                'export ADARE_VLLM_BASE_URL=https://ollama.com/v1',
                'export ADARE_VLLM_API_KEY=<key>',
                'export ADARE_VLLM_MODEL=gemma4:31b',
            ],
        )
        return

    reachable, detected = asyncio.run(_run_checks())
    if not reachable:
        print_error_message(
            title='vLLM endpoint not usable',
            next_steps=['Verify ADARE_VLLM_BASE_URL / ADARE_VLLM_API_KEY / ADARE_VLLM_MODEL',
                        'For Ollama Cloud the base URL is https://ollama.com/v1'],
        )
        return

    # ffmpeg availability for `adare dev agent --video` (informational — video is
    # opt-in, so a missing binary must not fail the doctor).
    ffmpeg_path = shutil.which(FFMPEG)
    if ffmpeg_path:
        console.print(f'[green]✓ ffmpeg found[/green] (for `adare dev agent --video`): {ffmpeg_path}')
    else:
        console.print('[yellow]! ffmpeg not found[/yellow] — `--video` will error; '
                      'install ffmpeg or set ADARE_FFMPEG')

    next_steps = []
    if not ffmpeg_path:
        next_steps.append('For `adare dev agent --video`: install ffmpeg or set ADARE_FFMPEG')
    if detected and detected != VLLM_COORD_SPACE:
        next_steps.append(
            f'Set the coordinate space to match the model: '
            f'export ADARE_VLLM_COORD_SPACE={detected} (currently {VLLM_COORD_SPACE})'
        )
    elif detected:
        next_steps.append(f'Coordinate space already correct: ADARE_VLLM_COORD_SPACE={VLLM_COORD_SPACE}')
    else:
        next_steps.append('Could not auto-detect the coordinate space — try a grounding model '
                          '(e.g. gemma4:31b) and re-run.')

    print_success_message(
        title=f'GUI-automation preflight complete (model: {VLLM_MODEL})',
        next_steps=next_steps,
    )
