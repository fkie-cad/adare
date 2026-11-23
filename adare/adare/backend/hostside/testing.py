"""Host-side ground-truth tests over a :class:`GuestFS`.

ADARE already has a host-mode test path (``GuestToHostTestExecutor``): pull the
file a test names to a local mirror, rewrite ``parameter.dst`` to the mirror and
run the unchanged test function on the host. Its transport is the QEMU guest
agent (a process in the guest). ``HostsideTestExecutor`` keeps the executor and
swaps the transport: the "pull" is a read from a :class:`GuestFS` (the offline
disk image, or the initial state), and the file-metadata probes (permissions,
timestamps) are inode reads, not ``stat`` run inside the guest.

Tests that need *live* state (``process_running``, ``system_service_status``,
registry, ...) cannot be answered from a disk image and are reported as such, not
guessed: they need the RAM-first :class:`~adare.backend.hostside.guestfs.LiveGuestFS`.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Any, cast

from adare.backend.experiment.guest_to_host_test_executor import GuestToHostTestExecutor
from adare.backend.experiment.host_services.guest_command_proxy import GuestClock
from adare.backend.hostside.guestfs import GuestFileNotFound, GuestFS, GuestFSError, GuestFSUnsupported, normalize
from adare.backend.testfunction.catalog import OFFLINE_PROBES  # QGA probes a disk image can answer
from adarelib.event.event import TestResult
from adarelib.testset.basictest import BasicTest, HostModeCategory
from adarelib.testset.testfunction import get_testclass_from_testfunction

log = logging.getLogger(__name__)


def _is_screen_test(function: str, testfunction_collection: dict) -> bool:
    """A ``visual.*`` function, or any function whose class runs against the live screen (HOST_NATIVE)."""
    if function.split('.', 1)[0] == 'visual':
        return True
    cls = get_testclass_from_testfunction(function, testfunction_collection)
    return bool(getattr(cls, 'host_mode_category', None) == HostModeCategory.HOST_NATIVE)


class GuestFSFileProxy:
    """The ``GuestFileProxy`` interface over a GuestFS: 'pull' = extract to a local mirror."""

    def __init__(self, fs: GuestFS):
        self.fs = fs
        self._temp_root = Path(tempfile.mkdtemp(prefix='adare_hostside_test_'))
        self._cache: dict[str, Path] = {}

    def _guest_path_to_local(self, guest_path: str) -> Path:
        return self._temp_root / normalize(guest_path).lstrip('/')

    async def pull_file(self, guest_path: str, force: bool = False) -> Path:
        if not force and guest_path in self._cache:
            return self._cache[guest_path]
        local = self._guest_path_to_local(guest_path)
        try:
            self.fs.extract(guest_path, local)
        except GuestFileNotFound as e:
            raise FileNotFoundError(f'{guest_path}: {e}') from e
        except GuestFSError as e:
            raise RuntimeError(f'cannot read {guest_path} from {self.fs.origin}: {e}') from e
        self._cache[guest_path] = local
        return local

    async def pull_directory(self, guest_path: str, force: bool = False) -> Path:
        return await self.pull_file(guest_path, force)

    async def resolve_guest_glob(self, pattern: str) -> list[str]:
        """Paths matching ``pattern``; a failed read raises ``RuntimeError`` (never looks like no match)."""
        try:
            return self.fs.glob(pattern)
        except GuestFileNotFound:
            return []
        except GuestFSError as e:
            raise RuntimeError(f'cannot list {pattern} in {self.fs.origin}: {e}') from e

    async def file_exists(self, guest_path: str) -> bool:
        return self.fs.exists(guest_path)

    async def path_kinds(self, pattern: str) -> list[tuple[str, str]]:
        """Existing paths matching ``pattern`` with kind ``file``/``dir``/``other``."""
        try:
            paths = self.fs.glob(pattern)
            return [(p, 'file' if self.fs.is_file(p) else 'dir' if self.fs.is_dir(p) else 'other') for p in paths]
        except GuestFSError as e:
            raise RuntimeError(f'cannot list {pattern} in {self.fs.origin}: {e}') from e

    def cleanup(self) -> None:
        shutil.rmtree(self._temp_root, ignore_errors=True)
        self._cache.clear()


class GuestFSCommandProxy:
    """The ``GuestCommandProxy`` interface, restricted to what an image can answer."""

    def __init__(self, fs: GuestFS, tz: tzinfo | None = None):
        self.fs = fs
        self.tz = tz

    async def get_file_permissions(self, guest_path: str) -> dict:
        try:
            st = self.fs.stat(guest_path)
        except GuestFileNotFound as e:
            raise FileNotFoundError(f'{guest_path} does not exist in {self.fs.origin}: {e}') from e
        return {
            'permissions': f'{st.permissions:o}',
            'owner': self.fs.name_of_uid(st.uid),
            'group': self.fs.name_of_gid(st.gid),
        }

    async def get_file_timestamps(self, guest_path: str) -> dict:
        try:
            st = self.fs.stat(guest_path)
        except GuestFileNotFound as e:
            raise FileNotFoundError(f'{guest_path} does not exist in {self.fs.origin}: {e}') from e
        return {'mtime': st.mtime, 'atime': st.atime, 'ctime': st.ctime}

    async def get_guest_clock(self) -> GuestClock:
        """No guest is running: the host clock (the guest RTC is seeded from it) in the image's time zone."""
        now = time.time()
        offset = datetime.fromtimestamp(now, self.tz).utcoffset() if self.tz is not None else None
        return GuestClock(now, int(offset.total_seconds()) if offset is not None else None)

    async def get_user_info(self, username: str) -> dict | None:
        """The ``/etc/passwd`` entry of ``username`` as ``{'uid', 'home'}``, or ``None`` if there is none."""
        try:
            passwd = self.fs.read_text('/etc/passwd')
        except GuestFSError:
            return None
        for line in passwd.splitlines():
            fields = line.split(':')
            if fields[0] == username and len(fields) >= 6 and fields[2].isdigit():
                return {'uid': int(fields[2]), 'home': fields[5]}
        return None

    async def user_exists(self, username: str) -> bool:
        return await self.get_user_info(username) is not None

    def __getattr__(self, name: str):
        async def unsupported(*args, **kwargs):
            raise GuestFSUnsupported(
                f'{name}: needs live guest state; a disk image cannot answer it (RAM-first LiveGuestFS not wired in)'
            )

        if name.startswith('_'):
            raise AttributeError(name)
        return unsupported


