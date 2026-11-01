"""Action-type catalogue endpoint (the workbench palette)."""

from fastapi import APIRouter

from adare.types.action_catalogue import build_action_catalogue

router = APIRouter(prefix="/api/actions", tags=["actions"])


@router.get("/types")
def get_action_types():
    """List every action type the playbook parser accepts, as ``ActionTypeMetadata[]``.

    Generated from the parser's action registry, so names and fields cannot drift.
    """
    return {"success": True, "data": build_action_catalogue()}
