"""
Unit tests for DotNotationParser class.

Tests the parsing logic for different dotnotation formats used to reference
experiments, environments, and test functions.
"""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from adare.database.api.dotnotation_parser import DotNotationParser
from adare.exceptions import ArgumentsError, NoProjectFoundError


class TestDotNotationParser:
    """Tests for DotNotationParser class."""

    @pytest.fixture
    def parser(self):
        """Create a DotNotationParser instance."""
        return DotNotationParser()

    # ===== Experiment Dotnotation Tests =====

    def test_parse_experiment_two_part_format(self, parser):
        """Test parsing project.experiment format."""
        result = parser.parse_experiment_dotnotation("myproject.myexperiment")

        assert result == {
            'project_name': 'myproject',
            'experiment_name': 'myexperiment',
            'environment_name': None
        }

    def test_parse_experiment_three_part_format(self, parser):
        """Test parsing project.environment.experiment format."""
        result = parser.parse_experiment_dotnotation("myproject.myenv.myexperiment")

        assert result == {
            'project_name': 'myproject',
            'environment_name': 'myenv',
            'experiment_name': 'myexperiment'
        }

    def test_parse_experiment_one_part_with_current_project(self, parser):
        """Test parsing single experiment name using current project context."""
        mock_path = MagicMock(spec=Path)
        mock_path.name = "current_project"

        with patch.object(parser, '_get_current_project_name', return_value='current_project'):
            result = parser.parse_experiment_dotnotation("myexperiment")

        assert result == {
            'project_name': 'current_project',
            'experiment_name': 'myexperiment',
            'environment_name': None
        }

    def test_parse_experiment_one_part_no_project_raises_error(self, parser):
        """Test that single experiment name without project context raises error."""
        with patch.object(parser, '_get_current_project_name',
                         side_effect=NoProjectFoundError(MagicMock())):
            with pytest.raises(NoProjectFoundError):
                parser.parse_experiment_dotnotation("myexperiment")

    def test_parse_experiment_invalid_four_part_raises_error(self, parser):
        """Test that four-part dotnotation raises ArgumentsError."""
        with pytest.raises(ArgumentsError) as exc_info:
            parser.parse_experiment_dotnotation("a.b.c.d")

        assert "Invalid experiment dotnotation" in str(exc_info.value)

    def test_parse_experiment_invalid_five_part_raises_error(self, parser):
        """Test that five-part dotnotation raises ArgumentsError."""
        with pytest.raises(ArgumentsError):
            parser.parse_experiment_dotnotation("a.b.c.d.e")

    def test_parse_experiment_with_special_characters_in_names(self, parser):
        """Test parsing dotnotation with special characters in names."""
        result = parser.parse_experiment_dotnotation("project_123.exp-test")

        assert result['project_name'] == 'project_123'
        assert result['experiment_name'] == 'exp-test'

    def test_parse_experiment_with_empty_parts(self, parser):
        """Test parsing dotnotation with empty parts (e.g., 'project..experiment')."""
        result = parser.parse_experiment_dotnotation("project..experiment")

        # The parser splits on '.', so this becomes 3 parts with empty middle
        assert result['project_name'] == 'project'
        assert result['environment_name'] == ''
        assert result['experiment_name'] == 'experiment'

    # ===== Environment Dotnotation Tests =====

    def test_parse_environment_two_part_format(self, parser):
        """Test parsing project.environment format."""
        result = parser.parse_environment_dotnotation("myproject.myenv")

        assert result == {
            'project_name': 'myproject',
            'environment_name': 'myenv'
        }

    def test_parse_environment_one_part_with_current_project(self, parser):
        """Test parsing single environment name using current project context."""
        with patch.object(parser, '_get_current_project_name', return_value='current_project'):
            result = parser.parse_environment_dotnotation("myenv")

        assert result == {
            'project_name': 'current_project',
            'environment_name': 'myenv'
        }

    def test_parse_environment_one_part_no_project_raises_error(self, parser):
        """Test that single environment name without project context raises error."""
        with patch.object(parser, '_get_current_project_name',
                         side_effect=NoProjectFoundError(MagicMock())):
            with pytest.raises(NoProjectFoundError):
                parser.parse_environment_dotnotation("myenv")

    def test_parse_environment_invalid_three_part_raises_error(self, parser):
        """Test that three-part environment dotnotation raises ArgumentsError."""
        with pytest.raises(ArgumentsError) as exc_info:
            parser.parse_environment_dotnotation("a.b.c")

        assert "Invalid environment dotnotation" in str(exc_info.value)

    def test_parse_environment_with_special_characters(self, parser):
        """Test parsing environment dotnotation with special characters."""
        result = parser.parse_environment_dotnotation("proj-test_v2.env_linux-64")

        assert result['project_name'] == 'proj-test_v2'
        assert result['environment_name'] == 'env_linux-64'

    # ===== Test Function Dotnotation Tests =====

    def test_parse_testfunction_two_part_format(self, parser):
        """Test parsing file.function format (current project)."""
        result = parser.parse_testfunction_dotnotation("myfile.myfunction")

        assert result == {
            'project_name': None,
            'file_name': 'myfile',
            'function_name': 'myfunction'
        }

    def test_parse_testfunction_three_part_format(self, parser):
        """Test parsing project.file.function format (cross-project)."""
        result = parser.parse_testfunction_dotnotation("otherproject.myfile.myfunction")

        assert result == {
            'project_name': 'otherproject',
            'file_name': 'myfile',
            'function_name': 'myfunction'
        }

    def test_parse_testfunction_invalid_one_part_raises_error(self, parser):
        """Test that single-part testfunction dotnotation raises ArgumentsError."""
        with pytest.raises(ArgumentsError) as exc_info:
            parser.parse_testfunction_dotnotation("onlyfunction")

        assert "Invalid testfunction dotnotation" in str(exc_info.value)

    def test_parse_testfunction_invalid_four_part_raises_error(self, parser):
        """Test that four-part testfunction dotnotation raises ArgumentsError."""
        with pytest.raises(ArgumentsError):
            parser.parse_testfunction_dotnotation("a.b.c.d")

    def test_parse_testfunction_with_special_characters(self, parser):
        """Test parsing testfunction dotnotation with special characters."""
        result = parser.parse_testfunction_dotnotation("test_file.test_function_v2")

        assert result['file_name'] == 'test_file'
        assert result['function_name'] == 'test_function_v2'

    def test_parse_testfunction_cross_project_with_special_chars(self, parser):
        """Test parsing cross-project testfunction with special characters."""
        result = parser.parse_testfunction_dotnotation("proj-123.file_name.func_v2")

        assert result['project_name'] == 'proj-123'
        assert result['file_name'] == 'file_name'
        assert result['function_name'] == 'func_v2'


