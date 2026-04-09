"""Run management endpoints."""
import logging
from typing import Optional

from fastapi import APIRouter, Query

from adare.webapi.adapters import result_to_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runs", tags=["runs"])


# ---- Helpers ----

def _api():
    from adare.api import AdareAPI
    return AdareAPI()


# ---- Endpoints ----

@router.get("")
async def list_runs(
    project: Optional[str] = Query(None),
    environment: Optional[str] = Query(None),
    experiment: Optional[str] = Query(None),
):
    """List all runs with optional filters."""
    from adare.core.dto.show import RunListRequest

    dto = RunListRequest(
        project=project,
        environment=environment,
        experiment=experiment,
    )
    result = _api().show.list_runs(dto)
    return result_to_response(result)


@router.get("/{ulid}")
async def get_run(ulid: str):
    """Get run details by ULID."""
    result = _api().show.get_run(ulid=ulid)
    return result_to_response(result)


@router.delete("/{ulid}")
async def remove_run(ulid: str, project_path: Optional[str] = Query(None)):
    """Remove a run by ULID."""
    from pathlib import Path
    from adare.core.dto.show import RunRemoveRequest

    dto = RunRemoveRequest(
        ulid=ulid,
        project_path=Path(project_path) if project_path else None,
    )
    result = _api().show.remove_run(dto)
    return result_to_response(result)
