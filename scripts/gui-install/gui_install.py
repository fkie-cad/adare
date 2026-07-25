#!/usr/bin/env python3
"""Replay a GUI-installer playbook headlessly — no LLM, fully deterministic.

Boots an installer ISO in QEMU (headless, with a QMP socket), replays a YAML
playbook of keyboard/mouse/wait steps to click through the graphical installer,
then reboots from the freshly installed disk and (optionally) verifies login.

This is the reusable, reproducible form of a hand-driven GUI install: the same
playbook always produces the same VM, on any machine with QEMU + KVM, with no
vision model in the loop. Add a new install by writing a new playbook YAML —
see playbooks/ and README.md.

Example:
  ./gui_install.py playbooks/ubuntu2004-desktop.yaml \\
      --iso /path/ubuntu-20.04.6-desktop-amd64.iso \\
      --vm-dir /vms --out /tmp/run2004

Requires: qemu-system-x86_64, qemu-img, python3, PyYAML. KVM strongly recommended.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qmp_drive import QMP  # noqa: E402

_OVMF_CANDIDATES = [
    '/usr/share/OVMF/OVMF_CODE.fd',
    '/usr/share/edk2-ovmf/x64/OVMF_CODE.fd',
    '/usr/share/qemu/OVMF.fd',
]
_OVMF_VARS = [
    '/usr/share/OVMF/OVMF_VARS.fd',
    '/usr/share/edk2-ovmf/x64/OVMF_VARS.fd',
]


def _find(paths):
    return next((p for p in paths if Path(p).is_file()), None)


def build_qemu_cmd(disk, iso, sock, serial_log, vm, nvram=None):
    """Assemble the qemu-system-x86_64 command line."""
    cmd = [
        'qemu-system-x86_64',
        '-machine', 'pc,accel=kvm:tcg',
        '-cpu', 'host',
        '-m', str(vm['ram_mb']),
        '-smp', str(vm['cpus']),
        '-drive', f'file={disk},format=qcow2,if=virtio,cache=writeback',
        '-vga', vm.get('vga', 'qxl'),
        '-usb', '-device', 'usb-tablet',
        '-netdev', 'user,id=n0', '-device', 'virtio-net-pci,netdev=n0',
        '-qmp', f'unix:{sock},server,nowait',
        '-serial', f'file:{serial_log}',
        '-display', 'none',
    ]
    if iso:
        cmd += ['-cdrom', str(iso), '-boot', 'd']
    if vm.get('firmware') == 'uefi' and nvram:
        code = _find(_OVMF_CANDIDATES)
        if not code:
            raise SystemExit('firmware: uefi requested but no OVMF_CODE.fd found')
        cmd[1:1] = [
            '-drive', f'if=pflash,format=raw,readonly=on,file={code}',
            '-drive', f'if=pflash,format=raw,file={nvram}',
        ]
    return cmd


def run_steps(q: QMP, steps, outdir: Path, w=1024, h=768):
    """Execute a list of playbook step dicts against the guest."""
    for i, step in enumerate(steps):
        action = step['action']
        note = step.get('note', '')
        repeat = int(step.get('repeat', 1))
        label = f'[{i:02d}] {action}' + (f' x{repeat}' if repeat > 1 else '')
        print(f'  {label:<22} {note}', flush=True)
        for _ in range(repeat):
            if action == 'key':
                q.key(step['keys'], shift=step.get('shift', False))
            elif action == 'type':
                q.type_text(step['text'])
            elif action == 'tap':
                q.tap(*step['coords'])
            elif action == 'wait':
                time.sleep(float(step['seconds']))
            elif action == 'wait_stable':
                ok = q.wait_stable(settle=float(step.get('settle', 20)),
                                   timeout=float(step.get('timeout', 600)),
                                   poll=float(step.get('poll', 3)),
                                   min_elapsed=float(step.get('min', 0)))
                if not ok:
                    print(f'    ! wait_stable timed out ({note or action})', flush=True)
            elif action == 'shot':
                pass  # handled below
            else:
                raise SystemExit(f'unknown step action: {action!r}')
            if action in ('key', 'tap'):
                time.sleep(float(step.get('pause', 0.4)))
        name = step.get('shot')
        if action == 'shot':
            name = name or step.get('name') or f'step{i:02d}'
        if name:
            path = q.shot(str(outdir / f'{i:02d}_{name}.png'))
            print(f'    shot -> {path}', flush=True)


def launch(cmd):
    print('  $ ' + ' '.join(cmd), flush=True)
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def stop(proc, sock):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
    if Path(sock).exists():
        Path(sock).unlink()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('playbook', type=Path)
    ap.add_argument('--iso', type=Path, required=True, help='installer ISO')
    ap.add_argument('--disk', type=Path, help='qcow2 path (default: <vm-dir>/<name>.qcow2)')
    ap.add_argument('--vm-dir', type=Path, default=Path.cwd(), help='dir for the disk image')
    ap.add_argument('--disk-size', help='override playbook disk size (e.g. 60G)')
    ap.add_argument('--ram', type=int, help='override RAM (MB)')
    ap.add_argument('--cpus', type=int, help='override vCPU count')
    ap.add_argument('--out', type=Path, help='screenshot output dir (default: ./<name>-run)')
    ap.add_argument('--sock', default='/tmp/gui-install/qmp.sock')
    ap.add_argument('--force', action='store_true', help='overwrite an existing disk')
    ap.add_argument('--keep-running', action='store_true', help='leave the VM booted at the end')
    ap.add_argument('--no-verify', action='store_true', help='skip the post-install login check')
    a = ap.parse_args()

    pb = yaml.safe_load(a.playbook.read_text())
    name = pb['name']
    vm = dict(pb.get('vm', {}))
    vm.setdefault('ram_mb', 4096); vm.setdefault('cpus', 4)
    vm.setdefault('disk_size', '60G'); vm.setdefault('vga', 'qxl')
    if a.ram: vm['ram_mb'] = a.ram
    if a.cpus: vm['cpus'] = a.cpus
    if a.disk_size: vm['disk_size'] = a.disk_size

    if not a.iso.is_file():
        raise SystemExit(f'ISO not found: {a.iso}')
    disk = a.disk or (a.vm_dir / f'{name}.qcow2')
    disk.parent.mkdir(parents=True, exist_ok=True)
    outdir = a.out or Path.cwd() / f'{name}-run'
    outdir.mkdir(parents=True, exist_ok=True)
    Path(a.sock).parent.mkdir(parents=True, exist_ok=True)

    # fresh disk
    if disk.exists() and not a.force:
        raise SystemExit(f'{disk} exists — pass --force to overwrite')
    if disk.exists():
        disk.unlink()
    subprocess.run(['qemu-img', 'create', '-f', 'qcow2', str(disk), vm['disk_size']],
                   check=True, stdout=subprocess.DEVNULL)
    nvram = None
    if vm.get('firmware') == 'uefi':
        nvram = disk.parent / f'{name}_VARS.fd'
        src = _find(_OVMF_VARS)
        if src:
            shutil.copy2(src, nvram)

    serial = disk.parent / f'{name}_install.log'
    if Path(a.sock).exists():
        Path(a.sock).unlink()

    print(f'== {name}: booting installer ==', flush=True)
    proc = launch(build_qemu_cmd(disk, a.iso, a.sock, serial, vm, nvram))
    q = None
    try:
        q = QMP(a.sock)
        print('== driving installer ==', flush=True)
        run_steps(q, pb.get('install', []), outdir)
        q.close(); q = None

        if pb.get('reboot_from_disk') and not a.keep_running:
            print('== rebooting from installed disk ==', flush=True)
            stop(proc, a.sock)
            proc = launch(build_qemu_cmd(disk, None, a.sock, serial, vm, nvram))
            q = QMP(a.sock)
            if not a.no_verify:
                print('== verifying installed system ==', flush=True)
                run_steps(q, pb.get('verify', []), outdir)
    finally:
        if q:
            if not a.keep_running:
                try:
                    q.powerdown()
                    for _ in range(30):
                        if proc.poll() is not None:
                            break
                        time.sleep(2)
                except (RuntimeError, OSError):
                    pass
            q.close()
        if not a.keep_running:
            stop(proc, a.sock)

    print(f'\n== done ==\n  disk:        {disk}\n  screenshots: {outdir}\n'
          f'  credentials: {pb.get("credentials", "see playbook")}', flush=True)


if __name__ == '__main__':
    main()