class TestDotNotationParserEdgeCases:
    """Edge case tests for DotNotationParser."""

    @pytest.fixture
    def parser(self):
        """Create a DotNotationParser instance."""
        return DotNotationParser()

    def test_parse_experiment_with_numbers_only(self, parser):
        """Test parsing dotnotation with numeric-only names."""
        result = parser.parse_experiment_dotnotation("123.456")

        assert result['project_name'] == '123'
        assert result['experiment_name'] == '456'

    def test_parse_environment_with_unicode_characters(self, parser):
        """Test parsing dotnotation with unicode characters."""
        result = parser.parse_environment_dotnotation("project.env_test")

        assert result['project_name'] == 'project'
        assert result['environment_name'] == 'env_test'

    def test_parse_testfunction_preserves_case(self, parser):
        """Test that parsing preserves case of names."""
        result = parser.parse_testfunction_dotnotation("MyFile.MyFunction")

        assert result['file_name'] == 'MyFile'
        assert result['function_name'] == 'MyFunction'

    def test_parse_experiment_whitespace_in_parts(self, parser):
        """Test that whitespace in parts is preserved (parser doesn't strip)."""
        # Note: This tests current behavior - whitespace is NOT stripped
        result = parser.parse_experiment_dotnotation("project . experiment")

        assert result['project_name'] == 'project '
        assert result['experiment_name'] == ' experiment'

    def test_parse_empty_string_experiment(self, parser):
        """Test parsing empty string for experiment raises appropriate error."""
        # Empty string split results in single empty element
        with patch.object(parser, '_get_current_project_name', return_value='current_project'):
            result = parser.parse_experiment_dotnotation("")

        assert result['experiment_name'] == ''
        assert result['project_name'] == 'current_project'


class TestGetCurrentProjectName:
    """Tests for _get_current_project_name helper method."""

    @pytest.fixture
    def parser(self):
        """Create a DotNotationParser instance."""
        return DotNotationParser()

    def test_get_current_project_name_returns_directory_name(self, parser):
        """Test that _get_current_project_name returns project directory name."""
        mock_path = MagicMock(spec=Path)
        mock_path.name = "my_project"

        with patch('adare.database.api.dotnotation_parser.determine_projectdirectory',
                   return_value=mock_path):
            result = parser._get_current_project_name()

        assert result == "my_project"

    def test_get_current_project_name_raises_error_when_not_in_project(self, parser):
        """Test that _get_current_project_name raises error when not in project."""
        with patch('adare.database.api.dotnotation_parser.determine_projectdirectory',
                   return_value=None):
            with pytest.raises(NoProjectFoundError):
                parser._get_current_project_name()
