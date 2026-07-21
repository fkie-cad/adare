"""Synchronous QMP-driven internal (qcow2) snapshots for ``qemu:///session``.

On macOS / aarch64 the guest disk is attached via raw ``<qemu:commandline>`` and
is therefore *not* modelled as a libvirt ``<disk>``. ``virsh snapshot-create``
consequently sees zero disks and refuses ("too many disk snapshot requests"),
so libvirt external snapshots cannot work at all. QEMU's own savevm/loadvm
captures the full RAM+device state alongside a qcow2 internal snapshot instead.

We drive it over the ``-qmp`` unix socket QEMU exposes (adare's *runtime* QMP
goes through libvirt's separate monitor, so this socket is free) using the
async ``snapshot-save`` / ``snapshot-load`` / ``snapshot-delete`` jobs. The
device list is set explicitly to the guest disk node **only** — this excludes
the writable raw pflash (UEFI varstore) node, which is not snapshot-capable and
would otherwise abort a plain HMP ``savevm``.

Two host-side requirements make this work (see ``libvirt_xml_builder``):
  * the disk controller must be MIGRATABLE — virtio-blk-pci, not nvme (nvme is
    non-migratable and blocks the RAM/device state save);
  * everything else (edk2 pflash, virtio-gpu-pci resolution) is untouched.

A small JSON marker is written next to the memory path so restore/delete — which
receive only file paths, never the snapshot name — can recover the qcow2 tag.
"""
import json
import logging
import os
import re
import socket
import time

from adare.hypervisor.exceptions import HypervisorException

log = logging.getLogger(__name__)

_JOB_TIMEOUT = 180.0
_MARKER_BACKEND = 'qmp-internal'


def _job_id(prefix: str, tag: str) -> str:
    """QEMU job ids must be simple identifiers; sanitise the tag."""
    return f'{prefix}_{re.sub(r"[^A-Za-z0-9_]", "_", tag)}'


class _QMPClient:
    """Minimal blocking QMP client over a unix socket."""

    def __init__(self, socket_path: str, timeout: float = 30.0):
        try:
            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock.settimeout(timeout)
            self._sock.connect(socket_path)
            self._stream = self._sock.makefile('rwb')
            greeting = json.loads(self._stream.readline())
        except (OSError, ValueError) as e:
            raise HypervisorException(
                f"Cannot connect to QMP socket {socket_path}: {e}"
            ) from e
        if 'QMP' not in greeting:
            raise HypervisorException(f"Unexpected QMP greeting: {greeting}")
        self.execute('qmp_capabilities')

    def execute(self, command: str, **arguments) -> dict:
        obj: dict = {'execute': command}
        if arguments:
            obj['arguments'] = arguments
        try:
            self._stream.write((json.dumps(obj) + '\n').encode())
            self._stream.flush()
            while True:
                line = self._stream.readline()
                if not line:
                    raise HypervisorException("QMP connection closed unexpectedly")
                resp = json.loads(line)
                if 'return' in resp or 'error' in resp:
                    return resp
                # otherwise an async event — keep reading for the reply
        except (OSError, ValueError) as e:
            raise HypervisorException(f"QMP command '{command}' failed: {e}") from e

    def run_job(self, command: str, job_id: str, timeout: float = _JOB_TIMEOUT,
                **arguments) -> tuple[bool, str | None]:
        """Submit an async block job and wait for it to conclude."""
        resp = self.execute(command, **{'job-id': job_id, **arguments})
        if 'error' in resp:
            return False, resp['error'].get('desc', str(resp['error']))

        error: str | None = None
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = next(
                (j for j in self.execute('query-jobs').get('return', [])
                 if j.get('id') == job_id),
                None,
            )
            if job is None:
                error = f"job '{job_id}' vanished before concluding"
                break
            status = job.get('status')
            if status == 'concluded':
                error = job.get('error')
                break
            if status in ('aborting', 'null'):
                error = job.get('error') or f"job '{job_id}' aborted"
                break
            time.sleep(0.4)
        else:
            error = f"job '{job_id}' timed out after {timeout}s"

        self._dismiss(job_id)
        return (error is None), error

    def _dismiss(self, job_id: str) -> None:
        try:
            if any(j.get('id') == job_id
                   for j in self.execute('query-jobs').get('return', [])):
                self.execute('job-dismiss', id=job_id)
        except HypervisorException:
            pass  # best-effort cleanup; not worth masking the real result

    def close(self) -> None:
        try:
            self._stream.close()
            self._sock.close()
        except OSError:
            pass


