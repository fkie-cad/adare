"""HostsideClient: the agent-free implementation of the guest tool interface.

The host drives the guest through ``AdareVMClient`` (WebSocket tool calls to the
in-guest ``adarevm``): ``screenshot``, ``click``, ``keyboard``, ``execute_shell``,
``get_timestamp``, ``pull_file_chunked``, ``run_test``, ... ``HostsideClient`` has
the same method surface, so the playbook controller, the action executors and the
CV pipeline run unchanged; behind it there is no guest process:

=======================  ====================================================
tool                     host-side implementation
=======================  ====================================================
screenshot / click /     QMP ``screendump`` / ``input-send-event`` through the
drag / keyboard /        existing ``QEMUHostGUIExecutor`` (USB tablet, absolute
scroll / goto            coordinates)
idle                     ``asyncio.sleep`` on the host
get_timestamp            host clock (guest RTC is seeded from the host,
                         ``<clock offset='utc'>``); time zone read offline
execute_shell            file-effect commands were staged into the overlay
                         before boot; anything else fails loudly (class d)
pull_file_chunked        deferred: extracted from the quiesced image
run_test                 not used: tests are deferred to the quiesced image
collect_system_info      offline, from the final image
get_filesystem_snapshot  not supported (offline diff replaces it)
=======================  ====================================================
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from adare.backend.hostside.session import HostsideSession

log = logging.getLogger(__name__)


class HostsideUnsupportedError(RuntimeError):
    """A guest tool that cannot be provided without a component in the guest."""


class HostsideClient:
    """Duck-typed replacement for ``AdareVMClient`` (no connection, no guest process)."""

    is_hostside = True

    def __init__(self, vm, session: HostsideSession):
        from adare.backend.experiment.execution.qemu_host_gui_executor import QEMUHostGUIExecutor

        self.vm = vm
        self.session = session
        self.connected = True
        self.host = None
        self.port = None
        self._gui = QEMUHostGUIExecutor(vm=vm)

    # -- connection management (nothing to connect) ---------------------------------

    async def connect(self, timeout: float = 10.0, quiet: bool = False) -> bool:
        self.connected = True
        return True

    async def disconnect(self) -> None:
        self.connected = False

    async def reconnect(self, retries: int = 3, base_delay: float = 2.0) -> bool:
        self.connected = True
        return True

    async def ping(self) -> bool:
        return True

    async def wait_for_connection(self, timeout: float = 30.0) -> bool:
        return True

    def is_connected(self) -> bool:
        return True

    def add_event_handler(self, event_type: str, handler) -> None:
        return None

    def remove_event_handler(self, event_type: str, handler) -> None:
        return None

    async def __aenter__(self) -> HostsideClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    # -- GUI: QMP ---------------------------------------------------------------------

    async def screenshot(self, x=None, y=None, width=None, height=None) -> dict[str, Any]:
        region = None
        if None not in (x, y, width, height):
            region = {'x': x, 'y': y, 'width': width, 'height': height}
        return await self._gui.screenshot(region)

    async def click(self, x: int, y: int) -> dict[str, Any]:
        return await self._gui.click(x, y, 'left')

    async def right_click(self, x: int, y: int) -> dict[str, Any]:
        return await self._gui.click(x, y, 'right')

    async def double_click(self, x: int, y: int) -> dict[str, Any]:
        return await self._gui.click(x, y, 'double')

    async def drag(self, x1: int, y1: int, x2: int, y2: int) -> dict[str, Any]:
        return await self._gui.drag(x1, y1, x2, y2)

    async def keyboard(self, type: str, key: str) -> dict[str, Any]:
        return await self._gui.keyboard(type, key)

    async def scroll(self, direction: str, amount: int) -> dict[str, Any]:
        return await self._gui.scroll(direction, amount)

    async def goto(self, x: int, y: int) -> dict[str, Any]:
        raise HostsideUnsupportedError('goto (pointer move without click) is not provided by the QMP GUI executor')

    async def idle(self, duration: float) -> dict[str, Any]:
        await asyncio.sleep(duration)
        return {'status': 'success', 'message': f'idled {duration}s on the host'}

    async def screenshot_window(self, window: str) -> dict[str, Any]:
        raise HostsideUnsupportedError('per-window screenshots need a compositor-side component in the guest')

    async def extract_icon(self, spec: dict, size: int = 256, timeout: float = 30.0) -> dict[str, Any]:
        raise HostsideUnsupportedError('Windows icon extraction needs a component in the guest (class d)')

    # -- clock ------------------------------------------------------------------------

    async def get_timestamp(self, use_local: bool = False, timeout: float = 10.0) -> dict[str, Any]:
        """Host clock as the guest time (the guest RTC is seeded from the host); time zone from the image."""
        now = time.time()
        tz = self.session.guest_tz
        local = datetime.fromtimestamp(now, tz)
        offset = local.utcoffset()
        seconds = int(offset.total_seconds()) if offset else 0
        sign = '+' if seconds >= 0 else '-'
        tz_text = 'UTC' if seconds == 0 else f'{sign}{abs(seconds) // 3600:02d}:{abs(seconds) % 3600 // 60:02d}'
        result = {
            'timestamp': now,
            'timezone': tz_text,
            'iso_format': datetime.fromtimestamp(now, UTC).isoformat(),
            'source': 'host-clock',
        }
        if use_local:
            result['local_time'] = local.isoformat()
        return result

    # -- shell / files ------------------------------------------------------------------

    async def execute_shell(
        self,
        shell_command: str,
        cwd: str | None = None,
        env: dict | None = None,
        timeout: float | None = None,
        shell: bool = False,
        inherit_env: bool = True,
        admin: bool = False,
        websocket_timeout: float | None = None,
    ) -> dict[str, Any]:
        return self.session.handle_command(shell_command, shell=shell, admin=admin, cwd=cwd)

    async def pull_file_chunked(
        self, guest_path: str, host_path: Path, chunk_size: int = 1048576, progress_callback=None
    ) -> dict[str, Any]:
        self.session.defer_pull(guest_path, Path(host_path))
        return {
            'file_size': 0,
            'chunks_transferred': 0,
            'metadata': {'deferred': True, 'reason': 'extracted after quiesce'},
        }

    async def pull_multiple_files_chunked(self, files, *args, **kwargs) -> dict[str, Any]:
        for guest_path, host_path in files:
            self.session.defer_pull(guest_path, Path(host_path))
        return {'status': 'success', 'deferred': True}

    # -- tests / test infrastructure (all host-side) --------------------------------------

    async def upload_testfunctions(self, testfunctions_path: Path, specific_files=None) -> dict[str, Any]:
        return {'status': 'success', 'message': 'test functions run on the host; nothing uploaded'}

    async def install_testfunction_dependencies(self, dependencies: list[str]) -> dict[str, Any]:
        return {'status': 'success', 'message': 'test functions run on the host; nothing installed in the guest'}

    async def set_variables(self, variables: dict[str, Any]) -> dict[str, Any]:
        return {'status': 'success'}

    async def run_test(
        self, test_name: str, resolved_test_data: dict[str, Any], timeout: float = 130.0
    ) -> dict[str, Any]:
        raise HostsideUnsupportedError('run_test: host-side tests are evaluated by the HostsideTestExecutor')

    # -- system ---------------------------------------------------------------------------

    async def get_status(self) -> dict[str, Any]:
        return {'status': 'success', 'backend': 'hostside', 'agent': None}

    async def collect_system_info(self, timeout: float = 120.0) -> dict[str, Any]:
        raise HostsideUnsupportedError('system info is collected offline from the final image')

    async def get_filesystem_snapshot(self, root_path: str = '/', timeout: float = 660.0) -> dict[str, Any]:
        raise HostsideUnsupportedError(
            'in-guest `find` snapshots need a guest process; the host-side backend diffs base vs overlay offline (--diff)'
        )

    async def call_tool(self, tool, params: dict[str, Any] | None = None, timeout: float = 30.0) -> dict[str, Any]:
        name = getattr(tool, 'value', tool)
        handler = getattr(self, name, None)
        if handler is None or name.startswith('_'):
            raise HostsideUnsupportedError(f'tool {name!r} is not available in the host-side backend')
        return cast(dict[str, Any], await handler(**(params or {})))
