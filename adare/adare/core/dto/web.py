"""
Web Data Transfer Objects for API layer.

These DTOs provide type-safe request/response objects for web operations,
enabling consistent interfaces across CLI, REST API, and Web UI.
"""
from dataclasses import dataclass
from pathlib import Path

# =============================================================================
# Authentication DTOs
# =============================================================================

@dataclass
class WebLoginResult:
    """Result of web login operation."""
    logged_in: bool
    username: str | None = None
    message: str = ""


@dataclass
class WebLogoutResult:
    """Result of web logout operation."""
    logged_out: bool
    message: str = ""


@dataclass
class WebStatusResult:
    """Result of web status check."""
    logged_in: bool
    username: str | None = None


# =============================================================================
# Download DTOs
# =============================================================================

@dataclass
class DownloadEnvironmentRequest:
    """Request to download an environment."""
    project_path: Path
    environment_name: str


@dataclass
class DownloadExperimentRequest:
    """Request to download an experiment."""
    project_path: Path
    ulid: str


@dataclass
class DownloadTestfunctionRequest:
    """Request to download a testfunction."""
    project_path: Path
    testfunction_name: str
    version: int | None = None


@dataclass
class DownloadResult:
    """Result of download operation."""
    downloaded: bool
    message: str = ""
    location: Path | None = None


# =============================================================================
# Sync DTOs
# =============================================================================

@dataclass
class SyncRequest:
    """Request to sync with web app."""
    project_path: Path | None = None


@dataclass
class SyncResult:
    """Result of sync operation."""
    synced: bool
    message: str = ""


# =============================================================================
# Upload/Publish DTOs
# =============================================================================

@dataclass
class UploadRunRequest:
    """Request to upload an experiment run.

    ``project_path`` is required: the run is a project-scoped record, so the
    serializer has to open that project's database rather than the global one.
    """
    project_path: Path
    ulid: str


@dataclass
class PublishRunRequest:
    """Request to publish an experiment run."""
    project_path: Path
    ulid: str


@dataclass
class PublishResult:
    """Result of publish operation."""
    published: bool
    message: str = ""


# =============================================================================
# Check DTOs
# =============================================================================

@dataclass
class CheckExperimentRequest:
    """Request to check if experiment exists online."""
    ulid: str


@dataclass
class CheckExperimentResult:
    """Result of experiment check."""
    experiment_ulid: str
    exists: bool
    status: str = ""  # 'published' or 'not_found'


@dataclass
class CheckRunRequest:
    """Request to check if run exists online."""
    ulid: str


@dataclass
class CheckRunResult:
    """Result of run check."""
    run_ulid: str
    exists: bool
    status: str = ""  # 'published' or 'not_found'


# =============================================================================
# Submit DTOs
# =============================================================================

@dataclass
class SubmitRequest:
    """Request to submit an entity (experiment/testfunction/environment) as a PR."""
    project_path: Path
    name: str
    action: str = 'create'
    # Experiments only: skip the client-side dependency pre-flight. The pre-flight
    # reads the server's PUBLISHED catalog, so it cannot see a test function whose
    # owning set is still unpublished even though ingest would resolve it. This is
    # the escape hatch for that case; the server stays authoritative.
    skip_dependency_check: bool = False


@dataclass
class SubmitResult:
    """Result of submit operation."""
    pr_url: str = ""
    pr_number: int = 0
    message: str = ""


# =============================================================================
# Bundle Download DTOs
# =============================================================================

@dataclass
class DownloadBundleRequest:
    """Request to download an experiment bundle."""
    project_path: Path
    ulid: str


@dataclass
class DownloadBundleResult:
    """Result of a bundle download, listing what was fetched."""
    experiment_name: str
    environment_names: list[str]
    testfunction_names: list[str]
    message: str = ""