def _find_disk_node(client: _QMPClient) -> str:
    """Return the node-name of the writable qcow2 guest disk (never pflash)."""
    for blk in client.execute('query-block').get('return', []):
        inserted = blk.get('inserted', {})
        qdev = blk.get('qdev') or ''
        if (inserted.get('drv') == 'qcow2' and not inserted.get('ro')
                and 'flash' not in qdev):
            node = inserted.get('node-name')
            if node:
                return node
    raise HypervisorException("No writable qcow2 guest disk node found via QMP")


def _write_marker(marker_paths: list[str], tag: str) -> None:
    # The internal snapshot lives inside the live overlay qcow2, so there are no
    # real external RAM/disk files. We drop the same JSON marker at every path
    # the caller recorded (memory + disk) so file-existence checks elsewhere
    # (e.g. the session restorer) do not treat the checkpoint as broken.
    payload = {'backend': _MARKER_BACKEND, 'tag': tag}
    for path in marker_paths:
        if path:
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh)


def read_marker_tag(memory_path: str) -> str | None:
    """Return the qcow2 tag recorded by :func:`create`, or None."""
    try:
        with open(memory_path, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if data.get('backend') == _MARKER_BACKEND:
        return data.get('tag')
    return None


def create(socket_path: str, tag: str, memory_path: str,
           disk_path: str | None = None) -> bool:
    """Create a live RAM+disk internal snapshot; record markers for later lookup."""
    client = _QMPClient(socket_path)
    try:
        node = _find_disk_node(client)
        # Idempotent: drop any stale snapshot with this tag first (ignore result).
        client.run_job('snapshot-delete', _job_id('del', tag), tag=tag, devices=[node])
        ok, err = client.run_job(
            'snapshot-save', _job_id('save', tag),
            tag=tag, vmstate=node, devices=[node],
        )
        if not ok:
            raise HypervisorException(f"snapshot-save failed: {err}")
        _write_marker([memory_path, disk_path], tag)
        log.info(f"Created internal QMP snapshot '{tag}' on node {node}")
        return True
    finally:
        client.close()


def restore(socket_path: str, memory_path: str) -> bool:
    """Load the internal snapshot named by the marker at memory_path (in place)."""
    tag = read_marker_tag(memory_path)
    if not tag:
        log.error(f"No QMP internal-snapshot marker at {memory_path}")
        return False
    client = _QMPClient(socket_path)
    try:
        node = _find_disk_node(client)
        ok, err = client.run_job(
            'snapshot-load', _job_id('load', tag),
            tag=tag, vmstate=node, devices=[node],
        )
        if not ok:
            raise HypervisorException(f"snapshot-load failed: {err}")
        # snapshot-load restores the run state captured at save time; make sure
        # the VM is running so the reactive GUI loop can keep screenshotting.
        if not client.execute('query-status').get('return', {}).get('running'):
            client.execute('cont')
        log.info(f"Restored internal QMP snapshot '{tag}' on node {node}")
        return True
    finally:
        client.close()


def delete(socket_path: str, memory_path: str, disk_path: str | None = None) -> bool:
    """Delete the internal snapshot named by the marker and remove the markers."""
    tag = read_marker_tag(memory_path) or read_marker_tag(disk_path or '')
    success = True
    if tag:
        try:
            client = _QMPClient(socket_path)
            try:
                node = _find_disk_node(client)
                ok, err = client.run_job(
                    'snapshot-delete', _job_id('del', tag), tag=tag, devices=[node],
                )
                if not ok:
                    log.warning(f"snapshot-delete for '{tag}' reported: {err}")
                    success = False
            finally:
                client.close()
        except HypervisorException as e:
            # VM may already be gone (session teardown); the ephemeral overlay
            # holding the snapshot is deleted anyway, so this is not fatal.
            log.warning(f"Could not delete QMP internal snapshot '{tag}': {e}")
            success = False
    for path in (memory_path, disk_path):
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError as e:
                log.warning(f"Failed to remove snapshot marker {path}: {e}")
                success = False
    return success
