"""Local VM management endpoints (database-tracked VMs, not VirtualSpice proxy)."""
import logging

from fastapi import APIRouter

from adare.webapi.adapters import result_to_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/local-vms", tags=["local-vms"])


# ---- Helpers ----

def _api():
    from adare.api import AdareAPI
    return AdareAPI()


# ---- Endpoints ----

@router.get("")
async def list_vms():
    """List all locally registered VMs."""
    result = _api().vm.list_all()
    return result_to_response(result)


@router.get("/{vm_id}")
async def get_vm(vm_id: str):
    """Get VM details by ID."""
    result = _api().vm.get_by_id(vm_id)
    return result_to_response(result)


@router.delete("/{vm_id}")
async def delete_vm(vm_id: str, force: bool = False):
    """Delete a VM by ID."""
    result = _api().vm.delete(vm_id, force=force)
    return result_to_response(result)
