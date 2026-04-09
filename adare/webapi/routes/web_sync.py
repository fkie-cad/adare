"""Web integration and sync endpoints."""
import logging

from fastapi import APIRouter

from adare.webapi.adapters import result_to_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/web", tags=["web-sync"])


# ---- Helpers ----

def _api():
    from adare.api import AdareAPI
    return AdareAPI()


# ---- Endpoints ----

@router.post("/login")
async def login():
    """Login to the ADARE web service."""
    result = _api().web.login()
    return result_to_response(result)


@router.post("/logout")
async def logout():
    """Logout from the ADARE web service."""
    result = _api().web.logout()
    return result_to_response(result)


@router.get("/status")
async def get_status():
    """Get current web service authentication status."""
    result = _api().web.get_status()
    return result_to_response(result)


@router.post("/sync")
async def sync():
    """Sync local data with the ADARE web service."""
    result = _api().web.sync()
    return result_to_response(result)
