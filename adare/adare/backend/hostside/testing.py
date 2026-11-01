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
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, cast

from adare.backend.experiment.guest_to_host_test_executor import GuestToHostTestExecutor
from adare.backend.hostside.guestfs import GuestFileNotFound, GuestFS, GuestFSError, GuestFSUnsupported, normalize
from adarelib.event.event import TestResult
from adarelib.testset.basictest import BasicTest, HostModeCategory

log = logging.getLogger(__name__)

#: QGA-probe test functions a disk image can answer (the rest need live state)
OFFLINE_PROBES = frozenset({'file_permissions', 'file_timestamps', 'user_exists', 'log_entry_exists'})


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
        return self.fs.glob(pattern)

    async def file_exists(self, guest_path: str) -> bool:
        return self.fs.exists(guest_path)

    def cleanup(self) -> None:
        shutil.rmtree(self._temp_root, ignore_errors=True)
        self._cache.clear()


class GuestFSCommandProxy:
    """The ``GuestCommandProxy`` interface, restricted to what an image can answer."""

    def __init__(self, fs: GuestFS):
        self.fs = fs

    async def get_file_permissions(self, guest_path: str) -> dict:
        try:
            st = self.fs.stat(guest_path)
        except GuestFileNotFound:
            return {}
        return {
            'permissions': f'{st.permissions:o}',
            'owner': self.fs.name_of_uid(st.uid),
            'group': self.fs.name_of_gid(st.gid),
        }

    async def get_file_timestamps(self, guest_path: str) -> dict:
        try:
            st = self.fs.stat(guest_path)
        except GuestFileNotFound:
            return {}
        return {'mtime': st.mtime, 'atime': st.atime, 'ctime': st.ctime}

    async def user_exists(self, username: str) -> bool:
        try:
            passwd = self.fs.read_text('/etc/passwd')
        except GuestFSError:
            return False
        return any(line.split(':', 1)[0] == username for line in passwd.splitlines())

    async def search_log_file(self, log_path: str, pattern: str, max_lines: int = 1000) -> tuple[bool, list[str]]:
        try:
            text = self.fs.read_text(log_path)
        except GuestFSError:
            return False, []
        rx = re.compile(pattern)
        lines = [ln for ln in text.splitlines()[-max_lines:] if rx.search(ln)]
        return bool(lines), lines

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
            proxies = (GuestFSFileProxy(fs), GuestFSCommandProxy(fs))
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
        ok, base_issues = GuestToHostTestExecutor.validate_playbook_tests(playbook_tests, testfunction_collection)
        if not ok:
            issues.extend(base_issues)
        for test in playbook_tests:
            full = getattr(test, 'function', '')
            short = full.split('.', 1)[-1]
            cls = None
            for coll in testfunction_collection.values():
                if isinstance(coll, dict) and short in coll:
                    cls = coll[short]
                    break
            is_probe = cls is not None and getattr(cls, 'host_mode_category', None) == HostModeCategory.QGA_PROBE
            if is_probe and short not in OFFLINE_PROBES:
                issues.append(f"Test '{getattr(test, 'name', '?')}' ({full}) needs live guest state")
        return issues

    def cleanup(self) -> None:
        for file_proxy, _ in self._proxies.values():
            file_proxy.cleanup()
        self._proxies.clear()
