"""Database and system management endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, Query

from adare.webapi.adapters import result_to_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/manage", tags=["manage"])


# ---- Helpers ----

def _api():
    from adare.api import AdareAPI
    return AdareAPI()


# ---- Database Endpoints ----

@router.get("/db-status")
async def get_db_status():
    """Check database system status."""
    result = _api().manage.get_db_status()
    return result_to_response(result)


@router.post("/init-db")
async def init_db():
    """Initialize the database system."""
    result = _api().manage.init_db()
    return result_to_response(result)


@router.post("/repair-db")
async def repair_db():
    """Repair the database system."""
    result = _api().manage.repair_db()
    return result_to_response(result)


@router.post("/reset-db")
async def reset_db():
    """Reset the database."""
    result = _api().manage.reset_db()
    return result_to_response(result)


@router.post("/clean-install-db")
async def clean_install_db(force: bool = Query(False)):
    """Perform a clean database installation."""
    result = _api().manage.clean_install_db(force=force)
    return result_to_response(result)


# ---- VM Management Endpoints ----

@router.post("/reset-all-vms")
async def reset_all_vms(force: bool = Query(False)):
    """Reset all VMs."""
    result = _api().manage.reset_all_vms(force=force)
    return result_to_response(result)


@router.post("/refresh-vm-runtime")
async def refresh_vm_runtime(project_path: Optional[str] = Query(None)):
    """Refresh VM runtime."""
    from pathlib import Path

    path = Path(project_path) if project_path else None
    result = _api().manage.refresh_vm_runtime(project_path=path)
    return result_to_response(result)


@router.post("/build-vm-runtime-wheels")
async def build_vm_runtime_wheels(project_path: Optional[str] = Query(None)):
    """Build VM runtime wheels."""
    from pathlib import Path

    path = Path(project_path) if project_path else None
    result = _api().manage.build_vm_runtime_wheels(project_path=path)
    return result_to_response(result)
