"""Real-`qemu-img` overlay/flatten tests (T10) and the full Linux recipe flow (T16).

T10 uses a tiny real qcow2 and no boot at all, so it is fast; its point is the
one invariant a mock cannot check — that the flattened output has **no backing
file**. A flattened disk that still references its base would break the moment the
base cache is pruned, and nothing else in the suite would notice.

T16 is the load-bearing verification of the whole feature: a real QEMU boot, a
real guest agent, real `guest-exec`, a real clean shutdown and a real flatten,
against an Ubuntu guest that installs unattended in ~15 minutes. Once it passes,
Windows is only needed for Windows-*specific* behaviour.

T16 is marked `live_vm` and is therefore **deselected by default** — `addopts` in
both pyproject.toml files carries `-m "not live_vm"`. That is not a soft
convention: in practice it downloads and installs a 4 GB distro for ~30 minutes,
and it has been started by accident more than once simply by running the unit
suite. Opt in explicitly, and only on an idle host (ADARE's VM budget is one VM
at a time):

    pytest adare/tests/unit -m live_vm

Any command-line `-m` overrides the default, because argparse keeps the last `-m`
and addopts are prepended.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from adare.hypervisor.qemu.vm_creator.overlay import create_work_overlay, flatten_overlay

pytestmark = [pytest.mark.integration, pytest.mark.requires_qemu]


def _qemu_img() -> str:
    from adare.config import HYPERVISOR_CONFIGS
    return HYPERVISOR_CONFIGS['qemu']['qemu_img_exe']


def _info(disk: Path) -> dict:
    result = subprocess.run(
        [_qemu_img(), 'info', '--output=json', str(disk)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


@pytest.fixture(autouse=True)
def _require_qemu_img():
    from adare.config import HYPERVISOR_CONFIGS
    exe = HYPERVISOR_CONFIGS['qemu']['qemu_img_exe']
    if shutil.which(exe) is None:
        pytest.skip(f'{exe} not on PATH')


@pytest.fixture
def base_disk(tmp_path) -> Path:
    """A real 10 MB qcow2 with recognisable bytes written into it."""
    disk = tmp_path / 'base.qcow2'
    subprocess.run([_qemu_img(), 'create', '-f', 'qcow2', str(disk), '10M'],
                   capture_output=True, text=True, check=True)
    return disk


# --- T10 ---

def test_overlay_records_the_base_as_its_backing_file(base_disk, tmp_path):
    overlay = create_work_overlay(base_disk, tmp_path / 'work.qcow2')
    info = _info(overlay)
    assert Path(info['backing-filename']).resolve() == base_disk.resolve()


def test_backing_path_is_absolute(base_disk, tmp_path):
    """A relative backing path breaks as soon as the CWD differs."""
    nested = tmp_path / 'nested'
    nested.mkdir()
    overlay = create_work_overlay(base_disk, nested / 'work.qcow2')
    assert Path(_info(overlay)['backing-filename']).is_absolute()


def test_flattened_output_has_no_backing_file(base_disk, tmp_path):
    """THE invariant: the result must survive the base cache being pruned."""
    overlay = create_work_overlay(base_disk, tmp_path / 'work.qcow2')
    dest = tmp_path / 'flat.qcow2'
    flatten_overlay(overlay, dest, compress=False)
    assert 'backing-filename' not in _info(dest)


def test_flattened_output_has_no_backing_file_when_compressed(base_disk, tmp_path):
    overlay = create_work_overlay(base_disk, tmp_path / 'work.qcow2')
    dest = tmp_path / 'flat-zstd.qcow2'
    flatten_overlay(overlay, dest, compress=True)
    assert 'backing-filename' not in _info(dest)


def test_flattening_leaves_the_base_untouched(base_disk, tmp_path):
    before = base_disk.read_bytes()
    overlay = create_work_overlay(base_disk, tmp_path / 'work.qcow2')
    flatten_overlay(overlay, tmp_path / 'flat.qcow2', compress=False)
    assert base_disk.read_bytes() == before


def test_flattened_output_passes_qemu_img_check(base_disk, tmp_path):
    overlay = create_work_overlay(base_disk, tmp_path / 'work.qcow2')
    dest = tmp_path / 'flat.qcow2'
    flatten_overlay(overlay, dest, compress=True)
    subprocess.run([_qemu_img(), 'check', str(dest)],
                   capture_output=True, text=True, check=True)


def test_missing_base_disk_raises(tmp_path):
    from adare.hypervisor.exceptions import HypervisorException

    with pytest.raises(HypervisorException, match='Base disk not found'):
        create_work_overlay(tmp_path / 'absent.qcow2', tmp_path / 'work.qcow2')


# --- T16: the full recipe flow on a Linux guest ---

@pytest.mark.slow
@pytest.mark.live_vm
def test_full_recipe_flow_on_a_linux_guest(tmp_path, monkeypatch):
    """Build a provisioned `ubuntu2404` recipe end to end, for real.

    Exercises 100% of the new host-side machinery — Stage 1 install, base caching,
    overlay, boot, guest-agent readiness, per-step `guest-exec`, exit-code policy,
    `verify`, clean ACPI shutdown, flatten, register — on a guest that installs
    unattended. **No Windows involved.**

    Needs a matching Ubuntu ISO locally (any of the standard search locations) and
    roughly half an hour. Skipped otherwise.

    The profile is chosen to match the HOST architecture, so the guest runs under
    hardware acceleration. Cross-arch TCG would work but takes long enough to make
    the test useless in practice.
    """
    import yaml

    from adare.backend.vm.recipe import build_or_reuse_recipe_vm
    from adare.config.configdirectory import ISO_DIR, QEMU_CACHE_DIR
    from adare.hypervisor.qemu.accel import host_arch
    from adare.hypervisor.qemu.vm_creator.os_catalog import get_os_definition
    from adare.types.environment import parse_environment_file

    profile = 'ubuntu2404arm64' if host_arch() == 'aarch64' else 'ubuntu2404'
    os_def = get_os_definition(profile)

    # The arm64 profiles ship no iso_url (Ubuntu published no arm64 desktop ISO
    # for these releases), so the filename is not always in the catalog either.
    names = [name for name in (os_def.iso_filename,
                               'ubuntu-24.04.4-live-server-arm64.iso',
                               'ubuntu-24.04-live-server-amd64.iso') if name]
    candidates = [directory / name
                  for directory in (ISO_DIR, QEMU_CACHE_DIR) for name in names]
    iso = next((path for path in candidates if path.is_file()), None)
    if iso is None:
        pytest.skip(
            f'no {profile} ISO found; put one of {names} in {ISO_DIR} to run this test'
        )

    from adare.hypervisor.qemu.vm_creator.iso_utils import iso_sha256

    env_file = tmp_path / 'ubuntu-provisioned.yml'
    env_file.write_text(yaml.dump({
        'vm_type': 'recipe',
        'hypervisor': 'qemu',
        'description': 'T16: Ubuntu + build-time provisioning smoke test',
        'recipe': {
            'profile': profile,
            'iso': str(iso),
            'iso_sha256': iso_sha256(iso),
            # setup_level 1 (base) is the minimum that ships the guest agent, and
            # skips the Python environment we do not need here.
            'params': {'setup_level': 1, 'disk_size': '20G', 'ram_mb': 4096, 'cpus': 2},
            'provision': [
                {'name': 'install-jq',
                 'command': 'DEBIAN_FRONTEND=noninteractive apt-get install -y jq',
                 'timeout_minutes': 15,
                 # A package install asserting its own outcome is the whole
                 # command/verify contract in miniature.
                 'verify': 'jq --version'},
                {'name': 'record-provenance',
                 'command': 'jq --version > /var/log/adare-provisioned.txt'},
            ],
        },
        'os': {
            'os': os_def.display_name, 'platform': 'linux', 'distribution': 'ubuntu',
            'version': '24.04', 'language': 'English',
            'architecture': os_def.architecture,
        },
    }))

    metadata = parse_environment_file(env_file)
    result = build_or_reuse_recipe_vm(metadata, base_dir=env_file.parent)

    assert result['vm_id']

    # The registered disk must be standalone: a backing reference here would mean
    # the environment silently depends on a prunable cache entry.
    from adare.backend.vm import database as vm_database

    vm = vm_database.get_vm_by_id(result['vm_id'])
    assert vm is not None
    assert 'backing-filename' not in _info(Path(vm.file))
