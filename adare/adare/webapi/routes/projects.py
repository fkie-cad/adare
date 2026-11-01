"""Project management endpoints."""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from adare.webapi.adapters import result_to_response

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
def list_projects():
    """List all registered projects."""
    result = _api().project.list_all()
    return result_to_response(result)


@router.get("/{path:path}")
def get_project(path: str):
    """Get a project by its filesystem path."""
    result = _api().project.get_by_path(Path(path))
    return result_to_response(result)


@router.post("")
def create_project(body: ProjectCreateBody):
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
def remove_project(name: str, path: str | None = None):
    """Remove a project by name (or by ``?path=``).

    The underlying service needs the project path. When *path* is not supplied it is
    resolved from the registered project with that *name*; an unknown name is a 404.
    """
    from adare.core.dto.project import ProjectRemoveRequest

    if path is None:
        listed = _api().project.list_all()
        if not listed.success:
            return result_to_response(listed)
        match = next((p for p in listed.data if p.name == name), None)
        if match is None:
            raise HTTPException(status_code=404, detail=f"Project '{name}' not found")
        path = str(match.path)

    dto = ProjectRemoveRequest(path=Path(path))
    result = _api().project.remove(dto)
    return result_to_response(result)
