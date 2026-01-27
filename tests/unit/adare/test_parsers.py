
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from adare.parsers import parse_metadata_file, parse_environment_file
from adare.exceptions import DataStructuringError
import cattrs

class TestParsers:
    @patch('adare.parsers.yaml_to_dict')
    @patch('adare.parsers.cattrs.structure')
    def test_parse_metadata_file_success(self, mock_structure, mock_yaml_to_dict, tmp_path):
        metadata_file = tmp_path / "metadata.yaml"
        metadata_file.touch()
        
        mock_yaml_to_dict.return_value = {"key": "value"}
        mock_metadata = MagicMock()
        mock_structure.return_value = mock_metadata
        
        result = parse_metadata_file(metadata_file)
        
        assert result == mock_metadata
        mock_yaml_to_dict.assert_called_once_with(metadata_file)
        # Note: can't easily check structure call arg 2 because it's a type import inside try/except

    @patch('adare.parsers.yaml_to_dict')
    def test_parse_metadata_file_empty(self, mock_yaml_to_dict, tmp_path):
        metadata_file = tmp_path / "metadata.yaml"
        metadata_file.touch()
        
        # yaml_to_dict might return None for empty file
        mock_yaml_to_dict.return_value = None
        
        # Should raise DataStructuringError because cattrs cannot structure empty dict into ExperimentMetadata
        # unless all fields are optional. Assuming ExperimentMetadata has required fields.
        # But wait, code does `json_dict = json_dict or {}`.
        # So it tries `cattrs.structure({}, ExperimentMetadata)`.
        # If ExperimentMetadata has required fields, this raises BaseValidationError.
        
        # Let's mock cattrs.structure to raise exception since we don't have ExperimentMetadata definition here easily
        with patch('adare.parsers.cattrs.structure', side_effect=cattrs.BaseValidationError("Missing fields", [Exception("dummy")], object)):
            with pytest.raises(DataStructuringError) as excinfo:
                parse_metadata_file(metadata_file)
            
            assert "parsing errors while parsing metadata file" in str(excinfo.value)

    @patch('adare.parsers.yaml_to_dict')
    def test_parse_metadata_file_validation_error(self, mock_yaml_to_dict, tmp_path):
        metadata_file = tmp_path / "metadata.yaml"
        metadata_file.touch()
        
        mock_yaml_to_dict.return_value = {"invalid": "data"}
        
        with patch('adare.parsers.cattrs.structure', side_effect=cattrs.BaseValidationError("Error", [Exception("dummy")], object)):
            with pytest.raises(DataStructuringError) as excinfo:
                parse_metadata_file(metadata_file)
            
            assert "parsing errors while parsing metadata file" in str(excinfo.value)

    @patch('adare.parsers.yaml_to_dict')
    @patch('adare.parsers.cattrs.structure')
    def test_parse_environment_file_success(self, mock_structure, mock_yaml_to_dict, tmp_path):
        env_file = tmp_path / "env.yaml"
        env_file.touch()
        
        mock_yaml_to_dict.return_value = {"env": "val"}
        mock_env = MagicMock()
        mock_structure.return_value = mock_env
        
        result = parse_environment_file(env_file)
        
        assert result == mock_env
        mock_yaml_to_dict.assert_called_once_with(env_file)

    @patch('adare.parsers.yaml_to_dict')
    def test_parse_environment_file_validation_error(self, mock_yaml_to_dict, tmp_path):
        env_file = tmp_path / "env.yaml"
        env_file.touch()
        
        mock_yaml_to_dict.return_value = {"inv": "alid"}
        
        with patch('adare.parsers.cattrs.structure', side_effect=cattrs.BaseValidationError("Error", [Exception("dummy")], object)):
            with pytest.raises(DataStructuringError) as excinfo:
                parse_environment_file(env_file)
            
        assert "parsing errors while parsing environment file" in str(excinfo.value)

    @patch('adare.parsers.yaml_to_dict')
    @patch('adare.parsers.cattrs.structure')
    def test_parse_environment_file_empty(self, mock_structure, mock_yaml_to_dict, tmp_path):
        env_file = tmp_path / "env.yaml"
        env_file.touch()
        
        mock_yaml_to_dict.return_value = None
        # Should structure empty dict
        mock_env = MagicMock()
        mock_structure.return_value = mock_env
        
        result = parse_environment_file(env_file)
        
        assert result == mock_env
        mock_structure.assert_called() # args unknown as EnvironmentMetadata is local import
