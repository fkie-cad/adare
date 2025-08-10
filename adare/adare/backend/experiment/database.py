# external imports
from pathlib import Path
from datetime import datetime

# internal imports
from adare.database.models.experiment import Experiment
from adare.database.api.experiment import ExperimentApi
from adare.database.api.environment import EnvironmentDbApi
from adare.database.api.stage import StageDbApi
from adare.backend.experiment.directory import ExperimentDirectory, ExperimentRunDirectory
from adare.backend.experiment.exceptions import NoEnvironmentError, MultipleEnvironmentsError
from adare.types.stages import Stage
from adarelib.constants import StatusEnum

# configure logging
import logging
log = logging.getLogger(__name__)


def get_experiment_by_project_and_name(project_path: Path, experiment_name: str, trigger_error: bool = True) -> str | None:
    with ExperimentApi() as api:
        experiment = api.get_experiment_by_project_and_name(project_path, experiment_name)
        if experiment is None:
            if trigger_error:
                log.error('experiment not found')
            return None
        return experiment.ulid


def get_experiment_by_ulid(experiment_ulid: str, fields: list[str] = None) -> Experiment | dict | None:
    """
    Get experiment by ULID with intelligent relationship loading.
    
    Args:
        experiment_ulid: Experiment ULID
        fields: Optional list of fields to extract. If None, returns full object.
                Available fields: 'id', 'name', 'description', 'sha256', 'sha256_playbook', 
                'sha256_testset', 'sha256_metadata', 'ulid', 'project_id'
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
    
    with ExperimentApi() as api:
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
                elif field == 'sha256_testset':
                    result['sha256_testset'] = experiment.sha256_testset
                elif field == 'sha256_metadata':
                    result['sha256_metadata'] = experiment.sha256_metadata
                elif field == 'ulid':
                    result['ulid'] = experiment.ulid
                elif field == 'project_id':
                    result['project_id'] = experiment.project_id
                # Foreign key relationship fields
                elif field == 'environments':
                    result['environments'] = [env.name for env in experiment.environments] if hasattr(experiment, 'environments') else []
                elif field == 'environment_names':
                    result['environment_names'] = [env.name for env in experiment.environments] if hasattr(experiment, 'environments') else []
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
                    log.warning(f'Unknown field requested: {field}. Available: id, name, description, sha256, sha256_playbook, sha256_testset, sha256_metadata, ulid, project_id, environments, environment_names, runs_count, tags, test_count')
            except AttributeError as e:
                log.warning(f"Could not access field '{field}': {e}")
                result[field] = None
        
        return result


def get_experiment_data(experiment_ulid: str) -> dict | None:
    """Get full experiment data with relationships - convenience function for common case."""
    return get_experiment_by_ulid(experiment_ulid, fields=['id', 'name', 'description', 'sha256', 'sha256_playbook', 'sha256_testset', 'sha256_metadata', 'ulid', 'environment_names', 'runs_count', 'test_count'])


def get_experiment_summary(experiment_ulid: str) -> dict | None:
    """Get basic experiment info with key relationships - lighter version."""
    return get_experiment_by_ulid(experiment_ulid, fields=['id', 'name', 'description', 'ulid', 'environment_names'])


def get_experiment_with_relationships(experiment_ulid: str) -> dict | None:
    """Get experiment with all relationships loaded."""
    return get_experiment_by_ulid(experiment_ulid, fields=['id', 'name', 'description', 'environments', 'runs_count', 'tags', 'test_count'])


def get_experiment_stats(experiment_ulid: str) -> dict | None:
    """Get experiment statistics - counts only."""
    return get_experiment_by_ulid(experiment_ulid, fields=['id', 'name', 'environment_count', 'runs_count', 'test_count'])


def get_experiment_hashes(project_path: Path, environment_name: str, experiment_name: str) -> dict:
    with ExperimentApi() as api:
        experiment = api.get_experiment_by_project_and_name(project_path, experiment_name)
        if experiment is None:
            log.error('experiment not found')
            raise ValueError('experiment not found')
        return {
            'experiment': experiment.sha256,
            'playbook': experiment.sha256_playbook,
            'testset': experiment.sha256_testset,
            'metadata': experiment.sha256_metadata,
        }


def get_experiment_run_count(experiment_ulid: str) -> int:
    with ExperimentApi() as api:
        experiment = api.get_experiment_by_ulid(experiment_ulid)
        if experiment is None:
            log.error('experiment not found')
            raise ValueError('experiment not found')
        return len(experiment.runs)


def create_experiment(name: str, experiment_directory: ExperimentDirectory) -> str:
    with ExperimentApi() as api:
        experiment = api.create_experiment(name, experiment_directory)
        return experiment.ulid


def remove_experiment(experiment_ulid: str):
    with ExperimentApi() as api:
        api.remove_experiment_by_ulid(experiment_ulid)


def check_for_experiment_change(experiment_ulid: str, sha256: str) -> bool:
    with ExperimentApi() as api:
        return not api.experiment_sha256_equals(experiment_ulid, sha256)


def get_environment_installations(environment_ulid: str):
    with EnvironmentDbApi() as api:
        return api.get_environment_installations(environment_ulid)


def get_environment_platform(environment_ulid: str):
    with EnvironmentDbApi() as api:
        return api.get_environment_platform(environment_ulid)


def get_environment_ulid(project_path: Path, experiment_name: str):
    with EnvironmentDbApi() as api:
        return api.get_environment(experiment_name, project_path.name).ulid if api.get_environment(experiment_name, project_path.name) else None


def get_environment_vagrant_box(environment_ulid: str):
    with EnvironmentDbApi() as api:
        return api.get_environment_vagrant_box(environment_ulid)


def update_experiment_run(experiment_run_ulid: str, experimentrun_directory: ExperimentRunDirectory) -> str:
    """
    Update experiment run with VM-specific data (path, logfiles, status).
    The experiment and environment should already be set via set_experiment_run_base_info().
    """
    with ExperimentApi() as api:
        experiment_run = api.update_experiment_run(
            run_ulid=experiment_run_ulid,
            path=experimentrun_directory.path,
            logfile_vagrant=experimentrun_directory.vagrant_log_file,
            logfile_adarevm=experimentrun_directory.adarevm_log_file,
            status=StatusEnum.RUNNING,
        )
        return experiment_run.ulid


def initialize_experiment_run(fake: bool = False):
    with ExperimentApi() as api:
        return api.initialize_experiment_run(fake).ulid

def set_experiment_run_base_info(experiment_run_ulid: str, experiment_name: str, environment_name: str, project_name: str) -> str:
    """
    Set the basic experiment and environment information early in the process.
    This prevents orphaned experiment runs if the process is interrupted early.
    """
    with ExperimentApi() as api:
        environment = api.get_environment(environment_name, project_name)
        experiment = api.get_experiment(experiment_name, environment)
        experiment_run = api.set_experiment_run_base_info(
            run_ulid=experiment_run_ulid,
            experiment=experiment,
            environment=environment
        )
        return experiment_run.ulid

def remove_fake_experiment_run(experiment_run_ulid: str):
    with ExperimentApi() as api:
        api.remove_fake_experiment_run(experiment_run_ulid)

def update_experiment_run_start(experiment_run_ulid: str, timestamp: datetime):
    with ExperimentApi() as api:
        api.update_experiment_run_start(experiment_run_ulid, timestamp)

def update_experiment_run_end(experiment_run_ulid: str, timestamp: datetime):
    with ExperimentApi() as api:
        api.update_experiment_run_end(experiment_run_ulid, timestamp)


def get_experiment_testfunction_files(project_path: Path, environment_name: str,  experiment_name: str):
    testfunction_files = []
    with ExperimentApi() as api:
        experiment = api.get_experiment_by_project_and_name(project_path, experiment_name)
        for abs_test in experiment.abstract_tests:
            if abs_test.testfunction.file.name not in testfunction_files:
                testfunction_files.append(Path(abs_test.testfunction.file.path))
        return testfunction_files


def update_experiment_run_status(experiment_run_ulid: str, status: int):
    with ExperimentApi() as api:
        api.update_experiment_run_status(experiment_run_ulid, status)


def get_experiment_environment(project_path: Path, environment_name: str,  experiment_name: str):
    with ExperimentApi() as api:
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


def update_stage_in_run(stage: Stage, experimentrun_ulid: str, stage_id: str) -> int:
    with StageDbApi() as db:
        return db.update_stage_in_run(stage, experimentrun_ulid, stage_id)


def sync_experiment(ulid: str, remote_ulid: str, abstract_tests_ulids: dict, remote_url: str, is_published: bool):
    with ExperimentApi() as api:
        api.sync_experiment(ulid, remote_ulid, abstract_tests_ulids, remote_url, is_published)


def get_experiment_hash(ulid: str):
    with ExperimentApi() as api:
        return api.get_experiment_by_ulid(ulid).sha256


def get_experiments_ulids(project_path: Path):
    with ExperimentApi() as api:
        return [
            experiment.ulid
            for experiment in api.get_experiments(project_path)
        ]

