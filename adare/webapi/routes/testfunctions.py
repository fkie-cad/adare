"""Test function endpoints."""
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from adare.webapi.adapters import result_to_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/testfunctions", tags=["testfunctions"])


# ---- Pydantic request models ----

class TestfunctionCreateBody(BaseModel):
    """Request body for creating a testfunction."""
    project_path: str
    name: str


class TestfunctionLoadBody(BaseModel):
    """Request body for loading a testfunction from file."""
    path: str
    force: bool = False


# ---- Helpers ----

def _api():
    from adare.api import AdareAPI
    return AdareAPI()


# ---- Endpoints ----

@router.get("")
async def list_testfunctions(file_name: Optional[str] = Query(None)):
    """List all test functions, optionally filtered by source file."""
    result = _api().show.list_testfunctions(file_name=file_name)
    return result_to_response(result)


@router.post("")
async def create_testfunction(body: TestfunctionCreateBody):
    """Create a new testfunction."""
    from adare.core.dto.testfunction import TestfunctionCreateRequest

    dto = TestfunctionCreateRequest(
        project_path=Path(body.project_path),
        name=body.name,
    )
    result = _api().testfunction.create(dto)
    return result_to_response(result)


@router.post("/load")
async def load_testfunction(body: TestfunctionLoadBody):
    """Load a testfunction from file."""
    from adare.core.dto.testfunction import TestfunctionLoadRequest

    dto = TestfunctionLoadRequest(
        path=Path(body.path),
        force=body.force,
    )
    result = _api().testfunction.load(dto)
    return result_to_response(result)


@router.get("/{name}/usage")
async def get_testfunction_usage(name: str):
    """Get testfunction usage information."""
    result = _api().testfunction.get_usage(name)
    return result_to_response(result)


@router.get("/{name}/exists")
async def check_testfunction_exists(name: str):
    """Check if a testfunction exists."""
    result = _api().testfunction.exists(name)
    return result_to_response(result)


@router.delete("/{name}")
async def remove_testfunction(name: str, force: bool = Query(False)):
    """Remove a testfunction."""
    result = _api().testfunction.remove(name, force=force)
    return result_to_response(result)


@router.get("/{dotnotation:path}")
async def get_testfunction(dotnotation: str):
    """Get test function details by dotnotation (e.g. ``standard.file_exists``)."""
    result = _api().show.get_testfunction(dotnotation)
    return result_to_response(result)
