"""Where the disk space under ADARE's directories goes.

Sizes are physical (allocated blocks), not apparent: qcow2 images are sparse,
and the apparent size of a 60 GiB disk says nothing about what it occupies.

Run and dev-session disks in ``~/.adare/qemu/disks`` are grouped by the VM
instance that owns them and classified the way ``adare vm prune`` does: a
group whose instance (or VM) has no database row is orphaned and reclaimable.
Walking the tree takes seconds on a full host, so the report is cached.
"""

import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from adare.config.configdirectory import APPDATA_DIR, ISO_DIR, QEMU_CACHE_DIR, QEMU_STATE_DIR, VMS_DIR

log = logging.getLogger(__name__)

CACHE_SECONDS = 300

# <instance>-base.qcow2, <instance>-nvram.fd, <instance>-overlay-<ulid>[.qcow2], <instance>-dev-...
_RUN_FILE = re.compile(r'^(?P<owner>.+?)-(?:base\.qcow2|nvram\.fd|overlay-.+|dev-.+)$')

_cache: tuple[float, 'StorageReport'] | None = None
_cache_lock = threading.Lock()


@dataclass
class StorageCategory:
    key: str
    label: str
    path: str
    bytes: int
    files: int


@dataclass
class DiskOwner:
    """The files of one VM instance in the QEMU disk directory."""

    name: str
    bytes: int
    files: int
    state: str  # 'running' | 'registered' | 'orphaned'
    instance_status: str | None = None  # VmInstance.status when registered


@dataclass
class ProjectStorage:
    name: str
    path: str
    bytes: int
    files: int


@dataclass
class StorageReport:
    computed_at: float
    categories: list[StorageCategory] = field(default_factory=list)
    disk_owners: list[DiskOwner] = field(default_factory=list)
    projects: list[ProjectStorage] = field(default_factory=list)

    @property
    def reclaimable_bytes(self) -> int:
        return sum(owner.bytes for owner in self.disk_owners if owner.state == 'orphaned')


def physical_size(path: Path) -> tuple[int, int]:
    """(allocated bytes, file count) of a file or directory tree; symlinks are not followed."""
    try:
        st = path.lstat()
    except OSError:
        return 0, 0
    if not path.is_dir() or path.is_symlink():
        return _allocated(st), 1
    total = files = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as e:
            log.debug(f'cannot list {current}: {e}')
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                else:
                    total += _allocated(entry.stat(follow_symlinks=False))
                    files += 1
            except OSError:
                continue
    return total, files


def _allocated(st: os.stat_result) -> int:
    blocks = getattr(st, 'st_blocks', None)
    return blocks * 512 if blocks is not None else st.st_size


def _categories(qemu_disk_dir: Path) -> list[StorageCategory]:
    """Top-level breakdown; every byte is counted once (the disk dir is excluded from 'other')."""
    named = [
        ('environment_disks', 'Environment disks', VMS_DIR),
        ('run_disks', 'Run & dev-session disks', qemu_disk_dir),
        ('templates', 'Converted templates', QEMU_STATE_DIR / 'templates'),
        ('caches', 'Download & build caches', QEMU_CACHE_DIR),
        ('isos', 'Installer ISOs', ISO_DIR),
    ]
    categories = []
    counted: set[Path] = set()
    for key, label, path in named:
        resolved = path.resolve()
        if resolved in counted:
            continue
        counted.add(resolved)
        size, files = physical_size(path)
        categories.append(StorageCategory(key, label, str(path), size, files))

    # Everything else under the appdata dirs, e.g. backups, logs, databases
    other_bytes = other_files = 0
    roots = [APPDATA_DIR.resolve()]
    if APPDATA_DIR.resolve() not in QEMU_STATE_DIR.resolve().parents:
        roots.append(QEMU_STATE_DIR.resolve())
    for root in roots:
        size, files = _uncounted(root, counted)
        other_bytes += size
        other_files += files
    categories.append(StorageCategory('other', 'Other ADARE data', str(APPDATA_DIR), other_bytes, other_files))
    return categories


def _uncounted(directory: Path, counted: set[Path]) -> tuple[int, int]:
    """Size of ``directory`` minus the already counted directories inside it."""
    if not directory.is_dir() or directory in counted:
        return 0, 0
    total = files = 0
    try:
        children = list(directory.iterdir())
    except OSError:
        return 0, 0
    for child in children:
        resolved = child if child.is_symlink() else child.resolve()
        if resolved in counted:
            continue
        if any(resolved in c.parents for c in counted):
            size, count = _uncounted(resolved, counted)
        else:
            size, count = physical_size(child)
        total += size
        files += count
    return total, files


def group_disk_owners(
    disk_dir: Path,
    running: set[str],
    registered: dict[str, str | None],
) -> list[DiskOwner]:
    """Group the QEMU disk directory by owning instance.

    Args:
        running: names of live QEMU processes
        registered: VM and instance names in the database -> instance status (None for VM names)
    """
    groups: dict[str, list[int]] = {}
    if disk_dir.is_dir():
        for child in disk_dir.iterdir():
            match = _RUN_FILE.match(child.name)
            owner = match['owner'] if match else child.name
            size, files = physical_size(child)
            entry = groups.setdefault(owner, [0, 0])
            entry[0] += size
            entry[1] += files
    owners = []
    for name, (size, files) in groups.items():
        if name in running:
            state = 'running'
        elif name in registered:
            state = 'registered'
        else:
            state = 'orphaned'
        owners.append(DiskOwner(name, size, files, state, registered.get(name)))
    owners.sort(key=lambda o: o.bytes, reverse=True)
    return owners


def _registered_names() -> dict[str, str | None]:
    from adare.database.api.vm import VmApi

    names: dict[str, str | None] = {}
    with VmApi() as api:
        for vm in api.get_all_vms():
            names[vm.name] = None
        for instance in api.get_all_vm_instances():
            names[instance.instance_name] = instance.status
    return names


def _project_storage() -> list[ProjectStorage]:
    from adare.database.api.project import ProjectDbApi

    with ProjectDbApi() as api:
        projects = [(p.name, p.path) for p in api.get_projects() if p.path]
    result = []
    for name, path in projects:
        size, files = physical_size(Path(path))
        result.append(ProjectStorage(name, path, size, files))
    result.sort(key=lambda p: p.bytes, reverse=True)
    return result


def compute_storage_report() -> StorageReport:
    from adare.backend.system.host import vm_processes
    from adare.hypervisor.qemu.mixins.configuration import get_qemu_disk_dir

    disk_dir = get_qemu_disk_dir()
    running = {vm.name for vm in vm_processes()}
    return StorageReport(
        computed_at=time.time(),
        categories=_categories(disk_dir),
        disk_owners=group_disk_owners(disk_dir, running, _registered_names()),
        projects=_project_storage(),
    )


def storage_report(refresh: bool = False) -> StorageReport:
    """The cached report, recomputed when older than :data:`CACHE_SECONDS` or on ``refresh``."""
    global _cache
    with _cache_lock:
        if not refresh and _cache is not None and time.time() - _cache[0] < CACHE_SECONDS:
            return _cache[1]
        report = compute_storage_report()
        _cache = (report.computed_at, report)
        return report
