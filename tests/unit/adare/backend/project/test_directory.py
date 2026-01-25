
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from adare.backend.project.directory import ProjectDirectory
from adare.backend.project.exceptions import ProjectDirectoryCreationError

@pytest.fixture
def project_path(tmp_path):
    return tmp_path / "test_project"

@pytest.fixture
def project_dir(project_path):
    return ProjectDirectory(project_path)

class TestProjectDirectory:

    def test_properties(self, project_dir, project_path):
        assert project_dir.path == project_path
        assert project_dir.experiments == project_path / 'experiments'
        assert project_dir.vm_runtime == project_path / 'vm_runtime'
        assert project_dir.shared == project_path / 'shared'

    def test_create_success(self, project_dir):
        project_dir.create()
        assert project_dir.path.exists()
        assert project_dir.experiments.exists()
        assert project_dir.shared.exists()
        assert project_dir.vm_runtime.exists()

    def test_create_failure(self, project_dir):
        # Simulate OS error
        with patch.object(Path, 'mkdir', side_effect=OSError("Permission denied")):
            with pytest.raises(ProjectDirectoryCreationError):
                project_dir.create()

    def test_remove_success(self, project_dir):
        project_dir.create()
        assert project_dir.path.exists()
        project_dir.remove()
        assert not project_dir.path.exists()

    def test_exists(self, project_dir):
        assert not project_dir.exists()
        project_dir.create()
        assert project_dir.exists()

    def test_get_environment_hash_invalid_path(self, project_dir):
        with pytest.raises(ValueError):
             # /tmp/env is likely not in global ENVIRONMENTS_DIR
             project_dir.get_environment_hash(Path("/tmp/env.yml"))

    @patch('adare.backend.project.directory.download')
    @patch('shutil.unpack_archive')
    def test_download_tool(self, mock_unpack, mock_download, project_dir):
        project_dir.create()
        url = "http://example.com/tool.zip"
        
        # Side effect: download creates the file
        def side_effect(url, file, quiet):
            file.touch()
            
        mock_download.side_effect = side_effect
        
        project_dir.download_tool(url, zipped=True)
        
        mock_download.assert_called_once()
        mock_unpack.assert_called_once()
        # File should be unlinked after unzip
        assert not (project_dir.shared_tools / "tool.zip").exists()
