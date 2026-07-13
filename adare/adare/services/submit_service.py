"""
Submit Service - Business logic for submitting experiments, testfunctions, and environments
to the shared Gitea repository via pull requests.
"""
import logging
from datetime import datetime

from adare.core.dto.web import SubmitRequest, SubmitResult
from adare.core.result import Result

log = logging.getLogger(__name__)


class SubmitService:
    """Service for submitting content to the shared Gitea repo as PRs."""

    def submit_experiment(self, request: SubmitRequest) -> Result[SubmitResult]:
        import requests

        from adare.webappaccess.exceptions import NotLoggedInError
        from adare.webappaccess.experiment_export import export_experiment_for_submission

        try:
            files = export_experiment_for_submission(request.project_path, request.name)
            pr = self._create_pr('experiment', request.name, files, action=request.action)
            return Result.ok(SubmitResult(
                pr_url=pr['html_url'],
                pr_number=pr['number'],
                message=f"PR #{pr['number']} created for experiment '{request.name}'"
            ))
        except FileNotFoundError as e:
            return Result.fail(
                code="FileNotFound",
                message=str(e),
                solutions=['Verify the experiment exists in your project']
            )
        except NotLoggedInError as e:
            return Result.fail(
                code="NotLoggedIn",
                message=str(e),
                solutions=['Run "adare web login" first']
            )
        except (RuntimeError, requests.HTTPError, requests.ConnectionError) as e:
            log.error(f"Failed to submit experiment: {e}")
            return Result.fail(
                code="SubmitError",
                message=f"Failed to submit experiment: {e}",
                solutions=['Check your internet connection', 'Verify you are logged in']
            )

    def submit_testfunction(self, request: SubmitRequest) -> Result[SubmitResult]:
        import requests

        from adare.webappaccess.exceptions import NotLoggedInError
        from adare.webappaccess.experiment_export import export_testfunction_for_submission

        try:
            files = export_testfunction_for_submission(request.project_path, request.name)
            pr = self._create_pr('testfunction', request.name, files, action=request.action)
            return Result.ok(SubmitResult(
                pr_url=pr['html_url'],
                pr_number=pr['number'],
                message=f"PR #{pr['number']} created for testfunction '{request.name}'"
            ))
        except FileNotFoundError as e:
            return Result.fail(
                code="FileNotFound",
                message=str(e),
                solutions=['Verify the testfunction exists in your project']
            )
        except NotLoggedInError as e:
            return Result.fail(
                code="NotLoggedIn",
                message=str(e),
                solutions=['Run "adare web login" first']
            )
        except (RuntimeError, requests.HTTPError, requests.ConnectionError) as e:
            log.error(f"Failed to submit testfunction: {e}")
            return Result.fail(
                code="SubmitError",
                message=f"Failed to submit testfunction: {e}",
                solutions=['Check your internet connection', 'Verify you are logged in']
            )

    def submit_environment(self, request: SubmitRequest) -> Result[SubmitResult]:
        import requests

        from adare.webappaccess.exceptions import NotLoggedInError
        from adare.webappaccess.experiment_export import export_environment_for_submission

        try:
            files = export_environment_for_submission(request.project_path, request.name)
            pr = self._create_pr('environment', request.name, files, action=request.action)
            return Result.ok(SubmitResult(
                pr_url=pr['html_url'],
                pr_number=pr['number'],
                message=f"PR #{pr['number']} created for environment '{request.name}'"
            ))
        except FileNotFoundError as e:
            return Result.fail(
                code="FileNotFound",
                message=str(e),
                solutions=['Verify the environment exists in your project']
            )
        except NotLoggedInError as e:
            return Result.fail(
                code="NotLoggedIn",
                message=str(e),
                solutions=['Run "adare web login" first']
            )
        except (RuntimeError, requests.HTTPError, requests.ConnectionError) as e:
            log.error(f"Failed to submit environment: {e}")
            return Result.fail(
                code="SubmitError",
                message=f"Failed to submit environment: {e}",
                solutions=['Check your internet connection', 'Verify you are logged in']
            )

    def precheck_submission(self, entity_type: str, name: str) -> "Result[dict]":
        """Ask the server to classify a *create* submission by name, before any PR.

        Lets the CLI warn/guide up front (already-published -> offer a modify PR;
        open-duplicate -> point at the existing PR) instead of opening a PR the
        server would only reject/auto-close. Uses the Django token (this endpoint
        is ``IsAuthenticated``). Returns the raw ``{code, message, pr_number?}``.
        """
        import requests

        import adare.config.server as config_server
        from adare.webappaccess.exceptions import NotLoggedInError
        from adare.webappaccess.login import WebappLogin

        try:
            header = WebappLogin().get_django_authenticated_request_header()
            url = f'{config_server.API_URL}submit/precheck/'
            response = requests.post(
                url, json={'entity_type': entity_type, 'name': name},
                headers=header, timeout=config_server.TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return Result.ok(response.json())
        except NotLoggedInError as e:
            return Result.fail(
                code="NotLoggedIn",
                message=str(e),
                solutions=['Run "adare web login" first'],
            )
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as e:
            log.error(f"Submission pre-check failed: {e}")
            return Result.fail(
                code="PrecheckError",
                message=f"Could not pre-check the submission: {e}",
                solutions=['Check your internet connection', 'Verify you are logged in'],
            )

    def _create_pr(self, entity_type: str, name: str, files: dict[str, bytes],
                   action: str = 'create') -> dict:
        """Create a branch, upload files, and open a ``action`` PR in the shared repo."""
        import adare.config.server as config_server
        from adare.webappaccess.exceptions import NotLoggedInError
        from adare.webappaccess.gitea_api import GiteaApiClient
        from adare.webappaccess.login import WebappLogin

        webapp = WebappLogin()
        user_session = webapp.get_user_session()
        if not user_session:
            raise NotLoggedInError(log, message='You must be logged in to submit content')

        gitea_token = user_session['gitea_token']
        client = GiteaApiClient(config_server.GITEA_URL, gitea_token)

        owner = config_server.GITEA_EXPERIMENTS_REPO_OWNER
        repo = config_server.GITEA_EXPERIMENTS_REPO

        title = f'[{entity_type} {action}] {name}'
        head_prefix = f'submit/{entity_type}/{name}-'

        # Reuse an already-open PR for this entity+action instead of opening a
        # duplicate. Re-uploading then pushes to the same branch/PR, so the server
        # sees the same gitea_pr_number and idempotently upserts its draft (no name
        # clash). Match on the exact title; for create also match the head-branch
        # prefix (branch names carry no action, so prefix-matching only a create
        # avoids mistaking a create branch for a modify).
        existing_pr = client.find_open_pull_request(
            owner, repo, title=title,
            head_prefix=head_prefix if action == 'create' else None,
        )
        if existing_pr:
            branch_name = existing_pr['head']['ref']
            log.info(f'Reusing open PR #{existing_pr["number"]} on branch {branch_name}')
        else:
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            branch_name = f'submit/{entity_type}/{name}-{timestamp}'
            if not client.create_branch(owner, repo, branch_name):
                raise RuntimeError(f'Failed to create branch {branch_name}')

        for filepath, content in files.items():
            success = client.create_or_update_file(
                owner, repo, filepath, content, branch_name,
                message=f'[{entity_type} {action}] Add {filepath}'
            )
            if not success:
                raise RuntimeError(f'Failed to upload {filepath}')

        if existing_pr:
            return existing_pr

        return client.create_pull_request(
            owner, repo,
            title=title,
            head=branch_name,
            body=f'Automated submission ({action}) of {entity_type} `{name}` via ADARE CLI.',
        )
