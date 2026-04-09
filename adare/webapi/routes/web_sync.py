"""Web integration and sync endpoints."""
import logging
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from adare.webapi.adapters import result_to_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/web", tags=["web-sync"])


# ---- Pydantic request models ----

class DownloadEnvironmentBody(BaseModel):
    """Request body for downloading an environment."""
    project_path: str
    environment_name: str


class DownloadExperimentBody(BaseModel):
    """Request body for downloading an experiment."""
    project_path: str
    ulid: str


class DownloadTestfunctionBody(BaseModel):
    """Request body for downloading a testfunction."""
    project_path: str
    testfunction_name: str
    version: int | None = None


class DownloadBundleBody(BaseModel):
    """Request body for downloading an experiment bundle."""
    project_path: str
    ulid: str
    include_disk_images: bool = False


class UploadRunBody(BaseModel):
    """Request body for uploading a run."""
    ulid: str


class PublishRunBody(BaseModel):
    """Request body for publishing a run."""
    project_path: str
    ulid: str


class SyncBody(BaseModel):
    """Request body for sync operation."""
    project_path: str | None = None


class SubmitBody(BaseModel):
    """Request body for submitting an entity as a PR."""
    project_path: str
    name: str


# ---- Helpers ----

def _api():
    from adare.api import AdareAPI
    return AdareAPI()


# ---- Authentication Endpoints ----

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


# ---- Sync Endpoints ----

@router.post("/sync")
async def sync(body: SyncBody | None = None):
    """Sync local data with the ADARE web service."""
    from adare.core.dto.web import SyncRequest

    dto = None
    if body and body.project_path:
        dto = SyncRequest(project_path=Path(body.project_path))
    result = _api().web.sync(dto)
    return result_to_response(result)


# ---- Download Endpoints ----

@router.post("/download/environment")
async def download_environment(body: DownloadEnvironmentBody):
    """Download an environment from the ADARE web service."""
    from adare.core.dto.web import DownloadEnvironmentRequest

    dto = DownloadEnvironmentRequest(
        project_path=Path(body.project_path),
        environment_name=body.environment_name,
    )
    result = _api().web.download_environment(dto)
    return result_to_response(result)


@router.post("/download/experiment")
async def download_experiment(body: DownloadExperimentBody):
    """Download an experiment from the ADARE web service."""
    from adare.core.dto.web import DownloadExperimentRequest

    dto = DownloadExperimentRequest(
        project_path=Path(body.project_path),
        ulid=body.ulid,
    )
    result = _api().web.download_experiment(dto)
    return result_to_response(result)


@router.post("/download/testfunction")
async def download_testfunction(body: DownloadTestfunctionBody):
    """Download a testfunction from the ADARE web service."""
    from adare.core.dto.web import DownloadTestfunctionRequest

    dto = DownloadTestfunctionRequest(
        project_path=Path(body.project_path),
        testfunction_name=body.testfunction_name,
        version=body.version,
    )
    result = _api().web.download_testfunction(dto)
    return result_to_response(result)


@router.post("/download/bundle")
async def download_bundle(body: DownloadBundleBody):
    """Download an experiment bundle with dependencies."""
    from adare.core.dto.web import DownloadBundleRequest

    dto = DownloadBundleRequest(
        project_path=Path(body.project_path),
        ulid=body.ulid,
        include_disk_images=body.include_disk_images,
    )
    result = _api().web.download_bundle(dto)
    return result_to_response(result)


# ---- Upload/Publish Endpoints ----

@router.post("/upload-run")
async def upload_run(body: UploadRunBody):
    """Upload an experiment run to the ADARE web service."""
    from adare.core.dto.web import UploadRunRequest

    dto = UploadRunRequest(ulid=body.ulid)
    result = _api().web.upload_run(dto)
    return result_to_response(result)


@router.post("/publish-run")
async def publish_run(body: PublishRunBody):
    """Publish an experiment run to the ADARE web service."""
    from adare.core.dto.web import PublishRunRequest

    dto = PublishRunRequest(
        project_path=Path(body.project_path),
        ulid=body.ulid,
    )
    result = _api().web.publish_run(dto)
    return result_to_response(result)


# ---- Check Endpoints ----

@router.get("/check/experiment/{ulid}")
async def check_experiment(ulid: str):
    """Check if an experiment exists on the ADARE web service."""
    from adare.core.dto.web import CheckExperimentRequest

    dto = CheckExperimentRequest(ulid=ulid)
    result = _api().web.check_experiment(dto)
    return result_to_response(result)


@router.get("/check/run/{ulid}")
async def check_run(ulid: str):
    """Check if a run exists on the ADARE web service."""
    from adare.core.dto.web import CheckRunRequest

    dto = CheckRunRequest(ulid=ulid)
    result = _api().web.check_run(dto)
    return result_to_response(result)


# ---- Submit Endpoints ----

@router.post("/submit/experiment")
async def submit_experiment(body: SubmitBody):
    """Submit an experiment as a Gitea PR."""
    from adare.core.dto.web import SubmitRequest

    dto = SubmitRequest(
        project_path=Path(body.project_path),
        name=body.name,
    )
    result = _api().web.submit_experiment(dto)
    return result_to_response(result)


@router.post("/submit/testfunction")
async def submit_testfunction(body: SubmitBody):
    """Submit a testfunction as a Gitea PR."""
    from adare.core.dto.web import SubmitRequest

    dto = SubmitRequest(
        project_path=Path(body.project_path),
        name=body.name,
    )
    result = _api().web.submit_testfunction(dto)
    return result_to_response(result)


@router.post("/submit/environment")
async def submit_environment(body: SubmitBody):
    """Submit an environment as a Gitea PR."""
    from adare.core.dto.web import SubmitRequest

    dto = SubmitRequest(
        project_path=Path(body.project_path),
        name=body.name,
    )
    result = _api().web.submit_environment(dto)
    return result_to_response(result)