class HostsideTestExecutor(GuestToHostTestExecutor):
    """Runs the playbook's tests on the host against the GuestFS that matches each test's state point.

    ``session.fs_for_test(name)`` returns the GuestFS (initial: base + staged
    operations; final: the quiesced overlay) a test is evaluated against.
    """

    def __init__(self, session, testfunction_collection: dict):
        self.session = session
        self._proxies: dict[int, tuple[GuestFSFileProxy, GuestFSCommandProxy]] = {}
        super().__init__(
            guest_file=cast(Any, None), guest_command=cast(Any, None), testfunction_collection=testfunction_collection
        )

    def _bind(self, fs: GuestFS) -> None:
        proxies = self._proxies.get(id(fs))
        if proxies is None:
            proxies = (GuestFSFileProxy(fs), GuestFSCommandProxy(fs, getattr(self.session, 'guest_tz', None)))
            self._proxies[id(fs)] = proxies
        self.guest_file, self.guest_command = cast(Any, proxies)

    async def execute_test(self, test_name: str, test_function: str, test_instance: BasicTest) -> TestResult:
        try:
            fs = self.session.fs_for_test(test_name)
        except GuestFSError as e:
            return TestResult.execution_error(e, f"no guest filesystem available for '{test_name}': {e}")
        self._bind(fs)
        self.session.markers.marker(
            'adare.test.evaluate',
            test=test_name,
            function=test_function,
            state=self.session.state_of(test_name),
            fs=fs.consistency,
        )
        result = await super().execute_test(test_name, test_function, test_instance)
        status = getattr(result, 'status', None)
        self.session.markers.marker('adare.test.result', test=test_name, status=str(status))
        return result

    async def _execute_qga_probe_test(self, test_name, test_function, test_instance) -> TestResult:
        func = test_function.split('.')[-1]
        if func not in OFFLINE_PROBES:
            return TestResult.error(
                [f"'{func}' needs live guest state (process/service/registry); an offline image cannot answer it"]
            )
        return await super()._execute_qga_probe_test(test_name, test_function, test_instance)

    @staticmethod
    def validate_offline(playbook_tests: list, testfunction_collection: dict) -> list[str]:
        """Pre-flight: tests an offline image cannot evaluate (so the run fails before boot, not after)."""
        issues = []
        # visual tests read the live screen; hostside tests run after the VM is shut down, with none.
        # Recognised by name (a ``visual.exists`` does not resolve in the collection the way other
        # functions do) so the message says why, not "unknown test type".
        screen_tests = [
            t for t in playbook_tests if _is_screen_test(getattr(t, 'function', ''), testfunction_collection)
        ]
        for test in screen_tests:
            issues.append(
                f"Test '{getattr(test, 'name', '?')}' ({getattr(test, 'function', '')}) reads the live screen; the "
                f"hostside backend evaluates tests after shutdown, with no screen. Use --backend agent for visual tests."
            )
        others = [t for t in playbook_tests if t not in screen_tests]
        ok, base_issues = GuestToHostTestExecutor.validate_playbook_tests(others, testfunction_collection)
        if not ok:
            issues.extend(base_issues)
        for test in others:
            full = getattr(test, 'function', '')
            short = full.split('.', 1)[-1]
            # by collection.name: several collections share function names
            cls = get_testclass_from_testfunction(full, testfunction_collection)
            is_probe = getattr(cls, 'host_mode_category', None) == HostModeCategory.QGA_PROBE
            if is_probe and short not in OFFLINE_PROBES:
                issues.append(f"Test '{getattr(test, 'name', '?')}' ({full}) needs live guest state")
        return issues

    def cleanup(self) -> None:
        for file_proxy, _ in self._proxies.values():
            file_proxy.cleanup()
        self._proxies.clear()
