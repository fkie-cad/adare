"""VM instance and snapshot management endpoints (running VMs, not the
locally-registered VM images served by ``local_vms.py``)."""
import logging

from fastapi import APIRouter, Query

from adare.webapi.adapters import result_to_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vm-instances", tags=["vm-instances"])


# ---- Helpers ----

def _api():
    from adare.api import AdareAPI
    return AdareAPI()


# ---- Endpoints ----

@router.get("")
async def list_instances(vm_id: str | None = Query(None)):
    """List VM instances, optionally filtered by their source VM image."""
    result = _api().vm.list_instances(vm_id=vm_id)
    return result_to_response(result)


@router.get("/usage")
async def get_instance_usage():
    """Get aggregate VM instance usage (declared before ``/{instance_id}`` so
    the literal path isn't captured as an instance id)."""
    result = _api().vm.get_instance_usage()
    return result_to_response(result)


@router.get("/{instance_id}")
async def get_instance(instance_id: str):
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
async def list_snapshots(instance_id: str):
    """List snapshots for a VM instance."""
    result = _api().vm.list_snapshots(instance_id=instance_id)
    return result_to_response(result)


@router.delete("/{instance_id}/snapshots/{snapshot_name}")
async def delete_snapshot(instance_id: str, snapshot_name: str):
    """Delete a VM instance snapshot."""
    result = _api().vm.delete_snapshot(instance_id, snapshot_name)
    return result_to_response(result)
