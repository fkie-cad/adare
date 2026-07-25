"""Resolve ADARE VM names to VirtualSpice display URLs (launch-and-hand-off).

Single source of truth for the "watch a running VM" hand-off: ADARE owns the VM
*name* (== libvirt domain name == VM instance name); VirtualSpice owns the
*uuid*. Every trigger (CLI, dev-session auto-open, adare-web button) resolves the
name to a uuid via VirtualSpice's own ``/api/vms`` and builds the standalone
display-page path. Callers prepend the ``http://<host>:8081`` origin so host
handling stays with each caller.
"""

import logging
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

DEFAULT_SPICE_PORT = 8081

router = APIRouter(tags=["vm-watch"])


def resolve_vm_uuid(name: str, spice_port: int = DEFAULT_SPICE_PORT) -> str | None:
    """Return the VirtualSpice uuid for the VM whose name matches ``name``.

    Queries VirtualSpice's ``GET /api/vms`` (both ADARE and VirtualSpice share
    the same ``qemu:///session``, so VirtualSpice already sees ADARE's running
    domains). Returns ``None`` if the VM is not found or VirtualSpice is down.
    """
    url = f"http://127.0.0.1:{spice_port}/api/vms"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            vms = resp.json()
    except (httpx.HTTPError, ConnectionError) as e:
        logger.warning("Could not reach VirtualSpice at %s: %s", url, e)
        return None

    for vm in vms:
        if vm.get("name") == name:
            return vm.get("uuid")
    return None


def build_display_path(uuid: str, name: str, view_only: bool) -> str:
    """Build the VirtualSpice standalone display-page path for a VM.

    Callers prepend the origin (e.g. ``http://<host>:8081``).
    """
    return (
        f"/display.html?vmId={uuid}"
        f"&name={quote(name)}"
        f"&viewOnly={'1' if view_only else '0'}"
    )


@router.get("/api/vm-watch-url")
def vm_watch_url(name: str, view_only: bool = True):
    """Resolve an ADARE VM name to the live-display connection info.

    The ADARE-owned viewer connects to the returned same-origin ``ws_path``
    (``/ws/vm/{uuid}``), which ADARE proxies to VirtualSpice internally — the
    browser never contacts ``:8081`` directly. Returns 404 when the VM name
    cannot be resolved (VirtualSpice down or no matching domain).
    """
    uuid = resolve_vm_uuid(name, spice_port=DEFAULT_SPICE_PORT)
    if uuid is None:
        raise HTTPException(
            status_code=404,
            detail=f"No running VM named '{name}' found in VirtualSpice",
        )
    return {
        "uuid": uuid,
        "name": name,
        "view_only": view_only,
        "spice_port": DEFAULT_SPICE_PORT,
        "ws_path": f"/ws/vm/{uuid}",
    }
