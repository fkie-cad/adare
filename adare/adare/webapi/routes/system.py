"""Host resources, storage, usage history and run capacity endpoints."""

import logging

from fastapi import APIRouter, Query

from adare.webapi.adapters import result_to_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])


# ---- Helpers ----


def _api():
    from adare.api import AdareAPI

    return AdareAPI()


# ---- Endpoints ----


@router.get("/resources")
def get_resources():
    """Live CPU, memory, disk and the running VMs."""
    return result_to_response(_api().system.get_resources())


@router.get("/storage")
def get_storage(refresh: bool = Query(False)):
    """Disk usage of ADARE's directories (cached for minutes; ``refresh`` re-measures)."""
    return result_to_response(_api().system.get_storage(refresh=refresh))


@router.get("/history")
def get_history(hours: float = Query(24, gt=0, le=24 * 30)):
    """Host usage samples of the last ``hours``."""
    return result_to_response(_api().system.get_history(hours=hours))


@router.get("/run-usage")
def get_run_usage(environment: str | None = Query(None), limit: int = Query(100, gt=0, le=1000)):
    """Measured resource usage of recent runs."""
    return result_to_response(_api().system.get_run_usage(environment_name=environment, limit=limit))


@router.get("/capacity")
def get_capacity():
    """How many more runs of each environment fit on the host right now."""
    return result_to_response(_api().system.get_capacity())
