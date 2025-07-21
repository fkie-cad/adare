# external imports
from pathlib import Path

# internal imports
from adare.database.api.testfunction import TestfunctionDbApi
from adare.backend.testfunction.exceptions import TestfunctionUpdatedError


# configure logging
import logging
log = logging.getLogger(__name__)


def load_testfunction_file(project_path: Path, testfunction_file: Path, requirements_file: Path) -> int:
    with TestfunctionDbApi() as api:
        if not api.testfunction_file_obj_exists(testfunction_file):
            # create a new one
            return api.create_testfunction_file_obj(project_path, testfunction_file, requirements_file).id
        else:
            # update the existing one but only add new test - never change existing ones
            return api.update_testfunction_file_obj(testfunction_file, requirements_file).id


def remove_testfunction_file(testfunction_file: Path):
    with TestfunctionDbApi() as api:
        if not api.testfunction_file_obj_exists(testfunction_file):
            raise TestfunctionUpdatedError(
                log,
                message=f'Testfunction {testfunction_file} does not exist',
            )
        api.remove_testfunction_file_obj(testfunction_file)
        log.info(f'removed testfunction {testfunction_file}')
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
