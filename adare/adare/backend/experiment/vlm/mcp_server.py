"""Expose one running dev-session VM as an MCP server for an external harness.

ADARE is not the agentic loop here — an external harness (OpenCode, Claude Code,
or any MCP client, model-agnostic, including one driving a local Ollama model)
is the brain. This server hands that brain ADARE's real strengths: VM control
over QMP, CV/OCR grounding, a testfunction catalog to search, and a recorder
that turns a natural-language session into a deterministic, replayable ADARE
playbook (image crops + OCR text + a ``tests:`` block).

Grounding model: the harness reads :meth:`screenshot` and decides where to click
(cloud vision first-assembles during *record*); each recorded click auto-crops
the pre-click screenshot into an ``image:`` target so *replay* re-finds it with
CV (:func:`find_icon`) / OCR (:func:`find_text`) and **no LLM**. ``find_text`` /
``find_icon`` are also exposed as record-time grounding aids.

The server is long-lived and bound to an already-running dev session; it is
constructed by :class:`~adare.services.devmode.mcp_serving.McpServingMixin`.
"""

from __future__ import annotations

import base64
import io
import logging
import shutil
from pathlib import Path
from typing import Any

from PIL import Image

log = logging.getLogger(__name__)

DEFAULT_MCP_PATH = '/mcp'


