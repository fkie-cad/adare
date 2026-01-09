"""
Comprehensive unit tests for adare/database/utils/display_helpers.py
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from adare.database.utils.display_helpers import (
    get_current_project_name,
    get_smart_display_name,
    safe_get_sync_status,
    safe_get_os_info,
    safe_get_vm_info,
    safe_get_tags,
)


class TestGetCurrentProjectName:
    """Tests for get_current_project_name function."""

    def setup_method(self):
        """Clear the lru_cache before each test."""
        get_current_project_name.cache_clear()

    @patch('adare.backend.basics.determine_projectdirectory')
    def test_returns_project_name_when_found(self, mock_determine):
        """Test that project name is returned when project directory is found."""
        mock_path = Mock(spec=Path)
        mock_path.name = "my_project"
        mock_determine.return_value = mock_path

        result = get_current_project_name()

        assert result == "my_project"
        mock_determine.assert_called_once_with(None, silent=True)

    @patch('adare.backend.basics.determine_projectdirectory')
    def test_returns_none_when_project_not_found(self, mock_determine):
        """Test that None is returned when no project directory is found."""
        mock_determine.return_value = None

        result = get_current_project_name()

        assert result is None

    @patch('adare.backend.basics.determine_projectdirectory')
    def test_returns_none_on_exception(self, mock_determine):
        """Test that None is returned when an exception occurs."""
        mock_determine.side_effect = RuntimeError("Test error")

        result = get_current_project_name()

        assert result is None

    @patch('adare.backend.basics.determine_projectdirectory')
    def test_caches_result(self, mock_determine):
        """Test that the result is cached after first call."""
        mock_path = Mock(spec=Path)
        mock_path.name = "cached_project"
        mock_determine.return_value = mock_path

        # Call twice
        result1 = get_current_project_name()
        result2 = get_current_project_name()

        assert result1 == "cached_project"
        assert result2 == "cached_project"
        # Should only be called once due to caching
        mock_determine.assert_called_once()


class TestGetSmartDisplayName:
    """Tests for get_smart_display_name function."""

    def setup_method(self):
        """Clear the lru_cache before each test."""
        get_current_project_name.cache_clear()

    def test_environment_same_project_returns_name_only(self):
        """Test environment in same project returns just the name."""
        mock_env = Mock()
        mock_env.name = "env1"
        mock_env.dotnotation = "project1.env1"
        mock_env.project = Mock()
        mock_env.project.name = "project1"

        result = get_smart_display_name(mock_env, 'environment', current_project_name="project1")

        assert result == "env1"

    def test_environment_different_project_returns_dotnotation(self):
        """Test environment in different project returns full dotnotation."""
        mock_env = Mock()
        mock_env.name = "env1"
        mock_env.dotnotation = "project1.env1"
        mock_env.project = Mock()
        mock_env.project.name = "project1"

        result = get_smart_display_name(mock_env, 'environment', current_project_name="other_project")

        assert result == "project1.env1"

    def test_environment_no_current_project_returns_dotnotation(self):
        """Test environment with no current project returns full dotnotation."""
        mock_env = Mock()
        mock_env.name = "env1"
        mock_env.dotnotation = "project1.env1"
        mock_env.project = Mock()
        mock_env.project.name = "project1"

        result = get_smart_display_name(mock_env, 'environment', current_project_name=None)

        assert result == "project1.env1"

    def test_experiment_same_project_returns_name_only(self):
        """Test experiment in same project returns just the name."""
        mock_exp = Mock()
        mock_exp.name = "exp1"
        mock_project = Mock()
        mock_project.name = "project1"
        mock_env = Mock()
        mock_env.project = mock_project
        mock_exp.environments = [mock_env]

        result = get_smart_display_name(mock_exp, 'experiment', current_project_name="project1")

        assert result == "exp1"

    def test_experiment_different_project_returns_dotnotation(self):
        """Test experiment in different project returns full dotnotation."""
        mock_exp = Mock()
        mock_exp.name = "exp1"
        mock_project = Mock()
        mock_project.name = "project1"
        mock_env = Mock()
        mock_env.project = mock_project
        mock_exp.environments = [mock_env]

        result = get_smart_display_name(mock_exp, 'experiment', current_project_name="other_project")

        assert result == "project1.exp1"

    def test_experiment_no_environments_returns_name(self):
        """Test experiment with no environments returns just the name."""
        mock_exp = Mock()
        mock_exp.name = "exp1"
        mock_exp.environments = []

        result = get_smart_display_name(mock_exp, 'experiment', current_project_name="project1")

        assert result == "exp1"

    def test_experiment_no_current_project_returns_dotnotation(self):
        """Test experiment with no current project returns full dotnotation."""
        mock_exp = Mock()
        mock_exp.name = "exp1"
        mock_project = Mock()
        mock_project.name = "project1"
        mock_env = Mock()
        mock_env.project = mock_project
        mock_exp.environments = [mock_env]

        result = get_smart_display_name(mock_exp, 'experiment', current_project_name=None)

        assert result == "project1.exp1"

    def test_testfunction_same_project_returns_name_part(self):
        """Test testfunction in same project returns name without project prefix."""
        mock_tf = Mock()
        mock_tf.name = "test_func"
        mock_tf.dotnotation = "project1.module.test_func"

        result = get_smart_display_name(mock_tf, 'testfunction', current_project_name="project1")

        assert result == "module.test_func"

    def test_testfunction_different_project_returns_full_dotnotation(self):
        """Test testfunction in different project returns full dotnotation."""
        mock_tf = Mock()
        mock_tf.name = "test_func"
        mock_tf.dotnotation = "project1.module.test_func"

        result = get_smart_display_name(mock_tf, 'testfunction', current_project_name="other_project")

        assert result == "project1.module.test_func"

    def test_testfunction_no_dot_returns_name(self):
        """Test testfunction with no dot in dotnotation returns name."""
        mock_tf = Mock()
        mock_tf.name = "test_func"
        mock_tf.dotnotation = "test_func"

        result = get_smart_display_name(mock_tf, 'testfunction', current_project_name="project1")

        assert result == "test_func"

    def test_testfunction_no_current_project_returns_name(self):
        """Test testfunction with no current project returns name."""
        mock_tf = Mock()
        mock_tf.name = "test_func"
        mock_tf.dotnotation = "project1.test_func"

        result = get_smart_display_name(mock_tf, 'testfunction', current_project_name=None)

        assert result == "test_func"

    def test_unknown_type_returns_name(self):
        """Test unknown object type returns just the name."""
        mock_obj = Mock()
        mock_obj.name = "unknown_obj"
        mock_obj.dotnotation = "project1.unknown_obj"

        result = get_smart_display_name(mock_obj, 'unknown_type', current_project_name="project1")

        assert result == "unknown_obj"

    @patch('adare.database.utils.display_helpers.get_current_project_name')
    def test_detects_current_project_when_not_provided(self, mock_get_project):
        """Test that current project is detected when not provided."""
        mock_get_project.return_value = "detected_project"
        mock_env = Mock()
        mock_env.name = "env1"
        mock_env.dotnotation = "detected_project.env1"
        mock_env.project = Mock()
        mock_env.project.name = "detected_project"

        result = get_smart_display_name(mock_env, 'environment')

        assert result == "env1"
        mock_get_project.assert_called_once()


class TestSafeGetSyncStatus:
    """Tests for safe_get_sync_status function."""

    def test_returns_sync_status_when_available(self):
        """Test returns correct sync status when sync_metadata exists."""
        mock_obj = Mock()
        mock_obj.sync_metadata = Mock()
        mock_obj.sync_metadata.is_synced = True
        mock_obj.sync_metadata.needs_sync = False

        published, in_request = safe_get_sync_status(mock_obj)

        assert published is True
        assert in_request is False

    def test_returns_sync_status_needs_sync(self):
        """Test returns correct status when needs_sync is True."""
        mock_obj = Mock()
        mock_obj.sync_metadata = Mock()
        mock_obj.sync_metadata.is_synced = False
        mock_obj.sync_metadata.needs_sync = True

        published, in_request = safe_get_sync_status(mock_obj)

        assert published is False
        assert in_request is True

    def test_returns_false_when_no_sync_metadata(self):
        """Test returns (False, False) when no sync_metadata attribute."""
        mock_obj = Mock(spec=[])  # No sync_metadata attribute

        published, in_request = safe_get_sync_status(mock_obj)

        assert published is False
        assert in_request is False

    def test_returns_false_when_sync_metadata_is_none(self):
        """Test returns (False, False) when sync_metadata is None."""
        mock_obj = Mock()
        mock_obj.sync_metadata = None

        published, in_request = safe_get_sync_status(mock_obj)

        assert published is False
        assert in_request is False

    def test_returns_false_on_exception(self):
        """Test returns (False, False) when an exception occurs."""
        mock_obj = Mock()
        mock_obj.sync_metadata = Mock()
        # Make is_synced raise an exception
        type(mock_obj.sync_metadata).is_synced = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("Test error"))
        )

        published, in_request = safe_get_sync_status(mock_obj)

        assert published is False
        assert in_request is False

    def test_converts_truthy_values_to_bool(self):
        """Test that truthy values are converted to proper booleans."""
        mock_obj = Mock()
        mock_obj.sync_metadata = Mock()
        mock_obj.sync_metadata.is_synced = 1  # truthy but not True
        mock_obj.sync_metadata.needs_sync = "yes"  # truthy but not True

        published, in_request = safe_get_sync_status(mock_obj)

        assert published is True
        assert in_request is True
        assert isinstance(published, bool)
        assert isinstance(in_request, bool)


class TestSafeGetOsInfo:
    """Tests for safe_get_os_info function."""

    def test_returns_os_info_when_available(self):
        """Test returns correct OS info when osinfo exists."""
        mock_vm = Mock()
        mock_vm.osinfo = Mock()
        mock_vm.osinfo.__str__ = Mock(return_value="Windows 10 Professional")
        mock_vm.osinfo.os = "Windows"
        mock_vm.osinfo.distribution = "Professional"
        mock_vm.osinfo.version = "10"
        mock_vm.osinfo.language = "en-US"

        os_info_str, os_name, distribution, version, language = safe_get_os_info(mock_vm)

        assert os_info_str == "Windows 10 Professional"
        assert os_name == "Windows"
        assert distribution == "Professional"
        assert version == "10"
        assert language == "en-US"

    def test_returns_no_vm_when_vm_is_none(self):
        """Test returns 'No VM' when vm is None."""
        os_info_str, os_name, distribution, version, language = safe_get_os_info(None)

        assert os_info_str == "No VM"
        assert os_name == ""
        assert distribution == ""
        assert version == ""
        assert language == ""

    def test_returns_unknown_when_no_osinfo(self):
        """Test returns 'Unknown' when vm has no osinfo."""
        mock_vm = Mock(spec=[])  # No osinfo attribute

        os_info_str, os_name, distribution, version, language = safe_get_os_info(mock_vm)

        assert os_info_str == "Unknown"
        assert os_name == ""
        assert distribution == ""
        assert version == ""
        assert language == ""

    def test_returns_unknown_when_osinfo_is_none(self):
        """Test returns 'Unknown' when osinfo is None."""
        mock_vm = Mock()
        mock_vm.osinfo = None

        os_info_str, os_name, distribution, version, language = safe_get_os_info(mock_vm)

        assert os_info_str == "Unknown"
        assert os_name == ""
        assert distribution == ""
        assert version == ""
        assert language == ""

    def test_handles_partial_osinfo(self):
        """Test handles osinfo with some None values."""
        mock_vm = Mock()
        mock_vm.osinfo = Mock()
        mock_vm.osinfo.__str__ = Mock(return_value="Linux")
        mock_vm.osinfo.os = "Linux"
        mock_vm.osinfo.distribution = None
        mock_vm.osinfo.version = "5.0"
        mock_vm.osinfo.language = None

        os_info_str, os_name, distribution, version, language = safe_get_os_info(mock_vm)

        assert os_info_str == "Linux"
        assert os_name == "Linux"
        assert distribution == ""
        assert version == "5.0"
        assert language == ""

    def test_returns_unknown_on_exception(self):
        """Test returns 'Unknown' when an exception occurs."""
        mock_vm = Mock()
        # Make osinfo raise an exception when accessed
        type(mock_vm).osinfo = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("Test error"))
        )

        os_info_str, os_name, distribution, version, language = safe_get_os_info(mock_vm)

        assert os_info_str == "Unknown"
        assert os_name == ""
        assert distribution == ""
        assert version == ""
        assert language == ""


class TestSafeGetVmInfo:
    """Tests for safe_get_vm_info function."""

    def test_returns_vm_info_when_available(self):
        """Test returns correct VM info when vm exists."""
        mock_env = Mock()
        mock_env.vm = Mock()
        mock_env.vm.name = "test_vm"
        mock_env.vm.id = "vm-123"

        vm_name, vm_id = safe_get_vm_info(mock_env)

        assert vm_name == "test_vm"
        assert vm_id == "vm-123"

    def test_returns_no_vm_when_no_vm_attribute(self):
        """Test returns 'No VM' when env has no vm attribute."""
        mock_env = Mock(spec=[])  # No vm attribute

        vm_name, vm_id = safe_get_vm_info(mock_env)

        assert vm_name == "No VM"
        assert vm_id == ""

    def test_returns_no_vm_when_vm_is_none(self):
        """Test returns 'No VM' when vm is None."""
        mock_env = Mock()
        mock_env.vm = None

        vm_name, vm_id = safe_get_vm_info(mock_env)

        assert vm_name == "No VM"
        assert vm_id == ""

    def test_returns_no_vm_on_exception(self):
        """Test returns 'No VM' when an exception occurs."""
        mock_env = Mock()
        # Make vm raise an exception when accessed
        type(mock_env).vm = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("Test error"))
        )

        vm_name, vm_id = safe_get_vm_info(mock_env)

        assert vm_name == "No VM"
        assert vm_id == ""

    def test_handles_integer_vm_id(self):
        """Test handles integer VM id correctly."""
        mock_env = Mock()
        mock_env.vm = Mock()
        mock_env.vm.name = "test_vm"
        mock_env.vm.id = 42

        vm_name, vm_id = safe_get_vm_info(mock_env)

        assert vm_name == "test_vm"
        assert vm_id == 42


class TestSafeGetTags:
    """Tests for safe_get_tags function."""

    def test_returns_tag_names_when_available(self):
        """Test returns list of tag names when tags exist."""
        mock_obj = Mock()
        tag1 = Mock()
        tag1.name = "tag1"
        tag2 = Mock()
        tag2.name = "tag2"
        tag3 = Mock()
        tag3.name = "tag3"
        mock_obj.tags = [tag1, tag2, tag3]

        result = safe_get_tags(mock_obj)

        assert result == ["tag1", "tag2", "tag3"]

    def test_returns_empty_list_when_no_tags_attribute(self):
        """Test returns empty list when object has no tags attribute."""
        mock_obj = Mock(spec=[])  # No tags attribute

        result = safe_get_tags(mock_obj)

        assert result == []

    def test_returns_empty_list_when_tags_is_none(self):
        """Test returns empty list when tags is None."""
        mock_obj = Mock()
        mock_obj.tags = None

        result = safe_get_tags(mock_obj)

        assert result == []

    def test_returns_empty_list_when_tags_is_empty(self):
        """Test returns empty list when tags list is empty."""
        mock_obj = Mock()
        mock_obj.tags = []

        result = safe_get_tags(mock_obj)

        assert result == []

    def test_returns_empty_list_on_exception(self):
        """Test returns empty list when an exception occurs."""
        mock_obj = Mock()
        # Make tags raise an exception when iterated
        mock_obj.tags = Mock()
        mock_obj.tags.__iter__ = Mock(side_effect=RuntimeError("Test error"))

        result = safe_get_tags(mock_obj)

        assert result == []

    def test_handles_single_tag(self):
        """Test handles single tag correctly."""
        mock_obj = Mock()
        tag = Mock()
        tag.name = "single_tag"
        mock_obj.tags = [tag]

        result = safe_get_tags(mock_obj)

        assert result == ["single_tag"]


class TestEdgeCases:
    """Tests for edge cases and integration scenarios."""

    def setup_method(self):
        """Clear the lru_cache before each test."""
        get_current_project_name.cache_clear()

    def test_environment_without_project_attribute(self):
        """Test environment object without project attribute."""
        mock_env = Mock(spec=['name', 'dotnotation'])
        mock_env.name = "env1"
        mock_env.dotnotation = "project1.env1"

        result = get_smart_display_name(mock_env, 'environment', current_project_name="project1")

        # Should return dotnotation since hasattr(obj, 'project') fails
        assert result == "project1.env1"

    def test_sync_metadata_with_zero_values(self):
        """Test sync_metadata with 0 values (falsy but valid)."""
        mock_obj = Mock()
        mock_obj.sync_metadata = Mock()
        mock_obj.sync_metadata.is_synced = 0
        mock_obj.sync_metadata.needs_sync = 0

        published, in_request = safe_get_sync_status(mock_obj)

        assert published is False
        assert in_request is False

    def test_vm_with_empty_string_values(self):
        """Test VM info with empty string values."""
        mock_env = Mock()
        mock_env.vm = Mock()
        mock_env.vm.name = ""
        mock_env.vm.id = ""

        vm_name, vm_id = safe_get_vm_info(mock_env)

        assert vm_name == ""
        assert vm_id == ""

    def test_tags_with_empty_name(self):
        """Test tags where some have empty names."""
        mock_obj = Mock()
        tag1 = Mock()
        tag1.name = "valid_tag"
        tag2 = Mock()
        tag2.name = ""
        tag3 = Mock()
        tag3.name = "another_tag"
        mock_obj.tags = [tag1, tag2, tag3]

        result = safe_get_tags(mock_obj)

        assert result == ["valid_tag", "", "another_tag"]

    def test_experiment_with_multiple_environments(self):
        """Test experiment uses first environment for project detection."""
        mock_exp = Mock()
        mock_exp.name = "exp1"

        mock_project1 = Mock()
        mock_project1.name = "project1"
        mock_env1 = Mock()
        mock_env1.project = mock_project1

        mock_project2 = Mock()
        mock_project2.name = "project2"
        mock_env2 = Mock()
        mock_env2.project = mock_project2

        mock_exp.environments = [mock_env1, mock_env2]

        # Should use first environment's project
        result = get_smart_display_name(mock_exp, 'experiment', current_project_name="project1")
        assert result == "exp1"

        result2 = get_smart_display_name(mock_exp, 'experiment', current_project_name="project2")
        assert result2 == "project1.exp1"  # Still uses first env's project

    def test_testfunction_simple_dotnotation(self):
        """Test testfunction with simple project.name dotnotation."""
        mock_tf = Mock()
        mock_tf.name = "test_func"
        mock_tf.dotnotation = "project1.test_func"

        result = get_smart_display_name(mock_tf, 'testfunction', current_project_name="project1")

        assert result == "test_func"
