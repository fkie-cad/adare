"""Per-run QEMU resources: template disk, per-run vTPM copies, and run-file removal."""

import json
import subprocess
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from adare.hypervisor.qemu import run_resources
from adare.hypervisor.qemu.mixins.configuration import _ADARE_VM_UUID_NAMESPACE

pytestmark = pytest.mark.unit


@pytest.fixture
def qemu_state(tmp_path, monkeypatch):
    """Point every run-resource location at tmp_path."""
    disks, vms, run = tmp_path / 'disks', tmp_path / 'vms', tmp_path / 'run'
    for d in (disks, vms, run):
        d.mkdir()
    monkeypatch.setattr(run_resources, 'get_qemu_disk_dir', lambda: disks)
    monkeypatch.setattr(run_resources, 'get_qemu_vm_config_dir', lambda: vms)
    monkeypatch.setattr(run_resources, 'get_qemu_runtime_dir', lambda: run)
    monkeypatch.setattr(run_resources, 'TEMPLATE_DISK_DIR', tmp_path / 'templates')
    monkeypatch.setattr(run_resources, 'TPM_TEMPLATE_DIR', tmp_path / 'tpm-templates')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    return tmp_path


def _qemu_img(fmt: str):
    """Fake subprocess.run for qemu-img: `info` reports ``fmt``, `convert` writes the target."""

    def run(args, **kwargs):
        if args[1] == 'info':
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps({'format': fmt}), stderr='')
        if args[1] == 'convert':
            Path(args[-1]).write_bytes(b'qcow2')
            return subprocess.CompletedProcess(args, 0, stdout='', stderr='')
        raise AssertionError(args)

    return run


class TestTemplateDisk:
    def test_qcow2_disk_is_its_own_template(self, qemu_state, tmp_path):
        disk = tmp_path / 'ubuntu.qcow2'
        disk.write_bytes(b'x')
        with patch.object(run_resources.subprocess, 'run', side_effect=_qemu_img('qcow2')) as run:
            assert run_resources.resolve_template_disk(disk, 'a' * 64, 'qemu-img') == disk
        assert [c.args[0][1] for c in run.call_args_list] == ['info']

    def test_other_formats_are_converted_once_keyed_by_content_hash(self, qemu_state, tmp_path):
        disk = tmp_path / 'win.vmdk'
        disk.write_bytes(b'x')
        with patch.object(run_resources.subprocess, 'run', side_effect=_qemu_img('vmdk')) as run:
            first = run_resources.resolve_template_disk(disk, 'b' * 64, 'qemu-img')
            second = run_resources.resolve_template_disk(disk, 'b' * 64, 'qemu-img')

        assert first == second == qemu_state / 'templates' / f"{'b' * 16}.qcow2"
        assert [c.args[0][1] for c in run.call_args_list].count('convert') == 1


class TestRunTpm:
    def _manufacture(self, args, **kwargs):
        (Path(args[args.index('--tpmstate') + 1]) / 'tpm2-00.permall').write_bytes(b'fresh-ek')
        return subprocess.CompletedProcess(args, 0, stdout='', stderr='')

    def test_each_run_boots_its_own_copy_of_one_template(self, qemu_state):
        with patch.object(run_resources.subprocess, 'run', side_effect=self._manufacture) as run:
            run_resources.seed_run_tpm('vm1', 'run-a')
            run_resources.seed_run_tpm('vm1', 'run-b')

        assert run.call_count == 1  # manufactured once
        root = run_resources.swtpm_state_root()
        a, b = root / 'run-a' / 'tpm2' / 'tpm2-00.permall', root / 'run-b' / 'tpm2' / 'tpm2-00.permall'
        assert a.read_bytes() == b.read_bytes() == b'fresh-ek'
        a.write_bytes(b'run-a changed its tpm')
        assert (qemu_state / 'tpm-templates' / 'vm1' / 'tpm2' / 'tpm2-00.permall').read_bytes() == b'fresh-ek'

    def test_previously_shared_vtpm_is_adopted_not_replaced(self, qemu_state):
        legacy = run_resources.swtpm_state_root() / str(uuid.uuid5(_ADARE_VM_UUID_NAMESPACE, 'vm1')) / 'tpm2'
        legacy.mkdir(parents=True)
        (legacy / 'tpm2-00.permall').write_bytes(b'existing-ek')
        (legacy / '.lock').write_bytes(b'')

        with patch.object(run_resources.subprocess, 'run') as run:
            run_resources.seed_run_tpm('vm1', 'run-a')

        run.assert_not_called()
        seeded = run_resources.swtpm_state_root() / 'run-a' / 'tpm2'
        assert (seeded / 'tpm2-00.permall').read_bytes() == b'existing-ek'
        assert not (seeded / '.lock').exists()


class TestRemoveRunFiles:
    def test_removes_only_files_of_that_run(self, qemu_state):
        disks, vms, run = qemu_state / 'disks', qemu_state / 'vms', qemu_state / 'run'
        mine = 'ubuntu_run_AAAAAAAA'
        other = 'ubuntu_run_BBBBBBBB'
        (vms / f'{mine}.json').write_text(json.dumps({'uuid': 'uuid-mine'}))
        (vms / f'{other}.json').write_text(json.dumps({'uuid': 'uuid-other'}))
        for name in (mine, other):
            (disks / f'{name}-overlay-01RUN.qcow2').write_bytes(b'')
            (disks / f'{name}-nvram.fd').write_bytes(b'')
            (run / f'{name}.qmp').write_bytes(b'')
        (disks / f'{mine}-overlay-01RUN' / 'snapshots').mkdir(parents=True)
        template = disks / 'ubuntu.qcow2'
        template.write_bytes(b'template')
        tpm_root = run_resources.swtpm_state_root()
        for u in ('uuid-mine', 'uuid-other'):
            (tpm_root / u / 'tpm2').mkdir(parents=True)

        run_resources.remove_run_files(mine)

        assert sorted(p.name for p in disks.iterdir()) == sorted(
            ['ubuntu.qcow2', f'{other}-overlay-01RUN.qcow2', f'{other}-nvram.fd']
        )
        assert [p.name for p in vms.iterdir()] == [f'{other}.json']
        assert [p.name for p in run.iterdir()] == [f'{other}.qmp']
        assert [p.name for p in tpm_root.iterdir()] == ['uuid-other']
