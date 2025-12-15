# external imports
from pathlib import Path
from datetime import datetime

# internal imports
from adare.database.models.project_models import Experiment
from adare.database.api.experiment import ExperimentApi
from adare.database.api.environment import EnvironmentDbApi
from adare.database.reference_manager import reference_manager
from adare.database.api.stage import StageDbApi
from adare.backend.experiment.directory import ExperimentDirectory, ExperimentRunDirectory
from adare.backend.experiment.exceptions import NoEnvironmentError, MultipleEnvironmentsError
from adare.exceptions import EnvironmentNotFoundError
from adare.types.stages import Stage
from adarelib.constants import StatusEnum

# configure logging
import logging
log = logging.getLogger(__name__)


def get_experiment_by_project_and_name(project_path: Path, experiment_name: str, trigger_error: bool = True) -> str | None:
    with ExperimentApi(project_path) as api:
        experiment = api.get_experiment_by_project_and_name(project_path, experiment_name)
        if experiment is None:
            if trigger_error:
                log.error('experiment not found')
            return None
        return experiment.id


def get_experiment_by_ulid(project_path: Path, experiment_ulid: str, fields: list[str] = None) -> Experiment | dict | None:
    """
    Get experiment by ULID with intelligent relationship loading from project database.

    Args:
        project_path: Path to the project
        experiment_ulid: Experiment ULID
        fields: Optional list of fields to extract. If None, returns full object.
                Available fields: 'id', 'name', 'description', 'sha256', 'sha256_playbook',
                'sha256_metadata', 'ulid'
                Relationship fields: 'environments', 'environment_names', 'runs_count', 'tags'

    Returns:
        Experiment: Full object if fields=None
        dict: Experiment data if fields specified
        None: If experiment not found
    """
    from sqlalchemy.orm import joinedload, selectinload

    # Define which fields require which relationships
    RELATIONSHIP_REQUIREMENTS = {
        'environments': 'environments',
        'environment_names': 'environments',
        'environment_count': 'environments',
        'runs_count': 'runs',
        'runs': 'runs',
        'tags': 'tags',
        'abstract_tests': 'abstract_tests',
        'test_count': 'abstract_tests'
    }

    with ExperimentApi(project_path) as api:
        if fields and any(field in RELATIONSHIP_REQUIREMENTS for field in fields):
            # Build query with eager loading
            needed_relationships = set()
            for field in fields:
                if field in RELATIONSHIP_REQUIREMENTS:
                    needed_relationships.add(RELATIONSHIP_REQUIREMENTS[field])
            
            # Start with base query
            query = api._session.query(Experiment).filter_by(id=experiment_ulid)
            
            # Apply eager loading selectively
            if 'environments' in needed_relationships:
                query = query.options(selectinload(Experiment.environments))
            if 'runs' in needed_relationships:
                query = query.options(selectinload(Experiment.runs))
            if 'tags' in needed_relationships:
                query = query.options(selectinload(Experiment.tags))
            if 'abstract_tests' in needed_relationships:
                query = query.options(selectinload(Experiment.abstract_tests))
            
            experiment = query.first()
        else:
            # Simple query for backward compatibility
            experiment = api.get_experiment_by_ulid(experiment_ulid)
        
        if not experiment:
            return None
        
        # Return full object for backward compatibility
        if fields is None:
            return experiment
        
        # Extract requested fields safely
        result = {}
        for field in fields:
            try:
                if field == 'id':
                    result['id'] = experiment.id
                elif field == 'name':
                    result['name'] = experiment.name
                elif field == 'description':
                    result['description'] = experiment.description
                elif field == 'sha256':
                    result['sha256'] = experiment.sha256
                elif field == 'sha256_playbook':
                    result['sha256_playbook'] = experiment.sha256_playbook
                elif field == 'sha256_metadata':
                    result['sha256_metadata'] = experiment.sha256_metadata
                elif field == 'ulid':
                    result['ulid'] = experiment.id
                elif field == 'project_id':
                    result['project_id'] = experiment.project_id
                # Foreign key relationship fields
                elif field == 'environments':
                    result['environments'] = [env.name for env in experiment.environments if env] if hasattr(experiment, 'environments') else []
                elif field == 'environment_names':
                    result['environment_names'] = [env.name for env in experiment.environments if env] if hasattr(experiment, 'environments') else []
                elif field == 'environment_count':
                    result['environment_count'] = len(experiment.environments) if hasattr(experiment, 'environments') else 0
                elif field == 'runs_count':
                    result['runs_count'] = len(experiment.runs) if hasattr(experiment, 'runs') else 0
                elif field == 'runs':
                    result['runs'] = [run.id for run in experiment.runs] if hasattr(experiment, 'runs') else []
                elif field == 'tags':
                    result['tags'] = [tag.name for tag in experiment.tags] if hasattr(experiment, 'tags') else []
                elif field == 'abstract_tests':
                    result['abstract_tests'] = [test.name for test in experiment.abstract_tests] if hasattr(experiment, 'abstract_tests') else []
                elif field == 'test_count':
                    result['test_count'] = len(experiment.abstract_tests) if hasattr(experiment, 'abstract_tests') else 0
                else:
                    log.warning(f'Unknown field requested: {field}. Available: id, name, description, sha256, sha256_playbook, sha256_metadata, ulid, project_id, environments, environment_names, runs_count, tags, test_count')
            except AttributeError as e:
                log.warning(f"Could not access field '{field}': {e}")
                result[field] = None
        
        return result


