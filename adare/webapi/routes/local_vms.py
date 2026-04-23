"""Local VM management endpoints (database-tracked VMs, not VirtualSpice proxy)."""
import logging
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel

from adare.webapi.adapters import result_to_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/local-vms", tags=["local-vms"])


# ---- Pydantic request models ----

class VmLoadBody(BaseModel):
    """Request body for loading a VM from file."""
    file_path: str
    name: str | None = None
    description: str = ""
    os_platform: str = ""
    os_type: str = ""
    os_distribution: str = ""
    os_version: str = ""
    os_language: str = ""
    os_architecture: str = "x86_64"
    force: bool = False


class VmTestOvaBody(BaseModel):
    """Request body for testing an OVA file."""
    ova_file_path: str
    guest_platform: str
    verbose: bool = False
    vm_cleanup_mode: str = "prompt"


# ---- Helpers ----

def _api():
    from adare.api import AdareAPI
    return AdareAPI()


# ---- VM Endpoints ----

@router.get("")
async def list_vms():
    """List all locally registered VMs."""
    result = _api().vm.list_all()
    return result_to_response(result)


@router.post("/load")
async def load_vm(body: VmLoadBody):
    """Load a VM from file."""
    from adare.core.dto.vm import VmLoadRequest

    dto = VmLoadRequest(
        file_path=Path(body.file_path),
        name=body.name,
        description=body.description,
        os_platform=body.os_platform,
        os_type=body.os_type,
        os_distribution=body.os_distribution,
        os_version=body.os_version,
        os_language=body.os_language,
        os_architecture=body.os_architecture,
        force=body.force,
    )
    result = _api().vm.load(dto)
    return result_to_response(result)


@router.delete("/clear")
async def clear_all_vms(force: bool = Query(False)):
    """Clear all VMs."""
    result = _api().vm.clear_all(force=force)
    return result_to_response(result)


@router.post("/test-ova")
async def test_ova(body: VmTestOvaBody):
    """Test OVA file compatibility with ADARE."""
    from adare.core.dto.vm import VmTestRequest

    dto = VmTestRequest(
        ova_file_path=Path(body.ova_file_path),
        guest_platform=body.guest_platform,
        verbose=body.verbose,
        vm_cleanup_mode=body.vm_cleanup_mode,
    )
    result = await _api().vm.test_ova(dto)
    return result_to_response(result)


@router.get("/instances")
async def list_instances(vm_id: str | None = Query(None)):
    """List VM instances, optionally filtered by VM ID."""
    result = _api().vm.list_instances(vm_id=vm_id)
    return result_to_response(result)


@router.get("/instances/usage")
async def get_instance_usage():
    """Get VM instance usage statistics."""
    result = _api().vm.get_instance_usage()
    return result_to_response(result)


@router.delete("/instances/stopped")
async def remove_all_stopped_instances():
    """Remove all stopped VM instances."""
    result = await _api().vm.remove_all_stopped_instances()
    return result_to_response(result)


@router.get("/instances/{instance_id}")
async def get_instance(instance_id: str):
    """Get VM instance details by ID."""
    result = _api().vm.get_instance_by_id(instance_id)
    return result_to_response(result)


@router.delete("/instances/{instance_id}")
async def remove_instance(instance_id: str):
    """Remove a VM instance."""
    result = await _api().vm.remove_instance(instance_id)
    return result_to_response(result)


@router.get("/snapshots")
async def list_snapshots(instance_id: str | None = Query(None)):
    """List VM snapshots, optionally filtered by instance ID."""
    result = _api().vm.list_snapshots(instance_id=instance_id)
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
