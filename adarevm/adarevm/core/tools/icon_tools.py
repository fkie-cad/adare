"""
Icon extraction tool method for AdareVMServer.

Exposes ``extract_icon`` over the existing WebSocket protocol: given a
version-independent resolver spec, it resolves the correct icon on THIS
Windows target via the shell APIs in ``platforms/windows_icons.py`` and
returns it as a base64 PNG. The host caches the result -- Microsoft's bitmaps
are never shipped, only extracted at runtime on the licensed target.

Mirrors ``gui_tools.py::GUIToolsMixin``: async method taking ``websocket``
first, lazy imports the platform module, and emits LOG/ERROR events. Failures
raise specific exceptions so the server reports ``success=False`` and the host
``call_tool`` surfaces the reason.
"""

from __future__ import annotations

import logging

from adarelib.websocket.protocol import EventType

log = logging.getLogger(__name__)


class IconToolsMixin:
    """Mixin providing the icon extraction tool method."""

    async def _extract_icon(self, websocket, spec: dict, size: int = 256):
        """Extract a Windows icon described by a resolver spec.

        Args:
            spec: Single-strategy resolver spec (stock/exe/app/fileassoc/dll).
            size: Desired icon edge in pixels (default 256, the largest variant).

        Returns:
            dict with the base64 PNG: ``{"format": "png", "encoding":
            "base64", "size": <px>, "data": <b64>, "spec": <spec>}``.

        Raises:
            WindowsIconError (and subclasses): on unsupported platform, a
            malformed spec, a Win32 resolution failure, or a render failure.
        """
        from adarevm.platforms.windows_icons import WindowsIconError, extract_icon_png

        await self.send_event(websocket, EventType.LOG, {
            "message": f"Extracting icon for spec: {spec}"
        })

        try:
            encoded = extract_icon_png(spec, size=size)
        except WindowsIconError as exc:
            # Surface the specific failure to the host, then re-raise so the
            # server reports success=False (see AdareVMServer.handle_tool_call).
            log.error(f"Icon extraction failed for spec {spec}: {exc}")
            await self.send_event(websocket, EventType.ERROR, {
                "message": f"Icon extraction failed: {exc}"
            })
            raise

        await self.send_event(websocket, EventType.LOG, {
            "message": f"Extracted icon ({len(encoded)} base64 chars)"
        })
        return {
            "format": "png",
            "encoding": "base64",
            "size": size,
            "data": encoded,
            "spec": spec,
        }
