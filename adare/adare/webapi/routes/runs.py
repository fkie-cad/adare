"""Run management endpoints."""
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from adare.webapi.adapters import result_to_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runs", tags=["runs"])


# ---- Helpers ----

def _api():
    from adare.api import AdareAPI
    return AdareAPI()


def _classify_artifact(rel_path: str) -> str:
    """Best-effort artifact kind from its relative path, for the frontend's
    Artifacts tab (screenshots grid / video player / report / logs)."""
    lower = rel_path.lower()
    suffix = Path(lower).suffix
    name = Path(lower).name
    if lower.startswith("steps/") and suffix in (".png", ".jpg", ".jpeg"):
        return "screenshot"
    if suffix == ".mp4" or name == "run.mp4":
        return "video"
    if name.startswith("report"):
        return "report"
    if suffix == ".log" or "log" in name:
        return "log"
    return "other"


def _resolve_run_dir(ulid: str) -> Path | None:
    """Resolve a run's on-disk directory, or None if unknown/missing."""
    result = _api().show.get_run_files(ulid)
    if not result.success or not result.data:
        return None
    run_dir = result.data.get("run_dir")
    if not run_dir:
        return None
    path = Path(run_dir)
    return path if path.is_dir() else None


# ---- Endpoints ----

@router.get("")
async def list_runs(
    project: str | None = Query(None),
    environment: str | None = Query(None),
    experiment: str | None = Query(None),
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
async def remove_run(ulid: str, project_path: str | None = Query(None)):
    """Remove a run by ULID."""
    from pathlib import Path

    from adare.core.dto.show import RunRemoveRequest

    dto = RunRemoveRequest(
        ulid=ulid,
        project_path=Path(project_path) if project_path else None,
    )
    result = _api().show.remove_run(dto)
    return result_to_response(result)


@router.get("/{ulid}/artifacts")
async def list_run_artifacts(ulid: str):
    """List a run's on-disk artifacts (screenshots, video, report, logs)."""
    run_dir = _resolve_run_dir(ulid)
    if run_dir is None:
        return {"success": True, "data": []}

    artifacts = []
    for entry in sorted(run_dir.rglob("*")):
        if not entry.is_file():
            continue
        rel_path = entry.relative_to(run_dir).as_posix()
        artifacts.append({
            "path": rel_path,
            "kind": _classify_artifact(rel_path),
            "size": entry.stat().st_size,
        })
    return {"success": True, "data": artifacts}


@router.get("/{ulid}/artifacts/{artifact_path:path}")
async def get_run_artifact(ulid: str, artifact_path: str):
    """Stream a single run artifact file."""
    run_dir = _resolve_run_dir(ulid)
    if run_dir is None:
        raise HTTPException(status_code=404, detail="run directory not found")

    resolved_dir = run_dir.resolve()
    target = (run_dir / artifact_path).resolve()
    # Path-traversal guard: the resolved file must stay under the run dir.
    if not str(target).startswith(str(resolved_dir)):
        raise HTTPException(status_code=404)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return FileResponse(target)
