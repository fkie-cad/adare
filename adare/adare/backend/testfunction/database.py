# external imports
from pathlib import Path

# internal imports
from adare.database.api.testfunction import TestfunctionDbApi
from adare.backend.testfunction.exceptions import TestfunctionUpdatedError
from adare.database.models.global_models import TestFunctionFile


# configure logging
import logging
log = logging.getLogger(__name__)


def load_testfunction_file(project_path: Path, testfunction_file: Path, requirements_file: Path) -> int:
    with TestfunctionDbApi() as api:
        # Check if testfunction file already exists globally by name
        existing_file = api._session.query(TestFunctionFile).filter(
            TestFunctionFile.name == testfunction_file.stem).first()
        if existing_file:
            # Testfunctions are global - use existing file
            log.debug(f'Using existing global testfunction file: {testfunction_file.name}')
            return existing_file.id
        else:
            # Create a new testfunction file
            return api.create_testfunction_file_obj(project_path, testfunction_file, requirements_file).id


def remove_testfunction_file(name: str):
    """Remove a testfunction file by name (e.g., 'xml', 'json', 'csv')."""
    with TestfunctionDbApi() as api:
        if not api.testfunction_file_obj_exists_by_name(name):
            raise TestfunctionUpdatedError(
                log,
                message=f'Testfunction file "{name}" does not exist',
            )
        api.remove_testfunction_file_obj_by_name(name)
        log.info(f'removed testfunction file "{name}"')
        return True
    return False


def list_testfunctions(fields: list[str] = None) -> list:
    """
    List all testfunctions.
    
    Args:
        fields: Optional list of fields to extract. If None, returns full objects.
                Available fields depend on the testfunction model structure.
    
    Returns:
        list: Testfunction objects or data dictionaries
    """
    with TestfunctionDbApi() as api:
        testfunctions = api.get_testfunctions_by_file()
        
        # Return full objects for backward compatibility
        if fields is None:
            return testfunctions
        
        # Extract requested fields from each testfunction
        result = []
        for tf in testfunctions:
            tf_data = {}
            for field in fields:
                if field == 'id':
                    tf_data['id'] = getattr(tf, 'id', None)
                elif field == 'name':
                    tf_data['name'] = getattr(tf, 'name', None)
                elif field == 'description':
                    tf_data['description'] = getattr(tf, 'description', None)
                elif field == 'file_path':
                    tf_data['file_path'] = getattr(tf, 'file_path', None)
                elif field == 'dotnotation':
                    tf_data['dotnotation'] = getattr(tf, 'dotnotation', None)
                else:
                    log.warning(f'Unknown field requested: {field}. Available: id, name, description, file_path, dotnotation')
            result.append(tf_data)
        
        return result


def testfunction_exists(name: str):
    with TestfunctionDbApi() as api:
        return api.testfunction_exists(name)


def testfunction_file_exists(name: str):
    """Check if a testfunction file exists by name (e.g., 'xml', 'json', 'csv')."""
    with TestfunctionDbApi() as api:
        return api.testfunction_file_obj_exists_by_name(name)


def get_testfunction_file_hash(testfunction_id: int):
    with TestfunctionDbApi() as api:
        return api.get_testfunction_file_hash(testfunction_id)


def sync_testfunction_file(testfunction_id: int, remote_id: int, remote_url: str, is_published: bool):
    with TestfunctionDbApi() as api:
        api.sync_testfunction_file(testfunction_id, remote_id, remote_url, is_published)


def get_testfunction_files_ids(project_path: Path = None):
    """Get list of testfunction file IDs - safe from DetachedInstanceError."""
    with TestfunctionDbApi() as api:
        return [
            testfunction.id for testfunction in api.get_testfunction_files(project_path)
        ]


def get_testfunction_files_data(project_path: Path = None, fields: list[str] = None) -> list[dict]:
    """
    Get testfunction files data with flexible field extraction.

    Args:
        project_path: Optional project path filter
        fields: Optional list of fields to extract

    Returns:
        list[dict]: List of testfunction file data dictionaries
    """
    with TestfunctionDbApi() as api:
        testfunction_files = api.get_testfunction_files(project_path)

        # Default fields if none specified
        if fields is None:
            fields = ['id', 'name', 'path', 'description']

        result = []
        for tf_file in testfunction_files:
            tf_data = {}
            for field in fields:
                if field == 'id':
                    tf_data['id'] = getattr(tf_file, 'id', None)
                elif field == 'name':
                    tf_data['name'] = getattr(tf_file, 'name', None)
                elif field == 'path':
                    tf_data['path'] = getattr(tf_file, 'path', None)
                elif field == 'description':
                    tf_data['description'] = getattr(tf_file, 'description', None)
                elif field == 'sha256hash':
                    tf_data['sha256hash'] = getattr(tf_file, 'sha256hash', None)
                elif field == 'requirements_path':
                    tf_data['requirements_path'] = getattr(tf_file, 'requirements_path', None)
                else:
                    log.warning(f'Unknown field requested: {field}. Available: id, name, path, description, sha256hash, requirements_path')
            result.append(tf_data)

        return result


