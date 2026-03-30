"""
Web Data Transfer Objects for API layer.

These DTOs provide type-safe request/response objects for web operations,
enabling consistent interfaces across CLI, REST API, and Web UI.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# =============================================================================
# Authentication DTOs
# =============================================================================

@dataclass
class WebLoginResult:
    """Result of web login operation."""
    logged_in: bool
    username: Optional[str] = None
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
    username: Optional[str] = None


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
    version: Optional[int] = None


@dataclass
class DownloadResult:
    """Result of download operation."""
    downloaded: bool
    message: str = ""
    location: Optional[Path] = None


# =============================================================================
# Sync DTOs
# =============================================================================

@dataclass
class SyncRequest:
    """Request to sync with web app."""
    project_path: Optional[Path] = None


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
    """Request to upload an experiment run."""
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
    include_disk_images: bool = False
