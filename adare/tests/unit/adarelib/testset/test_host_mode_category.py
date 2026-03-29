"""Tests for HostModeCategory enum and BasicTest ClassVar integration."""

import attrs
from typing import ClassVar, Optional

from adarelib.testset.basictest import BasicTest, Parameter, HostModeCategory


class TestHostModeCategoryEnum:
    """Test HostModeCategory enum definition."""

    def test_has_all_five_values(self):
        """HostModeCategory must have exactly 5 members."""
        assert len(HostModeCategory) == 5

    def test_file_based_value(self):
        assert HostModeCategory.FILE_BASED == "file_based"

    def test_file_content_value(self):
        assert HostModeCategory.FILE_CONTENT == "file_content"

    def test_qga_probe_value(self):
        assert HostModeCategory.QGA_PROBE == "qga_probe"

    def test_host_native_value(self):
        assert HostModeCategory.HOST_NATIVE == "host_native"

    def test_agent_only_value(self):
        assert HostModeCategory.AGENT_ONLY == "agent_only"

    def test_is_str_enum(self):
        """HostModeCategory is a str enum (serializable via str())."""
        for member in HostModeCategory:
            assert isinstance(member, str)
            assert isinstance(member.value, str)

    def test_string_comparison(self):
        """String comparisons work because it's a str enum."""
        assert HostModeCategory.FILE_BASED == "file_based"
        assert "file_based" == HostModeCategory.FILE_BASED

    def test_json_serializable(self):
        """Values can be serialized to JSON strings."""
        import json
        for member in HostModeCategory:
            serialized = json.dumps(member.value)
            assert json.loads(serialized) == member.value


class TestBasicTestHostModeCategory:
    """Test HostModeCategory ClassVar on BasicTest."""

    def test_default_is_agent_only(self):
        """BasicTest default host_mode_category is AGENT_ONLY."""
        assert BasicTest.host_mode_category == HostModeCategory.AGENT_ONLY

    def test_classvar_not_instance_attribute(self):
        """host_mode_category is a ClassVar, not an instance attribute."""
        # attrs.define excludes ClassVar fields from __init__
        @attrs.define
        class DummyParam(Parameter):
            dst: str

        @attrs.define
        class DummyTest(BasicTest):
            name: str
            parameter: DummyParam
            description: Optional[str] = ''
            variable_metadata: Optional[dict] = None

        instance = DummyTest(
            name='test1',
            parameter=DummyParam(dst='/tmp/test'),
        )

        # ClassVar should be accessible on the class
        assert DummyTest.host_mode_category == HostModeCategory.AGENT_ONLY

        # Should also be accessible on the instance (via class lookup)
        assert instance.host_mode_category == HostModeCategory.AGENT_ONLY

        # But it's NOT in the attrs fields list
        field_names = [f.name for f in attrs.fields(DummyTest)]
        assert 'host_mode_category' not in field_names

    def test_subclass_with_custom_category(self):
        """Subclassing BasicTest with custom category preserves it."""
        @attrs.define
        class DummyParam(Parameter):
            dst: str

        @attrs.define
        class FileBased(BasicTest):
            host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.FILE_BASED
            name: str
            parameter: DummyParam
            description: Optional[str] = ''
            variable_metadata: Optional[dict] = None

        assert FileBased.host_mode_category == HostModeCategory.FILE_BASED

        # BasicTest default should remain unchanged
        assert BasicTest.host_mode_category == HostModeCategory.AGENT_ONLY

    def test_subclass_inherits_default(self):
        """A subclass without explicit override inherits AGENT_ONLY."""
        @attrs.define
        class DummyParam(Parameter):
            dst: str

        @attrs.define
        class InheritedTest(BasicTest):
            name: str
            parameter: DummyParam
            description: Optional[str] = ''
            variable_metadata: Optional[dict] = None

        assert InheritedTest.host_mode_category == HostModeCategory.AGENT_ONLY

    def test_multiple_subclasses_independent(self):
        """Different subclasses can have different categories without interfering."""
        @attrs.define
        class DummyParam(Parameter):
            dst: str

        @attrs.define
        class FileTest(BasicTest):
            host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.FILE_BASED
            name: str
            parameter: DummyParam
            description: Optional[str] = ''
            variable_metadata: Optional[dict] = None

        @attrs.define
        class ProbeTest(BasicTest):
            host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.QGA_PROBE
            name: str
            parameter: DummyParam
            description: Optional[str] = ''
            variable_metadata: Optional[dict] = None

        assert FileTest.host_mode_category == HostModeCategory.FILE_BASED
        assert ProbeTest.host_mode_category == HostModeCategory.QGA_PROBE
        assert BasicTest.host_mode_category == HostModeCategory.AGENT_ONLY

    def test_getattr_on_type(self):
        """getattr(type(instance), 'host_mode_category', ...) works correctly."""
        @attrs.define
        class DummyParam(Parameter):
            dst: str

        @attrs.define
        class FileTest(BasicTest):
            host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.FILE_CONTENT
            name: str
            parameter: DummyParam
            description: Optional[str] = ''
            variable_metadata: Optional[dict] = None

        instance = FileTest(
            name='test1',
            parameter=DummyParam(dst='/tmp/test'),
        )

        # This is the pattern used by _get_test_category
        category = getattr(type(instance), 'host_mode_category', HostModeCategory.AGENT_ONLY)
        assert category == HostModeCategory.FILE_CONTENT

    def test_getattr_fallback_for_missing(self):
        """getattr with default returns AGENT_ONLY for classes without the attribute."""

        class PlainClass:
            pass

        category = getattr(PlainClass, 'host_mode_category', HostModeCategory.AGENT_ONLY)
        assert category == HostModeCategory.AGENT_ONLY
