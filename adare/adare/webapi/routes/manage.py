"""Database and system management endpoints."""
import logging

from fastapi import APIRouter

from adare.webapi.adapters import result_to_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/manage", tags=["manage"])


# ---- Helpers ----

def _api():
    from adare.api import AdareAPI
    return AdareAPI()


# ---- Endpoints ----

@router.get("/db-status")
async def get_db_status():
    """Check database system status."""
    result = _api().manage.get_db_status()
    return result_to_response(result)
