"""Live guest process list from the host, through the qemufile project (no guest involvement).

Thin bridge to qemufile's ``vmi-layer-b`` kernel-anchor walk: QMP ``stop`` + ``pmemsave`` of guest
RAM, then ``init_task -> tasks`` list walk with the profile of the guest's exact kernel build
(``vmi_profiles/``). The walk's one bootstrap input, the KVA of ``init_task``, is read from the
guest's own ``System.map`` on the *image* (valid when the guest kernel is not KASLR-randomised,
which is the case for this QEMU/EDK2 configuration: no EFI RNG; the walk verifies the anchor and
fails loudly otherwise).

The qemufile checkout is only imported (path: ``ADARE_QEMUFILE`` = the repository root, else a
checkout next to ADARE). Nothing in it is edited. Used by the host-side backend to prove, from
the host, which processes the guest ran: see ``HostsideSession.sample_processes``.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from adare.backend.hostside import disk
from adare.backend.hostside.markers import _candidate_paths

DEFAULT_PROFILE = '6.8.0-136-generic-arm64'
_SYMBOL = re.compile(r'^([0-9a-f]+) [A-Za-z] init_task$', re.M)


class VmiUnavailable(RuntimeError):
    """The qemufile VMI layer or a profile for this guest kernel is not available."""


def _qemufile_root() -> Path:
    env = os.environ.get('ADARE_QEMUFILE')
    if env:
        return Path(env)
    for src in _candidate_paths():  # <qemufile>/src candidates
        if (src.parent / 'vmi-layer-b').is_dir():
            return src.parent
    raise VmiUnavailable('qemufile checkout not found: set ADARE_QEMUFILE to its repository root')


def import_vmi(profile: str = DEFAULT_PROFILE):
    """Import qemufile's vmi modules for ``profile`` and return ``(QmpGuestMem, procwalk, offsets)``."""
    layer = _qemufile_root() / 'vmi-layer-b'
    if not (layer / 'vmi_procwalk.py').is_file():
        raise VmiUnavailable(f'{layer}/vmi_procwalk.py not found')
    os.environ.setdefault('VMI_ACTIVE_PROFILE', profile)
    if str(layer) not in sys.path:
        sys.path.insert(0, str(layer))
    try:
        import vmi_offsets
        import vmi_procwalk
        from vmi_guestmem import QmpGuestMem
    except (ImportError, RuntimeError, KeyError) as e:
        raise VmiUnavailable(f'cannot import the qemufile VMI layer for profile {profile}: {e}') from e
    return QmpGuestMem, vmi_procwalk, vmi_offsets


def init_task_from_system_map(image: Path, release: str) -> int:
    """KVA of ``init_task`` from ``System.map-<release>`` on any ext volume of the image (usually /boot)."""
    import dissect.extfs as extfs

    stream = disk.open_disk_stream(image)
    try:
        for _name, fs in disk.open_ext_filesystems(stream):
            for candidate in (f'/System.map-{release}', f'/boot/System.map-{release}'):
                try:
                    text = fs.get(candidate).open().read().decode('ascii', 'replace')
                except (extfs.Error, OSError, ValueError, KeyError):
                    continue
                m = _SYMBOL.search(text)
                if m:
                    return int(m.group(1), 16)
    finally:
        stream.close()
    raise VmiUnavailable(f'init_task not found in System.map-{release} on {image}')


def list_processes(qmp_socket: str, image: Path, profile: str = DEFAULT_PROFILE) -> dict[str, Any]:
    """Pause the guest, dump RAM, walk the task list, resume. Returns processes and the pause cost."""
    QmpGuestMem, procwalk, offsets = import_vmi(profile)
    release = getattr(offsets, 'KERNEL_RELEASE', profile.split('-arm64')[0])
    anchor = init_task_from_system_map(image, release)
    from vmi_arch import ACTIVE_ARCH  # imported by the qemufile modules above

    mem = QmpGuestMem(qmp_socket, qemu_cwd='/', dump_relpath=f'tmp/adare-hostside-{os.getpid()}.bin')
    started = time.monotonic()
    tasks: list[dict[str, Any]] = []
    try:
        mem.stop_at_el1(log=lambda *_: None)
        mem.configure_kva_translation(memstart_addr=ACTIVE_ARCH.RAM_BASE)
        mem.verify_kva_translation([anchor], log=lambda *_: None)
        mem.snapshot(log=lambda *_: None)
        for kva in procwalk.iter_tasks(mem, anchor):
            fields = procwalk._task_fields(procwalk._read_task_struct(mem, kva))  # noqa: SLF001
            tasks.append(
                {'pid': fields['pid'], 'tgid': fields['tgid'], 'comm': fields['comm'], 'kthread': not fields['mm_kva']}
            )
    finally:
        mem.cont()
        stats = mem.stats()
        mem.close()
        dump = Path('/tmp') / f'adare-hostside-{os.getpid()}.bin'
        dump.unlink(missing_ok=True)
    return {
        'method': 'qemufile vmi_procwalk.iter_tasks (QMP stop + pmemsave + kernel-anchor walk)',
        'profile': profile,
        'init_task_kva': hex(anchor),
        'intervention_span_s': round(stats.get('intervention_span_s') or (time.monotonic() - started), 3),
        'processes': tasks,
    }
