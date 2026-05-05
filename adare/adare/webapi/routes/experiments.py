"""Experiment management endpoints."""
import logging
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel

from adare.webapi.adapters import result_to_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


# ---- Pydantic request models ----

class ExperimentCreateBody(BaseModel):
    """Request body for creating an experiment."""
    project_path: str
    name: str


class ExperimentCloneBody(BaseModel):
    """Request body for cloning an experiment."""
    project_path: str
    target_experiment: str
    environments: list[str] | None = None


class ExperimentRemoveBody(BaseModel):
    """Request body for removing an experiment."""
    project_path: str
    force: bool = False
    keep_files: bool = False


class ExperimentValidateBody(BaseModel):
    """Request body for validating an experiment."""
    project_path: str
    environment: str | None = None


class ExperimentEnvLinkBody(BaseModel):
    """Request body for adding/removing environments from an experiment."""
    project_path: str
    environments: list[str]
    force: bool = False


# ---- Helpers ----

def _api():
    from adare.api import AdareAPI
    return AdareAPI()


# ---- Endpoints ----

@router.get("")
async def list_experiments(tags: str | None = Query(None, description="Comma-separated tags to filter by")):
    """List all experiments, optionally filtered by tags."""
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    result = _api().show.list_experiments(tags=tag_list)
    return result_to_response(result)


@router.get("/{name}")
async def get_experiment(name: str):
    """Get experiment details by name."""
    result = _api().show.get_experiment(name=name)
    return result_to_response(result)


@router.post("")
async def create_experiment(body: ExperimentCreateBody):
    """Create a new experiment."""
    from adare.core.dto.experiment import ExperimentCreateRequest

    dto = ExperimentCreateRequest(
        project_path=Path(body.project_path),
        name=body.name,
    )
    result = _api().experiment.create(dto)
    return result_to_response(result)


@router.post("/{name}/clone")
async def clone_experiment(name: str, body: ExperimentCloneBody):
    """Clone an existing experiment."""
    from adare.core.dto.experiment import ExperimentCloneRequest

    dto = ExperimentCloneRequest(
        project_path=Path(body.project_path),
        source_experiment=name,
        target_experiment=body.target_experiment,
        environments=body.environments,
    )
    result = _api().experiment.clone(dto)
    return result_to_response(result)


@router.delete("/{name}")
async def remove_experiment(name: str, body: ExperimentRemoveBody):
    """Remove an experiment."""
    from adare.core.dto.experiment import ExperimentRemoveRequest

    dto = ExperimentRemoveRequest(
        project_path=Path(body.project_path),
        name=name,
        force=body.force,
        keep_files=body.keep_files,
    )
    result = _api().experiment.remove(dto)
    return result_to_response(result)


@router.post("/{name}/validate")
async def validate_experiment(name: str, body: ExperimentValidateBody):
    """Validate experiment configuration and integrity."""
    from adare.core.dto.experiment import ExperimentValidateRequest

    dto = ExperimentValidateRequest(
        project_path=Path(body.project_path),
        name=name,
        environment=body.environment,
    )
    result = _api().experiment.validate(dto)
    return result_to_response(result)


@router.post("/{name}/environments")
async def add_experiment_environments(name: str, body: ExperimentEnvLinkBody):
    """Link one or more environments to an experiment."""
    from adare.core.dto.experiment import ExperimentEnvModifyRequest

    dto = ExperimentEnvModifyRequest(
        project_path=Path(body.project_path),
        experiment_pattern=name,
        environments=body.environments,
        force=body.force,
    )
    result = _api().experiment.add_environments(dto)
    return result_to_response(result)


# DELETE with body: use api_route so FastAPI accepts the body parameter.
@router.api_route("/{name}/environments", methods=["DELETE"])
async def remove_experiment_environments(name: str, body: ExperimentEnvLinkBody):
    """Unlink one or more environments from an experiment."""
    from adare.core.dto.experiment import ExperimentEnvModifyRequest

    dto = ExperimentEnvModifyRequest(
        project_path=Path(body.project_path),
        experiment_pattern=name,
        environments=body.environments,
        force=body.force,
    )
    result = _api().experiment.remove_environments(dto)
    return result_to_response(result)
