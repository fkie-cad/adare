"""
Web Service - Business logic for web operations.

This service handles web-related operations (login, sync, download, upload)
and returns Result[T] objects that can be consumed by any frontend (CLI, Web UI, REST API).
"""
from pathlib import Path
from typing import Optional

import logging

from adare.core.result import Result
from adare.core.dto.web import (
    WebLoginResult,
    WebLogoutResult,
    WebStatusResult,
    DownloadEnvironmentRequest,
    DownloadExperimentRequest,
    DownloadTestfunctionRequest,
    DownloadResult,
    SyncRequest,
    SyncResult,
    UploadRunRequest,
    PublishRunRequest,
    PublishResult,
    CheckExperimentRequest,
    CheckExperimentResult,
    CheckRunRequest,
    CheckRunResult,
)

log = logging.getLogger(__name__)


class WebService:
    """
    Service for web-related operations.

    All methods return Result[T] objects for consistent error handling
    across different frontends.
    """

    # =========================================================================
    # Authentication Operations
    # =========================================================================

    def login(self) -> Result[WebLoginResult]:
        """
        Perform web login.

        Returns:
            Result[WebLoginResult] with login status.
        """
        from adare.web.login import login

        try:
            login()
            # If we get here, login was successful
            return Result.ok(WebLoginResult(
                logged_in=True,
                message="Login successful"
            ))

        except Exception as e:
            log.error(f"Login failed: {e}")
            return Result.fail(
                code="LoginError",
                message=f"Login failed: {e}",
                solutions=['Check your internet connection', 'Verify your credentials']
            )

    def logout(self) -> Result[WebLogoutResult]:
        """
        Perform web logout.

        Returns:
            Result[WebLogoutResult] with logout status.
        """
        from adare.web.login import logout

        try:
            logout()
            return Result.ok(WebLogoutResult(
                logged_out=True,
                message="Logout successful"
            ))

        except Exception as e:
            log.error(f"Logout failed: {e}")
            return Result.fail(
                code="LogoutError",
                message=f"Logout failed: {e}",
                solutions=['Try logging out again']
            )

    def get_status(self) -> Result[WebStatusResult]:
        """
        Get current web login status.

        Returns:
            Result[WebStatusResult] with login status.
        """
        from adare.database.api.usersession import UserSessionApi

        try:
            with UserSessionApi() as db:
                db.remove_expired_user_sessions()
                user_session = db.get_first_user_session()

                return Result.ok(WebStatusResult(
                    logged_in=bool(user_session),
                    username=user_session.username if user_session else None
                ))

        except Exception as e:
            log.error(f"Failed to get web status: {e}")
            return Result.fail(
                code="StatusError",
                message=f"Failed to get web status: {e}",
                solutions=['Check database connection']
            )

    # =========================================================================
    # Download Operations
    # =========================================================================

    def download_environment(self, request: DownloadEnvironmentRequest) -> Result[DownloadResult]:
        """
        Download an environment from the web.

        Args:
            request: DownloadEnvironmentRequest with project path and environment name

        Returns:
            Result[DownloadResult] with download status.
        """
        from adare.backend.environment.commands import environment_download

        try:
            environment_download(request.project_path, request.environment_name)
            return Result.ok(DownloadResult(
                downloaded=True,
                message=f"Environment '{request.environment_name}' downloaded successfully"
            ))

        except Exception as e:
            log.error(f"Failed to download environment: {e}")
            return Result.fail(
                code="DownloadError",
                message=f"Failed to download environment: {e}",
                solutions=['Check your internet connection', 'Verify the environment name']
            )

    def download_experiment(self, request: DownloadExperimentRequest) -> Result[DownloadResult]:
        """
        Download an experiment from the web.

        Args:
            request: DownloadExperimentRequest with project path and ULID

        Returns:
            Result[DownloadResult] with download status.
        """
        from adare.backend.experiment.commands import experiment_download

        try:
            experiment_download(request.project_path, request.ulid)
            return Result.ok(DownloadResult(
                downloaded=True,
                message=f"Experiment '{request.ulid}' downloaded successfully"
            ))

        except Exception as e:
            log.error(f"Failed to download experiment: {e}")
            return Result.fail(
                code="DownloadError",
                message=f"Failed to download experiment: {e}",
                solutions=['Check your internet connection', 'Verify the experiment ULID']
            )

    def download_testfunction(self, request: DownloadTestfunctionRequest) -> Result[DownloadResult]:
        """
        Download a testfunction from the web.

        Args:
            request: DownloadTestfunctionRequest with project path and testfunction name

        Returns:
            Result[DownloadResult] with download status.
        """
        from adare.backend.testfunction.commands import testfunction_download

        try:
            testfunction_download(request.project_path, request.testfunction_name)
            return Result.ok(DownloadResult(
                downloaded=True,
                message=f"Testfunction '{request.testfunction_name}' downloaded successfully"
            ))

        except Exception as e:
            log.error(f"Failed to download testfunction: {e}")
            return Result.fail(
                code="DownloadError",
                message=f"Failed to download testfunction: {e}",
                solutions=['Check your internet connection', 'Verify the testfunction name']
            )

    # =========================================================================
    # Sync Operations
    # =========================================================================

    def sync(self, request: SyncRequest = None) -> Result[SyncResult]:
        """
        Sync project with web app.

        Args:
            request: Optional SyncRequest with project path

        Returns:
            Result[SyncResult] with sync status.
        """
        from adare.backend.sync import sync as backend_sync

        try:
            project_path = request.project_path if request else None
            backend_sync(project_path)
            return Result.ok(SyncResult(
                synced=True,
                message="Sync completed successfully"
            ))

        except Exception as e:
            log.error(f"Sync failed: {e}")
            return Result.fail(
                code="SyncError",
                message=f"Sync failed: {e}",
                solutions=['Check your internet connection', 'Verify you are logged in']
            )

    # =========================================================================
    # Upload/Publish Operations
    # =========================================================================

    def upload_run(self, request: UploadRunRequest) -> Result[PublishResult]:
        """
        Upload an experiment run to the server.

        Args:
            request: UploadRunRequest with run ULID

        Returns:
            Result[PublishResult] with upload status.
        """
        from adare.webappaccess.upload import publish_experiment_run

        try:
            publish_experiment_run(request.ulid)
            return Result.ok(PublishResult(
                published=True,
                message=f"Run '{request.ulid}' uploaded successfully"
            ))

        except Exception as e:
            log.error(f"Failed to upload run: {e}")
            return Result.fail(
                code="UploadError",
                message=f"Failed to upload run: {e}",
                solutions=['Check your internet connection', 'Verify you are logged in']
            )

    def publish_run(self, request: PublishRunRequest) -> Result[PublishResult]:
        """
        Publish an experiment run to the server.

        Args:
            request: PublishRunRequest with project path and run ULID

        Returns:
            Result[PublishResult] with publish status.
        """
        from adare.backend.experiment.commands import publish_run_command

        try:
            publish_run_command(request.project_path, request.ulid)
            return Result.ok(PublishResult(
                published=True,
                message=f"Run '{request.ulid}' published successfully"
            ))

        except Exception as e:
            log.error(f"Failed to publish run: {e}")
            return Result.fail(
                code="PublishError",
                message=f"Failed to publish run: {e}",
                solutions=['Check your internet connection', 'Verify you are logged in']
            )

    # =========================================================================
    # Check Operations
    # =========================================================================

    def check_experiment(self, request: CheckExperimentRequest) -> Result[CheckExperimentResult]:
        """
        Check if an experiment exists on the server.

        Args:
            request: CheckExperimentRequest with experiment ULID

        Returns:
            Result[CheckExperimentResult] with check result.
        """
        from adare.webappaccess.api_client import check_experiment_exists

        try:
            exists = check_experiment_exists(request.ulid)
            return Result.ok(CheckExperimentResult(
                experiment_ulid=request.ulid,
                exists=exists,
                status='published' if exists else 'not_found'
            ))

        except Exception as e:
            log.error(f"Failed to check experiment: {e}")
            return Result.fail(
                code="CheckError",
                message=f"Failed to check experiment: {e}",
                solutions=['Check your internet connection', 'Verify you are logged in']
            )

    def check_run(self, request: CheckRunRequest) -> Result[CheckRunResult]:
        """
        Check if a run exists on the server.

        Args:
            request: CheckRunRequest with run ULID

        Returns:
            Result[CheckRunResult] with check result.
        """
        from adare.webappaccess.api_client import check_run_exists

        try:
            exists = check_run_exists(request.ulid)
            return Result.ok(CheckRunResult(
                run_ulid=request.ulid,
                exists=exists,
                status='published' if exists else 'not_found'
            ))

        except Exception as e:
            log.error(f"Failed to check run: {e}")
            return Result.fail(
                code="CheckError",
                message=f"Failed to check run: {e}",
                solutions=['Check your internet connection', 'Verify you are logged in']
            )
