"""Environment management endpoints."""
import logging
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from adare.webapi.adapters import result_to_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/environments", tags=["environments"])


# ---- Pydantic request models ----

class EnvironmentCreateBody(BaseModel):
    """Request body for creating an environment."""
    project_path: str
    name: str
    vm_path: str | None = None


# ---- Helpers ----

def _api():
    from adare.api import AdareAPI
    return AdareAPI()


# ---- Endpoints ----

@router.get("")
async def list_environments():
    """List all environments."""
    result = _api().show.list_environments()
    return result_to_response(result)


@router.get("/{name}")
async def get_environment(name: str):
    """Get environment details by name."""
    result = _api().show.get_environment(name)
    return result_to_response(result)


@router.post("")
async def create_environment(body: EnvironmentCreateBody):
    """Create a new environment template."""
    from adare.core.dto.environment import EnvironmentCreateRequest

    dto = EnvironmentCreateRequest(
        project_path=Path(body.project_path),
        name=body.name,
        vm_path=Path(body.vm_path) if body.vm_path else None,
    )
    result = _api().environment.create(dto)
    return result_to_response(result)


@router.delete("/{name}")
async def delete_environment(name: str, force: bool = False):
    """Delete an environment by name or ULID."""
    result = _api().environment.delete(name, force=force)
    return result_to_response(result)
