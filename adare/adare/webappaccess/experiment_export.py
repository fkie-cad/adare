"""
Export experiment files for submission to the shared Gitea repository.
"""
import logging
from pathlib import Path

from adare.backend.project.directory import ProjectDirectory
from adare.config.configdirectory import ENVIRONMENTS_DIR

log = logging.getLogger(__name__)


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
    env_file = ENVIRONMENTS_DIR / f'{environment_name}.yml'
    if not env_file.is_file():
        raise FileNotFoundError(f'Environment file not found: {env_file}')

    return {f'environments/{environment_name}.yml': env_file.read_bytes()}
