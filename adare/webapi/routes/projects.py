"""Project management endpoints."""
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from adare.webapi.adapters import result_to_response, serialize_value

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])


# ---- Pydantic request models ----

class ProjectCreateBody(BaseModel):
    """Request body for creating a project."""
    name: str
    path: str
    description: str = ""


# ---- Helpers ----

def _api():
    from adare.api import AdareAPI
    return AdareAPI()


# ---- Endpoints ----

@router.get("")
async def list_projects():
    """List all registered projects."""
    result = _api().project.list_all()
    return result_to_response(result)


@router.get("/{path:path}")
async def get_project(path: str):
    """Get a project by its filesystem path."""
    result = _api().project.get_by_path(path)
    return result_to_response(result)


@router.post("")
async def create_project(body: ProjectCreateBody):
    """Create a new project."""
    from adare.core.dto.project import ProjectCreateRequest

    dto = ProjectCreateRequest(
        name=body.name,
        path=Path(body.path),
        description=body.description,
    )
    result = _api().project.create(dto)
    return result_to_response(result)


@router.delete("/{name}")
async def remove_project(name: str, path: str | None = None):
    """Remove a project by name.

    The underlying service requires the project path. If *path* is not supplied
    as a query parameter, we attempt to resolve it from the project name first.
    """
    from adare.core.dto.project import ProjectRemoveRequest

    if path is None:
        # Look up the project to get its path
        get_result = _api().project.get_by_path(name)
        if not get_result.success:
            raise HTTPException(status_code=404, detail=f"Project '{name}' not found")
        path = str(get_result.data.path) if hasattr(get_result.data, "path") else name

    dto = ProjectRemoveRequest(path=Path(path))
    result = _api().project.remove(dto)
    return result_to_response(result)
