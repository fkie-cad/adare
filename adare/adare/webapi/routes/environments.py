"""Environment management endpoints."""
import logging
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import requests
from fastapi import APIRouter
from pydantic import BaseModel

from adare.webapi.adapters import result_to_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/environments", tags=["environments"])

# Publish contract mirrors (see server `giteaeventmanager/.../plugin.py`
# `check_file_validity`): a baked VM URL must be an http(s) URL with a REQUIRED
# 64-hex sha256. The URL no longer needs a disk extension (owncloud/Nextcloud
# share links have none) — integrity is anchored on the required sha256 and a
# `vm_format` hint. Kept here so the web variant only ever produces publishable
# environments.
BAKED_VM_EXTENSIONS = ('.ova', '.qcow2', '.vmdk', '.vdi', '.img')
VM_FORMATS = ('qcow2', 'ova', 'vmdk', 'vdi', 'img', 'raw')
SHA256_HEX_RE = re.compile(r'^[0-9a-f]{64}$')


# ---- Pydantic request models ----

class EnvironmentCreateBody(BaseModel):
    """Request body for creating an environment.

    Carries both shapes the web dialog can submit: a baked VM hosted at a
    published URL (``vm_url`` + ``vm_sha256``) or a declarative recipe
    (``os_profile`` + ``iso_url`` + ``iso_sha256`` plus build params). The web
    variant never sends local paths — those remain CLI-only on the DTO.
    """
    project_path: str
    name: str
    # Baked (published URL) source
    vm_url: str | None = None
    vm_sha256: str | None = None
    vm_format: str | None = None
    # Recipe source
    os_profile: str | None = None
    iso_url: str | None = None
    iso_sha256: str | None = None
    disk_size: str | None = None
    ram_mb: int | None = None
    cpus: int | None = None
    setup_level: int | None = None


class CheckUrlBody(BaseModel):
    """Request body for validating a published VM/ISO URL."""
    url: str
    sha256: str | None = None
    kind: Literal["vm", "iso"] = "vm"
    vm_format: str | None = None


class EnvironmentVerifyBody(BaseModel):
    """Request body for verifying an environment."""
    project_path: str


# ---- Helpers ----

def _api():
    from adare.api import AdareAPI
    return AdareAPI()


def _validate_url_format(
    url: str, sha256: str | None, kind: str, vm_format: str | None = None
) -> str | None:
    """Return a human-readable reason the URL is invalid, or None if valid.

    Mirrors the server's publish contract: an http(s) URL (no disk-extension
    requirement — owncloud/Nextcloud share links have none) with a REQUIRED
    64-hex sha256. For a baked VM whose URL has no recognized disk extension, a
    ``vm_format`` hint from the allow-list is required; when present it is always
    validated against the allow-list.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "URL must use the http or https scheme."
    if not parsed.netloc:
        return "URL is missing a host."
    if not sha256:
        return f"{kind}_sha256 is required (64 lowercase hex characters)."
    if not SHA256_HEX_RE.match(sha256):
        return "sha256 must be 64 lowercase hex characters."
    if kind == "vm":
        if vm_format is not None and vm_format != "" and vm_format not in VM_FORMATS:
            return "vm_format must be one of: " + ", ".join(VM_FORMATS)
        has_ext = parsed.path.lower().endswith(BAKED_VM_EXTENSIONS)
        if not has_ext and not vm_format:
            return (
                "vm_format is required when the URL has no recognized disk "
                "extension (one of: " + ", ".join(VM_FORMATS) + ")."
            )
    return None


# ---- Endpoints ----

@router.get("")
async def list_environments():
    """List all environments."""
    result = _api().show.list_environments()
    return result_to_response(result)


@router.get("/os-profiles")
async def list_os_profiles():
    """List available OS profiles for building recipe environments.

    Declared before ``/{name}`` so the literal path isn't captured as an
    environment name. Feeds the recipe dialog's OS-profile dropdown.
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
    """Create a new environment descriptor from a published URL (baked or recipe)."""
    from adare.core.dto.environment import EnvironmentCreateRequest

    # Enforce the publish contract on baked-URL creates before touching the
    # service: http(s), a required 64-hex sha256, and a vm_format when the URL
    # has no recognized disk extension. (Recipe ISO integrity is enforced by the
    # service/backend, which already requires iso_sha256.)
    if body.vm_url:
        reason = _validate_url_format(body.vm_url, body.vm_sha256, "vm", body.vm_format)
        if reason is not None:
            return {"success": False, "error": {
                "code": "InvalidVmUrl", "message": reason, "solutions": [],
            }}

    dto = EnvironmentCreateRequest(
        project_path=Path(body.project_path),
        name=body.name,
        vm_url=body.vm_url,
        vm_sha256=body.vm_sha256,
        vm_format=body.vm_format,
        os_profile=body.os_profile,
        iso_url=body.iso_url,
        iso_sha256=body.iso_sha256,
        disk_size=body.disk_size,
        ram_mb=body.ram_mb,
        cpus=body.cpus,
        setup_level=body.setup_level,
    )
    result = _api().environment.create(dto)
    return result_to_response(result)


@router.post("/check-url")
async def check_environment_url(body: CheckUrlBody):
    """Validate a published VM/ISO URL: format (contract) + reachability (HEAD).

    Returns ``{valid, reachable, status, reason}``. ``valid`` reflects the
    format contract; ``reachable`` reflects a live HEAD probe (the browser can't
    do a reliable cross-origin HEAD, so it is proxied here).
    """
    reason = _validate_url_format(body.url, body.sha256, body.kind, body.vm_format)
    if reason is not None:
        return {"success": True, "data": {
            "valid": False, "reachable": False, "status": None, "reason": reason,
        }}

    try:
        resp = requests.head(body.url, allow_redirects=True, timeout=10)
    except requests.RequestException as e:
        return {"success": True, "data": {
            "valid": True, "reachable": False, "status": None,
            "reason": f"URL is not reachable: {e}",
        }}

    reachable = resp.status_code < 400
    return {"success": True, "data": {
        "valid": True,
        "reachable": reachable,
        "status": resp.status_code,
        "reason": None if reachable else f"Host returned HTTP {resp.status_code}.",
    }}


@router.delete("/{name}")
async def delete_environment(name: str, force: bool = False):
    """Delete an environment by name or ULID."""
    result = _api().environment.delete(name, force=force)
    return result_to_response(result)


@router.post("/{name}/verify")
async def verify_environment(name: str, body: EnvironmentVerifyBody):
    """Run the built-in ``verify_vm`` smoke test against this environment.

    Idempotently attaches the built-in verify experiment to the environment,
    then starts a background run and returns immediately with its ULID.
    """
    project_path = Path(body.project_path)

    setup_result = _api().experiment.ensure_verify_setup(project_path, name)
    if not setup_result.success:
        return result_to_response(setup_result)

    run_result = await _api().experiment.run(project_path, setup_result.data, name)
    return result_to_response(run_result)