def get_experiment_data(project_path: Path, experiment_ulid: str) -> dict | None:
    """Get full experiment data with relationships - convenience function for common case."""
    return get_experiment_by_ulid(project_path, experiment_ulid, fields=['id', 'name', 'description', 'sha256', 'sha256_playbook', 'sha256_metadata', 'ulid', 'environment_names', 'runs_count', 'test_count'])


def get_experiment_summary(project_path: Path, experiment_ulid: str) -> dict | None:
    """Get basic experiment info with key relationships - lighter version."""
    return get_experiment_by_ulid(project_path, experiment_ulid, fields=['id', 'name', 'description', 'ulid', 'environment_names'])


def get_experiment_with_relationships(project_path: Path, experiment_ulid: str) -> dict | None:
    """Get experiment with all relationships loaded."""
    return get_experiment_by_ulid(project_path, experiment_ulid, fields=['id', 'name', 'description', 'environments', 'runs_count', 'tags', 'test_count'])


def get_experiment_stats(project_path: Path, experiment_ulid: str) -> dict | None:
    """Get experiment statistics - counts only."""
    return get_experiment_by_ulid(project_path, experiment_ulid, fields=['id', 'name', 'environment_count', 'runs_count', 'test_count'])


def get_experiment_hashes(project_path: Path, environment_name: str, experiment_name: str) -> dict:
    with ExperimentApi(project_path) as api:
        experiment = api.get_experiment_by_project_and_name(project_path, experiment_name)
        if experiment is None:
            log.error('experiment not found')
            raise ValueError('experiment not found')
        return {
            'experiment': experiment.sha256,
            'playbook': experiment.sha256_playbook,
            'metadata': experiment.sha256_metadata,
        }


def get_experiment_run_count(project_path: Path, experiment_ulid: str, exclude_fake: bool = False) -> int:
    with ExperimentApi(project_path) as api:
        experiment = api.get_experiment_by_ulid(experiment_ulid)
        if experiment is None:
            log.error('experiment not found')
            raise ValueError('experiment not found')
        if exclude_fake:
            return len([run for run in experiment.runs if not run.fake])
        return len(experiment.runs)


