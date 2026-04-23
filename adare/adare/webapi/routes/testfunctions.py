"""Test function endpoints."""
import logging

from fastapi import APIRouter, Query

from adare.webapi.adapters import result_to_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/testfunctions", tags=["testfunctions"])


# ---- Helpers ----

def _api():
    from adare.api import AdareAPI
    return AdareAPI()


# ---- Endpoints ----

@router.get("")
async def list_testfunctions(file_name: str | None = Query(None)):
    """List all test functions, optionally filtered by source file."""
    result = _api().show.list_testfunctions(file_name=file_name)
    return result_to_response(result)


@router.get("/{dotnotation:path}")
async def get_testfunction(dotnotation: str):
    """Get test function details by dotnotation (e.g. ``standard.file_exists``)."""
    result = _api().show.get_testfunction(dotnotation)
    return result_to_response(result)
