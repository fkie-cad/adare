"""
Export experiment files for submission to the shared Gitea repository.
"""
import logging
import re
from pathlib import Path

from adare.backend.project.directory import ProjectDirectory

log = logging.getLogger(__name__)

# Publish contract mirror (see server `giteaeventmanager/.../plugin.py`
# `check_file_validity` and webapi `_validate_url_format`): the same rules are
# enforced here, client-side, so a local path or a missing sha256 is caught
# BEFORE any Gitea branch/PR is created — never leak a local filesystem path.
_SHA256_HEX_RE = re.compile(r'^[0-9a-f]{64}$', re.IGNORECASE)
_DISK_EXTENSIONS = ('.ova', '.qcow2', '.vmdk', '.vdi', '.img')
_VM_FORMATS = ('qcow2', 'ova', 'vmdk', 'vdi', 'img', 'raw')


class EnvironmentSubmissionError(ValueError):
    """An environment failed the client-side publish pre-flight.

    Raised before any Gitea branch/PR is created, so a non-publishable
    environment (local path, missing/invalid sha256, missing vm_format) never
    reaches the shared repo.
    """


def _is_http_url(value: str) -> bool:
    from urllib.parse import urlparse
    return urlparse(value).scheme in ('http', 'https')


def _preflight_environment(env_file: Path) -> None:
    """Enforce the URL-only + required-sha256 publish contract on ``env_file``.

    Raises:
        EnvironmentSubmissionError: If the environment is not publishable.
    """
    from adare.types.environment import parse_environment_file

    metadata = parse_environment_file(env_file)
    if metadata is None:
        raise EnvironmentSubmissionError(f'Could not parse environment file: {env_file}')

    # Recipe source: the disk is built on load; the ISO must be a published URL
    # with a required sha256 (a local ISO path is not publishable).
    if metadata.is_recipe_environment:
        recipe = metadata.recipe
        if not _is_http_url(recipe.iso):
            raise EnvironmentSubmissionError(
                f"recipe 'iso' must be an http(s) URL to publish (got a local path: {recipe.iso!r}). "
                "Host the ISO and reference its URL."
            )
        if not recipe.iso_sha256 or not _SHA256_HEX_RE.match(recipe.iso_sha256):
            raise EnvironmentSubmissionError(
                "recipe 'iso_sha256' is required and must be 64 hex characters to publish."
            )
        return

    # Legacy vagrantbox (owner/box) is verified by the server against Vagrant
    # Cloud; nothing local to leak here.
    if metadata.is_vagrant_environment:
        return

    # Baked VM source: must be a published http(s) URL with a required sha256.
    vm = metadata.vm or ''
    if not _is_http_url(vm):
        raise EnvironmentSubmissionError(
            f"'vm' must be an http(s) URL to publish a baked environment (got a local path: {vm!r}). "
            "Host the disk image and reference its URL, e.g. via "
            "'adare environment publish-prepare'."
        )
    if not metadata.vm_sha256 or not _SHA256_HEX_RE.match(metadata.vm_sha256):
        raise EnvironmentSubmissionError(
            "'vm_sha256' is required and must be 64 hex characters to publish a baked VM URL."
        )
    if metadata.vm_format is not None and metadata.vm_format not in _VM_FORMATS:
        raise EnvironmentSubmissionError(
            "'vm_format' must be one of: " + ", ".join(_VM_FORMATS)
        )
    from urllib.parse import urlparse
    has_ext = urlparse(vm).path.lower().endswith(_DISK_EXTENSIONS)
    if not has_ext and not metadata.vm_format:
        raise EnvironmentSubmissionError(
            "'vm_format' is required when the VM URL has no recognized disk extension "
            "(one of: " + ", ".join(_VM_FORMATS) + ")."
        )


def export_experiment_for_submission(project_path: Path, experiment_name: str) -> dict[str, bytes]:
    """
    Collect experiment files for Gitea submission.

    Returns dict mapping repo-relative filepaths to file content bytes.
    """
    experiment_dir = ProjectDirectory(project_path).experiments / experiment_name
    if not experiment_dir.is_dir():
        raise FileNotFoundError(f'Experiment directory not found: {experiment_dir}')

    files = {}

    playbook_file = experiment_dir / 'playbook.yml'
    if not playbook_file.is_file():
        raise FileNotFoundError(f'playbook.yml not found in {experiment_dir}')
    files[f'experiments/{experiment_name}/playbook.yml'] = playbook_file.read_bytes()

    metadata_file = experiment_dir / 'metadata.yml'
    if not metadata_file.is_file():
        raise FileNotFoundError(f'metadata.yml not found in {experiment_dir}')
    files[f'experiments/{experiment_name}/metadata.yml'] = metadata_file.read_bytes()

    img_dir = experiment_dir / 'img'
    if img_dir.is_dir():
        image_count = 0
        for entry in img_dir.iterdir():
            if entry.is_file():
                files[f'experiments/{experiment_name}/img/{entry.name}'] = entry.read_bytes()
                image_count += 1
        log.info(f'Collected {image_count} image(s) from {img_dir}')

    return files


def export_testfunction_for_submission(project_path: Path, testfunction_name: str) -> dict[str, bytes]:
    """
    Collect testfunction files for Gitea submission.

    Returns dict mapping repo-relative filepaths to file content bytes.
    """
    tf_dir = ProjectDirectory(project_path).testfunctions / testfunction_name
    if not tf_dir.is_dir():
        raise FileNotFoundError(f'Testfunction directory not found: {tf_dir}')

    files = {}

    py_file = tf_dir / f'{testfunction_name}.py'
    if not py_file.is_file():
        raise FileNotFoundError(f'{testfunction_name}.py not found in {tf_dir}')
    files[f'testfunctions/{testfunction_name}/{testfunction_name}.py'] = py_file.read_bytes()

    req_file = tf_dir / 'requirements.txt'
    if not req_file.is_file():
        raise FileNotFoundError(f'requirements.txt not found in {tf_dir}')
    files[f'testfunctions/{testfunction_name}/requirements.txt'] = req_file.read_bytes()

    return files


def export_environment_for_submission(project_path: Path, environment_name: str) -> dict[str, bytes]:
    """
    Collect environment file for Gitea submission.

    Returns dict mapping repo-relative filepaths to file content bytes.
    """
    # Local import mirrors the codebase's lazy-import pattern and avoids any
    # backend<->webappaccess import cycle.
    from adare.backend.environment.database import get_environment_path_by_project_and_name

    env_file = get_environment_path_by_project_and_name(project_path, environment_name)
    if not env_file.is_file():
        raise FileNotFoundError(f'Environment file not found: {env_file}')

    # Pre-flight the publish contract BEFORE returning any bytes to the submit
    # service (which would otherwise create a Gitea branch/PR for a
    # non-publishable environment). This is the client-side no-path-leak guard.
    _preflight_environment(env_file)

    return {f'environments/{environment_name}.yml': env_file.read_bytes()}