def create_experiment(name: str, experiment_directory: ExperimentDirectory, project_path: Path = None, auto_commit: bool = True) -> str:
    # If project_path is not provided, derive it from the experiment directory path
    if project_path is None:
        # ExperimentDirectory path structure: <project>/experiments/<experiment_name>
        project_path = experiment_directory.path.parent.parent

    with ExperimentApi(project_path) as api:
        experiment = api.create_experiment(name, experiment_directory, auto_commit=auto_commit)
        return experiment.id


def remove_experiment(project_path: Path, experiment_ulid: str):
    with ExperimentApi(project_path) as api:
        api.remove_experiment_by_ulid(experiment_ulid)


def check_for_experiment_change(project_path: Path, experiment_ulid: str, sha256: str) -> bool:
    with ExperimentApi(project_path) as api:
        return not api.experiment_sha256_equals(experiment_ulid, sha256)


def get_environment_installations(environment_ulid: str):
    with EnvironmentDbApi() as api:
        return api.get_environment_installations(environment_ulid)


def get_environment_platform(environment_ulid: str):
    with EnvironmentDbApi() as api:
        return api.get_environment_platform(environment_ulid)


def get_environment_ulid(project_path: Path, experiment_name: str):
    with EnvironmentDbApi() as api:
        return api.get_environment(experiment_name, project_path.name).id if api.get_environment(experiment_name, project_path.name) else None


def get_environment_vagrant_box(environment_ulid: str):
    with EnvironmentDbApi() as api:
        return api.get_environment_vagrant_box(environment_ulid)


def update_experiment_run(experiment_run_ulid: str, experimentrun_directory: ExperimentRunDirectory) -> str:
    """
    Update experiment run with VM-specific data (path, logfiles, status).
    The experiment and environment should already be set via set_experiment_run_base_info().
    """
    # Get project_path from experimentrun_directory path structure
    # ExperimentRunDirectory path structure: project_path/run/experiment/timestamp
    project_path = experimentrun_directory.path.parent.parent.parent
    with ExperimentApi(project_path) as api:
        experiment_run = api.update_experiment_run(
            run_ulid=experiment_run_ulid,
            path=experimentrun_directory.path,
            logfile_adare=experimentrun_directory.adare_log_file,
            logfile_adarevm=experimentrun_directory.adarevm_log_file,
            status=StatusEnum.RUNNING,
        )
        return experiment_run.id


def initialize_experiment_run(project_path: Path, fake: bool = False):
    with ExperimentApi(project_path) as api:
        return api.initialize_experiment_run(fake).id

def set_experiment_run_base_info(experiment_run_ulid: str, experiment_name: str, environment_name: str, project_path: Path) -> str:
    """
    Set the basic experiment and environment information early in the process.
    This prevents orphaned experiment runs if the process is interrupted early.
    """
    with ExperimentApi(project_path) as api:
        environment = api.get_environment(environment_name, project_path.name)
        experiment = api.get_experiment(experiment_name, environment.id)
        experiment_run = api.set_experiment_run_base_info(
            run_ulid=experiment_run_ulid,
            experiment=experiment,
            environment_id=environment.id
        )
        return experiment_run.id

def remove_fake_experiment_run(project_path: Path, experiment_run_ulid: str):
    with ExperimentApi(project_path) as api:
        api.remove_fake_experiment_run(experiment_run_ulid)

def update_experiment_run_start(project_path: Path, experiment_run_ulid: str, timestamp: datetime):
    with ExperimentApi(project_path) as api:
        api.update_experiment_run_start(experiment_run_ulid, timestamp)

def update_experiment_run_end(project_path: Path, experiment_run_ulid: str, timestamp: datetime):
    with ExperimentApi(project_path) as api:
        api.update_experiment_run_end(experiment_run_ulid, timestamp)

def update_experiment_run_vm_instance(project_path: Path, experiment_run_ulid: str, vm_instance_id: str):
    with ExperimentApi(project_path) as api:
        api.update_experiment_run_vm_instance(experiment_run_ulid, vm_instance_id)