def get_testfunction_usage(testfunction_name: str) -> dict:
    """
    Get usage information for a testfunction file - which experiments and runs use it across ALL projects.

    Args:
        testfunction_name: Name of the testfunction file to check (e.g., 'xml', 'json', 'csv')

    Returns:
        dict: Usage information with 'exists', 'experiments', 'runs', 'can_safely_delete', 'projects_affected' keys
    """
    from adare.database.models.global_models import TestFunctionFile, TestFunction, Project
    from adare.database.models.project_models import AbstractTest, Experiment, ExperimentRun
    from adare.database.api.base import ProjectDatabaseApi
    from pathlib import Path

    with TestfunctionDbApi() as api:
        # Find the testfunction file in global database
        testfunction_file = api._session.query(TestFunctionFile).filter(
            TestFunctionFile.name == testfunction_name).first()

        if not testfunction_file:
            return {
                'exists': False,
                'experiments': [],
                'runs': [],
                'can_safely_delete': True,
                'projects_affected': []
            }

        # Get all testfunctions in this file
        testfunction_ids = [tf.id for tf in testfunction_file.test_functions]

        # Get all projects from global database
        all_projects = api._session.query(Project).all()

        all_experiments = []
        all_runs = []
        projects_affected = []

        # Check each project's database for usage
        for project in all_projects:
            project_path = Path(project.path)

            try:
                # Connect to project-specific database
                with ProjectDatabaseApi(project_path) as project_api:
                    # Find abstract tests using any testfunction from this file
                    abstract_tests = project_api._session.query(AbstractTest).filter(
                        AbstractTest.testfunction_id.in_(testfunction_ids)).all()

                    if not abstract_tests:
                        continue  # No usage in this project

                    # Track that this project is affected
                    if project.name not in [p['name'] for p in projects_affected]:
                        projects_affected.append({'name': project.name, 'path': project.path})

                    for abstract_test in abstract_tests:
                        # Find experiments using this abstract test
                        test_experiments = project_api._session.query(Experiment).filter(
                            Experiment.abstract_tests.contains(abstract_test)).all()

                        for experiment in test_experiments:
                            exp_info = {
                                'id': experiment.id,
                                'name': experiment.name,
                                'project': project.name
                            }
                            if exp_info not in all_experiments:
                                all_experiments.append(exp_info)

                            # Find runs for this experiment
                            experiment_runs = project_api._session.query(ExperimentRun).filter(
                                ExperimentRun.experiment_id == experiment.id).all()

                            for run in experiment_runs:
                                all_runs.append({
                                    'id': run.id,
                                    'experiment_name': experiment.name,
                                    'project': project.name
                                })

            except Exception as e:
                log.warning(f'Could not check project {project.name} at {project.path}: {e}')
                continue

        return {
            'exists': True,
            'testfunction_file_id': testfunction_file.id,
            'experiments': all_experiments,
            'runs': all_runs,
            'can_safely_delete': len(all_runs) == 0,
            'projects_affected': projects_affected
        }


def delete_experiment_runs_for_testfunction(testfunction_name: str) -> int:
    """
    Delete all experiment runs that use the specified testfunction.

    Args:
        testfunction_name: Name of the testfunction

    Returns:
        int: Number of runs deleted
    """
    usage = get_testfunction_usage(testfunction_name)

    if not usage['exists'] or not usage['runs']:
        return 0

    with TestfunctionDbApi() as api:
        from adare.database.models.project_models import ExperimentRun

        deleted_count = 0
        for run_info in usage['runs']:
            run = api._session.query(ExperimentRun).filter(
                ExperimentRun.id == run_info['id']).first()
            if run:
                api._session.delete(run)
                deleted_count += 1

        api._session.commit()
        log.info(f'Deleted {deleted_count} experiment runs for testfunction {testfunction_name}')

        return deleted_count


def can_safely_update_testfunction(testfunction_name: str) -> bool:
    """
    Check if a testfunction can be safely updated without affecting experiment runs.

    Args:
        testfunction_name: Name of the testfunction to check

    Returns:
        bool: True if safe to update, False if it would affect existing runs
    """
    usage = get_testfunction_usage(testfunction_name)
    return usage['can_safely_delete']
