
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import sys
import os

# Ensure project root is in path
sys.path.append(os.getcwd())

from adare.backend.environment.database import delete_environment

@pytest.fixture
def mock_dependencies():
    with patch('adare.backend.environment.database.EnvironmentDbApi') as mock_db_api, \
         patch('adare.backend.environment.database.vm_database', create=True) as mock_vm_db, \
         patch('adare.backend.environment.database.reference_manager') as mock_ref_mgr, \
         patch('adare.config.configdirectory.VMS_DIR') as mock_vms_dir:
        
        mock_db = mock_db_api.return_value.__enter__.return_value
        mock_ref_mgr.get_projects_using_environment.return_value = []
        
        yield {
            'db': mock_db,
            'vm_db': mock_vm_db,
            'vms_dir': mock_vms_dir
        }

def test_delete_environment_deletes_external_vm(mock_dependencies):
    """
    Reproduce bug: delete_environment deletes VM file even if it is external (not in VMS_DIR).
    """
    mock_db = mock_dependencies['db']
    mock_vms_dir = mock_dependencies['vms_dir']
    
    # Setup paths
    # Managed directory
    managed_dir = Path("/home/user/.adare/state/vms")
    mock_vms_dir.resolve.return_value = managed_dir
    
    # External VM file
    external_vm_path_str = "/home/user/downloads/my_vm.qcow2"
    external_vm_path = Path(external_vm_path_str)
    
    # Mock environment
    mock_env = MagicMock()
    mock_env.id = "env_1"
    mock_env.vm.id = "vm_1"
    mock_env.vm.file = external_vm_path_str
    
    mock_db.get_environment_by_ulid.return_value = mock_env
    
    # Mock that VM is not used by others
    # get_environments returns list of environments. 
    # Logic is: any(env.vm_id == vm_id for env in all_environments)
    # We return just this environment, so it will match itself, but we need to see how the logic works.
    # Logic in code:
    # all_environments = db.get_environments()
    # vm_still_in_use = any(env.vm_id == vm_id for env in all_environments)
    
    # Wait, if `all_environments` contains the current environment, `vm_still_in_use` will be True!
    # But `db.delete_environment(environment)` is called BEFORE VM cleanup check.
    # So `db.get_environments()` should NOT return the deleted environment if it simulates DB correctly.
    
    # Since we are mocking, we should ensure `db.get_environments()` does NOT return the deleted environment.
    mock_db.get_environments.return_value = [] # No environments left
    
    # Mock Path operations
    # We need to mock Path object creation or methods on the path instance used in the function
    # The code uses Path(environment.vm.file)
    
    with patch('pathlib.Path.exists', return_value=True), \
         patch('pathlib.Path.unlink') as mock_unlink, \
         patch('pathlib.Path.resolve') as mock_resolve, \
         patch('pathlib.Path.is_relative_to') as mock_is_relative_to:

        # Mock resolve to return absolute paths
        def resolve_side_effect():
            # This is tricky because resolve is called on self
            return external_vm_path
        
        # We can't easily mock resolve on specific instances created inside the function without more complex mocking.
        # However, for the reproduction, we assume the CURRENT implementation just calls unlink() without checking is_relative_to.
        
        # Force = True to trigger cleanup
        delete_environment("env_1", force=True)
        
        # Assert unlink was called (The Bug)
        # Note: logic in code:
        # if vm_file_path and vm_file_path.exists():
        #    try:
        #        vm_file_path.unlink()
        
        # Since we mocked exists=True, unlink should be called on the path object created from string.
        # unittest.mock.patch('pathlib.Path.unlink') patches the method on the class.
        
        mock_unlink.assert_called()
