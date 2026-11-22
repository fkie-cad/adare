"""VM instance and snapshot management endpoints (running VMs, not the
locally-registered VM images served by ``local_vms.py``)."""

import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from adare.webapi.adapters import result_to_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vm-instances", tags=["vm-instances"])


# ---- Helpers ----


def _api():
    from adare.api import AdareAPI

    return AdareAPI()


# Live log tail: first poll (no offset) returns at most this much of the file's end,
# later polls at most this much new data each.
_LOG_TAIL_BYTES = 64 * 1024
_LOG_CHUNK_MAX_BYTES = 1024 * 1024


def _libvirt_log_candidates(instance_name: str) -> list[Path]:
    """Where libvirt writes a QEMU domain's own log (``qemu:///session`` and ``qemu:///system``)."""
    return [
        Path.home() / ".cache" / "libvirt" / "qemu" / "log" / f"{instance_name}.log",
        Path("/var/log/libvirt/qemu") / f"{instance_name}.log",
    ]


def _instance_log_sources(instance_id: str) -> dict[str, Path]:
    """The log files a VM instance can be watched through, as ``key -> path``.

    ``run/<file>`` are the ``logs/*.log`` of the run holding the instance (adare, guest
    agent, serial console, QEMU debug, ...); ``libvirt`` is the hypervisor's domain log.
    Files are listed only once they exist, so polling the listing picks up late ones.

    Raises:
        HTTPException: 404 when the instance does not exist.
    """
    from adare.webapi.routes.runs import _resolve_run_dir

    result = _api().vm.get_instance_by_id(instance_id)
    if not result.success or result.data is None:
        raise HTTPException(status_code=404, detail="VM instance not found")
    instance = result.data

    sources: dict[str, Path] = {}
    if instance.current_experiment_run_id:
        run_dir = _resolve_run_dir(instance.current_experiment_run_id)
        if run_dir is not None:
            log_dir = run_dir / "logs"
            if log_dir.is_dir():
                for entry in sorted(log_dir.glob("*.log")):
                    if entry.is_file():
                        sources[f"run/{entry.name}"] = entry
    for candidate in _libvirt_log_candidates(instance.instance_name):
        if candidate.is_file() and os.access(candidate, os.R_OK):
            sources["libvirt"] = candidate
            break
    return sources


# ---- Endpoints ----


@router.get("")
def list_instances(vm_id: str | None = Query(None)):
    """List VM instances, optionally filtered by their source VM image."""
    result = _api().vm.list_instances(vm_id=vm_id)
    return result_to_response(result)


@router.get("/usage")
def get_instance_usage():
    """Get aggregate VM instance usage (declared before ``/{instance_id}`` so
    the literal path isn't captured as an instance id)."""
    result = _api().vm.get_instance_usage()
    return result_to_response(result)


@router.get("/{instance_id}")
def get_instance(instance_id: str):
    """Get a VM instance by ID."""
    result = _api().vm.get_instance_by_id(instance_id)
    return result_to_response(result)


@router.delete("/{instance_id}")
async def remove_instance(instance_id: str):
    """Remove a VM instance."""
    result = await _api().vm.remove_instance(instance_id)
    return result_to_response(result)


@router.delete("")
async def remove_all_stopped_instances():
    """Remove all stopped VM instances."""
    result = await _api().vm.remove_all_stopped_instances()
    return result_to_response(result)


@router.get("/{instance_id}/snapshots")
def list_snapshots(instance_id: str):
    """List snapshots for a VM instance."""
    result = _api().vm.list_snapshots(instance_id=instance_id)
    return result_to_response(result)


@router.delete("/{instance_id}/snapshots/{snapshot_name}")
def delete_snapshot(instance_id: str, snapshot_name: str):
    """Delete a VM instance snapshot."""
    result = _api().vm.delete_snapshot(instance_id, snapshot_name)
    return result_to_response(result)


@router.get("/{instance_id}/logs")
def list_instance_logs(instance_id: str):
    """List the log files a running instance can be tailed through (see ``_instance_log_sources``)."""
    sources = _instance_log_sources(instance_id)
    data = [{"key": key, "name": path.name, "size": path.stat().st_size} for key, path in sources.items()]
    return {"success": True, "data": data}


@router.get("/{instance_id}/logs/{source:path}")
def read_instance_log(instance_id: str, source: str, offset: int | None = Query(None, ge=0)):
    """Read a chunk of one of an instance's logs, for polling it live.

    Without ``offset`` the call returns the end of the file (at most 64 KiB); pass the
    returned ``next_offset`` to get only what was appended since. If the file got shorter
    than ``offset`` (truncated or replaced) the read starts over from its end and
    ``reset`` is true, so the client drops what it shows. A chunk that stops before the end
    of the file is cut at its last newline so no line, or UTF-8 character, is split.
    """
    sources = _instance_log_sources(instance_id)
    path = sources.get(source)
    if path is None:
        raise HTTPException(status_code=404, detail="log not found")

    try:
        with path.open("rb") as fh:
            size = os.fstat(fh.fileno()).st_size
            reset = offset is not None and offset > size
            start = max(0, size - _LOG_TAIL_BYTES) if offset is None or reset else offset
            fh.seek(start)
            chunk = fh.read(min(size - start, _LOG_CHUNK_MAX_BYTES))
    except OSError as e:
        raise HTTPException(status_code=404, detail=f"log not readable: {e}") from e

    if start + len(chunk) < size:
        cut = chunk.rfind(b"\n")
        if cut >= 0:
            chunk = chunk[: cut + 1]
    if start > 0 and (offset is None or reset):
        # A tail starts mid-file: drop the partial first line.
        first = chunk.find(b"\n")
        if first >= 0:
            start += first + 1
            chunk = chunk[first + 1 :]

    return {
        "success": True,
        "data": {
            "text": chunk.decode("utf-8", errors="replace"),
            "offset": start,
            "next_offset": start + len(chunk),
            "size": size,
            "reset": reset,
        },
    }