class GuiMcpServer:
    """A ``FastMCP`` server bound to one dev session's VM + CV + recorder + catalog.

    Constructed with already-resolved collaborators so it stays free of the
    DB / session-manager and is unit-testable with fakes:

    - ``executor``: a :class:`QEMUHostGUIExecutor`-shaped object with async
      ``screenshot`` / ``click`` / ``keyboard`` / ``scroll`` methods.
    - ``resolver``: an :class:`MCPTargetResolver`-shaped object with an async
      ``resolve_target(target, screenshot_base64=...)`` and a mutable
      ``images_dir`` attribute (pointed at the active recording's crops).
    - ``catalog``: the testfunction catalog as a list of dicts (see
      :meth:`list_testfunctions`).
    - ``base_dir``: where recordings (playbook YAML + ``img/`` crops) are written.
    """

    def __init__(
        self,
        *,
        executor: Any,
        resolver: Any,
        catalog: list[dict[str, Any]],
        base_dir: str | Path,
        cv_url: str = 'http://localhost:13109/mcp',
        server_name: str = 'adare-gui',
        recorder_factory: Any | None = None,
    ):
        self._executor = executor
        self._resolver = resolver
        self._catalog = list(catalog or [])
        self._base_dir = Path(base_dir)
        self._cv_url = cv_url
        self._server_name = server_name
        if recorder_factory is None:
            from adare.backend.experiment.vlm.recorder import PlaybookRecorder
            recorder_factory = PlaybookRecorder
        self._recorder_factory = recorder_factory

        # Valid test-function identifiers (dotnotation preferred; name accepted).
        self._known_functions: set[str] = set()
        for entry in self._catalog:
            for key in ('dotnotation', 'name'):
                value = entry.get(key)
                if value:
                    self._known_functions.add(value)

        self._recorder: Any | None = None
        self._recording = False
        self._last_png: bytes | None = None

        self.mcp = self._build_mcp()

    # -- MCP registration ---------------------------------------------------

    def _build_mcp(self):
        from fastmcp import FastMCP

        mcp = FastMCP(name=self._server_name)

        @mcp.tool()
        async def screenshot() -> dict[str, Any]:
            """Capture the VM screen. Returns base64 PNG + pixel dimensions.

            Read this to decide where to click/type. The image is cached so the
            next ``click`` can crop a robust image target around your point.
            """
            return await self.screenshot()

        @mcp.tool()
        async def click(x: int, y: int, button: str = 'left', describe: str = '') -> dict[str, Any]:
            """Click at absolute pixel (x, y). ``button``: left|right|middle.

            While recording, appends a ClickAction whose target is a crop of the
            pre-click screenshot; ``describe`` names the target for humans + the
            self-heal path.
            """
            return await self.click(x, y, button=button, describe=describe)

        @mcp.tool()
        async def double_click(x: int, y: int, describe: str = '') -> dict[str, Any]:
            """Double-click at absolute pixel (x, y)."""
            return await self.click(x, y, button='double', describe=describe)

        @mcp.tool()
        async def type(text: str, describe: str = '') -> dict[str, Any]:
            """Type literal text into the focused field."""
            return await self.type_text(text, describe=describe)

        @mcp.tool()
        async def key(combo: str, describe: str = '') -> dict[str, Any]:
            """Press a key or hotkey combo, e.g. ``enter`` or ``ctrl+s``."""
            return await self.key(combo, describe=describe)

        @mcp.tool()
        async def scroll(direction: str, amount: int = 3, describe: str = '') -> dict[str, Any]:
            """Scroll ``up`` or ``down`` by ``amount`` wheel steps."""
            return await self.scroll(direction, amount, describe=describe)

        @mcp.tool()
        async def wait(seconds: float) -> dict[str, Any]:
            """Wait for the UI to settle; recorded as an ``idle`` action."""
            return await self.wait(seconds)

        @mcp.tool()
        async def find_text(text: str) -> dict[str, Any]:
            """OCR grounding aid: locate ``text`` on screen. Returns x, y, confidence."""
            return await self.find_text(text)

        @mcp.tool()
        async def find_icon(image_name: str) -> dict[str, Any]:
            """Template grounding aid: locate a saved crop (``img/<name>``) on screen."""
            return await self.find_icon(image_name)

        @mcp.tool()
        async def list_testfunctions() -> list[dict[str, Any]]:
            """Search the project's testfunctions (name, dotnotation, params, ...).

            Use this to find an assertion for a goal like "verify the file is
            gone", then register it with ``add_test``.
            """
            return self.list_testfunctions()

        @mcp.tool()
        async def start_recording(goal: str = '', path: str = '') -> dict[str, Any]:
            """Begin recording GUI actions into a replayable playbook."""
            return self.start_recording(goal=goal, path=path or None)

        @mcp.tool()
        async def stop_recording() -> dict[str, Any]:
            """Stop appending actions (does not write the file; use save_playbook)."""
            return self.stop_recording()

        @mcp.tool()
        async def add_test(
            name: str, function: str, parameters: dict[str, Any] | None = None,
            description: str = '',
        ) -> dict[str, Any]:
            """Add an assertion to the recording, validated against the catalog.

            ``function`` must be a known testfunction (dotnotation or name) from
            ``list_testfunctions`` — unknown functions are rejected. Defines the
            test in the ``tests:`` block and runs it at the current point.
            """
            return self.add_test(name, function, parameters=parameters, description=description)

        @mcp.tool()
        async def add_variable(name: str, value: Any) -> dict[str, Any]:
            """Register a ``variables:`` entry so the playbook is parameterizable."""
            return self.add_variable(name, value)

        @mcp.tool()
        async def save_playbook(path: str = '') -> dict[str, Any]:
            """Write the recorded playbook (GUI actions + tests) and return its path."""
            return self.save_playbook(path or None)

        @mcp.tool()
        async def run_playbook(path: str) -> dict[str, Any]:
            """Replay a playbook deterministically (CV/OCR, no LLM)."""
            return await self.run_playbook(path)

        return mcp

    # -- perception / control ----------------------------------------------

    async def _capture(self) -> bytes:
        """Screenshot the VM, cache and return the raw PNG bytes."""
        res = await self._executor.screenshot()
        if res.get('status') != 'success':
            raise RuntimeError(res.get('message', 'screenshot failed'))
        b64 = res['image']['data']
        png = base64.b64decode(b64)
        self._last_png = png
        return png

    async def screenshot(self) -> dict[str, Any]:
        png = await self._capture()
        width = height = None
        try:
            with Image.open(io.BytesIO(png)) as img:
                width, height = img.size
        except (OSError, ValueError):
            pass
        return {
            'status': 'success',
            'image': base64.b64encode(png).decode('ascii'),
            'format': 'png',
            'width': width,
            'height': height,
        }

    async def click(self, x: int, y: int, *, button: str = 'left', describe: str = '') -> dict[str, Any]:
        result = await self._executor.click(int(x), int(y), button_type=button)
        if self._recording:
            png = self._last_png or await self._capture()
            self._recorder.record_click(
                png, int(x), int(y), describe or f'click ({x}, {y})',
                button='left' if button == 'double' else button,
                double=(button == 'double'),
            )
        return result

    async def type_text(self, text: str, *, describe: str = '') -> dict[str, Any]:
        result = await self._executor.keyboard('type', text)
        if self._recording:
            self._recorder.record_type(text, describe)
        return result

    async def key(self, combo: str, *, describe: str = '') -> dict[str, Any]:
        action_type = 'hotkey' if '+' in combo else 'press'
        result = await self._executor.keyboard(action_type, combo)
        if self._recording:
            self._recorder.record_key(combo, describe)
        return result

    async def scroll(self, direction: str, amount: int = 3, *, describe: str = '') -> dict[str, Any]:
        result = await self._executor.scroll(direction, int(amount))
        if self._recording:
            self._recorder.record_scroll(direction, int(amount), describe)
        return result

    async def wait(self, seconds: float) -> dict[str, Any]:
        import asyncio
        await asyncio.sleep(float(seconds))
        if self._recording:
            self._recorder.record_idle(float(seconds), f'wait {seconds}s')
        return {'status': 'success', 'message': f'waited {seconds}s'}

    # -- grounding aids -----------------------------------------------------

    async def _resolve(self, target: Any) -> dict[str, Any]:
        png = self._last_png or await self._capture()
        b64 = base64.b64encode(png).decode('ascii')
        match = await self._resolver.resolve_target(target, screenshot_base64=b64)
        if match is None:
            return {'status': 'not_found'}
        x, y = match.coordinates
        return {
            'status': 'success',
            'x': int(x),
            'y': int(y),
            'confidence': float(match.confidence),
            'method': match.method,
        }

    async def find_text(self, text: str) -> dict[str, Any]:
        from adare.types.playbook import Target
        return await self._resolve(Target(text=text))

    async def find_icon(self, image_name: str) -> dict[str, Any]:
        from adare.types.playbook import Target
        return await self._resolve(Target(image=image_name))

    # -- discovery ----------------------------------------------------------

    def list_testfunctions(self) -> list[dict[str, Any]]:
        """Return the testfunction catalog (host-mode compatibility is checked at replay)."""
        return [dict(entry) for entry in self._catalog]

    # -- authoring ----------------------------------------------------------

    def start_recording(self, *, goal: str = '', path: str | Path | None = None) -> dict[str, Any]:
        if path:
            playbook_path = Path(path)
        else:
            playbook_path = self._base_dir / 'gui_recording' / 'recording.play.yaml'
            if playbook_path.parent.exists():
                shutil.rmtree(playbook_path.parent)
        playbook_path.parent.mkdir(parents=True, exist_ok=True)
        self._recorder = self._recorder_factory(playbook_path, goal=goal)
        self._recording = True
        self._last_png = None
        # Point the CV resolver at this recording's crops so find_icon works.
        self._resolver.images_dir = self._recorder.img_dir
        return {'status': 'success', 'recording_path': str(playbook_path)}

    def stop_recording(self) -> dict[str, Any]:
        self._recording = False
        count = self._recorder.action_count if self._recorder else 0
        return {'status': 'success', 'action_count': count}

    def add_test(
        self, name: str, function: str,
        *, parameters: dict[str, Any] | None = None, description: str = '',
    ) -> dict[str, Any]:
        if self._recorder is None:
            return {'status': 'error', 'message': 'Not recording — call start_recording first'}
        if function not in self._known_functions:
            return {
                'status': 'error',
                'message': (f"Unknown testfunction '{function}'. "
                            'Call list_testfunctions for valid names/dotnotations.'),
            }
        self._recorder.add_test(name, function, parameter=parameters, description=description)
        return {'status': 'success', 'name': name, 'function': function}

    def add_variable(self, name: str, value: Any) -> dict[str, Any]:
        if self._recorder is None:
            return {'status': 'error', 'message': 'Not recording — call start_recording first'}
        self._recorder.add_variable(name, value)
        return {'status': 'success', 'name': name}

    def save_playbook(self, path: str | Path | None = None) -> dict[str, Any]:
        if self._recorder is None:
            return {'status': 'error', 'message': 'Nothing recorded — call start_recording first'}
        recorded_path = self._recorder.finalize()
        self._recording = False
        if path is None:
            return {'status': 'success', 'path': str(recorded_path)}

        target = Path(path)
        if target.resolve() == recorded_path.resolve():
            return {'status': 'success', 'path': str(recorded_path)}
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(recorded_path, target)
        # Carry the image crops + sidecar so relative img/ references stay valid.
        src_img = self._recorder.img_dir
        if src_img.is_dir():
            dst_img = target.parent / 'img'
            dst_img.mkdir(parents=True, exist_ok=True)
            for crop in src_img.iterdir():
                if crop.is_file():
                    shutil.copyfile(crop, dst_img / crop.name)
        src_meta = self._recorder.meta_path
        if src_meta.is_file():
            shutil.copyfile(src_meta, target.with_suffix('.meta.json'))
        return {'status': 'success', 'path': str(target)}

    # -- replay -------------------------------------------------------------

    async def run_playbook(self, path: str | Path) -> dict[str, Any]:
        from adare.backend.experiment.vlm.replay import run_playbook as _run_playbook

        vm = getattr(self._executor, 'vm', None)
        result = await _run_playbook(vm, Path(path), mcp_gui_url=self._cv_url, os_key='linux')
        return {
            'status': 'success' if result.success else 'failed',
            'success': result.success,
            'total': result.total,
            'executed': result.executed,
            'healed': list(result.healed),
            'failures': list(result.failures),
        }

    # -- lifecycle ----------------------------------------------------------

    async def serve_async(self, host: str, port: int, path: str = DEFAULT_MCP_PATH) -> None:
        """Run the server over streamable HTTP on the current event loop.

        Preferred entry point: the caller builds the session/VM connections in
        the same loop, so the QMP-backed executor stays valid for tool calls.
        """
        log.info('ADARE GUI MCP server listening on http://%s:%d%s', host, port, path)
        await self.mcp.run_async(transport='streamable-http', host=host, port=port, path=path)

    def serve(self, host: str, port: int, path: str = DEFAULT_MCP_PATH) -> None:
        """Run the server (blocking) over streamable HTTP — same transport as the CV server."""
        log.info('ADARE GUI MCP server listening on http://%s:%d%s', host, port, path)
        self.mcp.run(transport='streamable-http', host=host, port=port, path=path)