def get_experiment_testfunction_files(project_path: Path, environment_name: str,  experiment_name: str):
    testfunction_files = []
    with ExperimentApi(project_path) as api:
        experiment = api.get_experiment_by_project_and_name(project_path, experiment_name)
        for abs_test in experiment.abstract_tests:
            if abs_test.testfunction.file.name not in testfunction_files:
                testfunction_files.append(Path(abs_test.testfunction.file.path))
        return testfunction_files


def update_experiment_run_status(project_path: Path, experiment_run_ulid: str, status: int):
    with ExperimentApi(project_path) as api:
        api.update_experiment_run_status(experiment_run_ulid, status)


def get_experiment_environment(project_path: Path, environment_name: str,  experiment_name: str):
    with ExperimentApi(project_path) as api:
        # todo: fix
        experiment = api.get_experiment_by_project_and_name(project_path,  experiment_name)
        if experiment is None:
            log.error('experiment not found')
            raise ValueError('experiment not found')
        if len(experiment.environments) == 0:
            log.error('experiment has no environment')
            raise NoEnvironmentError(
                log,
                f'experiment {experiment} has no environment',
            )
        elif len(experiment.environments) > 1:
            raise MultipleEnvironmentsError(
                log,
                f'experiment {experiment} has multiple environments',
                possible_solutions=[
                    'specify the environment with -e <environment>'
                ]
            )
        return Path(experiment.environments[0].file)


def _find_project_path_by_run_ulid(experiment_run_ulid: str) -> Path | None:
    """
    Find project path by looking up experiment run ULID across all project databases.
    This is a fallback method when project_path is not readily available.
    """
    from adare.backend.project.database import get_all_projects
    from adare.database.api.experiment import ExperimentApi
    from adare.database.models.project_models import ExperimentRun

    projects = get_all_projects()
    log.debug(f"CLAUDE: Searching for experiment run {experiment_run_ulid} across {len(projects)} projects")

    for project_dict in projects:
        try:
            # Extract Path from project dictionary - get_all_projects() returns list[dict]
            project_path = Path(project_dict['path'])
            log.debug(f"CLAUDE: Checking project: {project_path}")

            with ExperimentApi(project_path) as api:
                # Check if this experiment run exists in this project database
                run = api._session.query(ExperimentRun).filter_by(id=experiment_run_ulid).first()
                if run:
                    log.info(f"CLAUDE: Found experiment run {experiment_run_ulid} in project {project_path}")
                    return project_path
        except Exception as e:
            # Continue searching if there's an error accessing this project database
            log.warning(f"CLAUDE: Error accessing project {project_dict.get('path', 'unknown')}: {e}")
            continue

    log.error(f"CLAUDE: Could not find experiment run {experiment_run_ulid} in any of {len(projects)} projects")
    return None


def update_stage_in_run(stage: Stage, experimentrun_ulid: str, stage_id: str, project_path: Path = None) -> int:
    """
    Update stage in run. If project_path is not provided, will attempt to find it.
    """
    if project_path is None:
        project_path = _find_project_path_by_run_ulid(experimentrun_ulid)
        if project_path is None:
            raise ValueError(f"Cannot find project for experiment run {experimentrun_ulid}")

    with StageDbApi(project_path) as db:
        return db.update_stage_in_run(stage, experimentrun_ulid, stage_id)


def sync_experiment(project_path: Path, ulid: str, remote_ulid: str, abstract_tests_ulids: dict, remote_url: str, is_published: bool):
    with ExperimentApi(project_path) as api:
        api.sync_experiment(ulid, remote_ulid, abstract_tests_ulids, remote_url, is_published)


def get_experiment_hash(project_path: Path, ulid: str):
    with ExperimentApi(project_path) as api:
        return api.get_experiment_by_ulid(ulid).sha256


def get_experiments_ulids(project_path: Path):
    with ExperimentApi(project_path) as api:
        return [
            experiment.id
            for experiment in api.get_experiments(project_path)
        ]

