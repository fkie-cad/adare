"""Environment management endpoints."""
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from adare.webapi.adapters import result_to_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/environments", tags=["environments"])


# ---- Pydantic request models ----

class EnvironmentCreateBody(BaseModel):
    """Request body for creating an environment.

    Two shapes: a baked template (`vm_path`) or a declarative recipe
    (`os_profile` + `iso_path`, plus optional build params) — see
    `EnvironmentCreateRequest.is_recipe`.
    """
    project_path: str
    name: str
    vm_path: str | None = None
    os_profile: str | None = None
    iso_path: str | None = None
    disk_size: str | None = None
    ram_mb: int | None = None
    cpus: int | None = None
    arch: str | None = None
    setup_level: int | None = None


class EnvironmentLoadBody(BaseModel):
    """Request body for loading an environment from YAML."""
    environment: str
    force: bool = False
    no_copy: bool = False


class EnvironmentVerifyBody(BaseModel):
    """Request body for verifying an environment by running the built-in
    verify_vm experiment against it."""
    project_path: str


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


@router.get("/os-profiles")
async def list_os_profiles():
    """List available OS profiles for building recipe environments.

    Registered ahead of `/{name}` so the literal "os-profiles" path segment
    isn't swallowed by that catch-all route.
    """
    result = _api().environment.list_os_profiles()
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

    iso_path = Path(body.iso_path) if body.iso_path else None
    if iso_path is not None and not iso_path.is_file():
        # EnvironmentService._create_recipe() hashes the ISO without an
        # existence check, so a bad path would otherwise surface as an
        # unhandled FileNotFoundError (500) instead of a clean 4xx here.
        raise HTTPException(
            status_code=400,
            detail=f"ISO path does not exist or is not a file: {iso_path}",
        )

    dto = EnvironmentCreateRequest(
        project_path=Path(body.project_path),
        name=body.name,
        vm_path=Path(body.vm_path) if body.vm_path else None,
        os_profile=body.os_profile,
        iso_path=iso_path,
        disk_size=body.disk_size,
        ram_mb=body.ram_mb,
        cpus=body.cpus,
        arch=body.arch,
        setup_level=body.setup_level,
    )
    result = _api().environment.create(dto)
    return result_to_response(result)


@router.post("/load")
async def load_environment(body: EnvironmentLoadBody):
    """Load an environment from YAML file."""
    from adare.core.dto.environment import EnvironmentLoadRequest

    dto = EnvironmentLoadRequest(
        environment=body.environment,
        force=body.force,
        no_copy=body.no_copy,
    )
    result = _api().environment.load(dto)
    return result_to_response(result)


@router.delete("/{name}")
async def delete_environment(name: str, force: bool = False):
    """Delete an environment by name or ULID."""
    result = _api().environment.delete(name, force=force)
    return result_to_response(result)


@router.post("/{name}/verify")
async def verify_environment(name: str, body: EnvironmentVerifyBody):
    """Register the built-in verify_vm experiment for this environment (if
    needed) and start a run. Returns the run ULID immediately so the UI can
    navigate to a run-detail page."""
    project_path = Path(body.project_path)
    api = _api()

    setup_result = api.experiment.ensure_verify_setup(project_path, name)
    if not setup_result.success:
        return result_to_response(setup_result)

    run_result = await api.experiment.run(project_path, setup_result.data, name)
    return result_to_response(run_result)
