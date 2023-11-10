# external imports
import yaml
import attr
from typing import Optional

# configure logging
import logging

log = logging.getLogger(__name__)


@attr.define
class ComparisonResult:
    success: bool
    details: Optional[str] = attr.Factory(str)
    additional_information: dict = attr.Factory(dict)
    exception: Optional[Exception] = None


class YamlCustomTag(yaml.YAMLObject):
    string: str

    def set_variables(self, variables: dict):
        pass


class YamlString(YamlCustomTag):
    yaml_tag = u'!s'

    def __init__(self, string: str):
        self.string = string

    def __repr__(self):
        return f'{self.string}'

    @classmethod
    def from_yaml(cls, loader: yaml.SafeLoader, node: yaml.nodes.MappingNode):
        return YamlString(node.value)

    @classmethod
    def to_yaml(cls, dumper, data):
        return dumper.represent_scalar(cls.yaml_tag, data.string)


class YamlPath(YamlCustomTag):
    yaml_tag = u'!path'

    def __init__(self, string: str):
        self.string = string

    def __repr__(self):
        return f'{self.string}'

    @classmethod
    def from_yaml(cls, loader: yaml.SafeLoader, node: yaml.nodes.MappingNode):
        return YamlString(node.value)

    @classmethod
    def to_yaml(cls, dumper, data):
        return dumper.represent_scalar(cls.yaml_tag, data.string)


class YamlTimestamp(YamlCustomTag):
    yaml_tag = u'!timestamp'

    def __init__(self, timestamp, timestamp_format_comparison=None, timestamp_format_in_entry=None, tolerance=1):
        self.string = timestamp
        self.timestamp_format_comparison = timestamp_format_comparison
        self.timestamp_format_in_entry = timestamp_format_in_entry
        self.tolerance = tolerance

    def __repr__(self):
        return f'{self.string}'

    @classmethod
    def from_yaml(cls, loader: yaml.SafeLoader, node: yaml.nodes.MappingNode):
        return YamlTimestamp(**loader.construct_mapping(node))

    @classmethod
    def to_yaml(cls, dumper, data):
        return dumper.represent_scalar(cls.yaml_tag, data.string)


class YamlRegexString(YamlCustomTag):
    yaml_tag = u'!re'

    def __init__(self, string: str):
        self.string = string

    def __repr__(self):
        return f'{self.string}'

    @classmethod
    def from_yaml(cls, loader: yaml.SafeLoader, node: yaml.nodes.MappingNode):
        return YamlRegexString(node.value)

    @classmethod
    def to_yaml(cls, dumper, data):
        return dumper.represent_scalar(cls.yaml_tag, data.string)


class YamlRegexStringAll(YamlRegexString):
    yaml_tag = u'!reALL'

    def __init__(self):
        super().__init__('.*')

    def __repr__(self):
        return f'{self.string}'

    @classmethod
    def from_yaml(cls, loader: yaml.SafeLoader, node: yaml.nodes.MappingNode):
        return YamlRegexStringAll()

    @classmethod
    def to_yaml(cls, dumper, data):
        return dumper.represent_scalar(cls.yaml_tag, data.string)


YAML_CUSTOM_TAGS = [YamlRegexString, YamlRegexStringAll, YamlTimestamp, YamlString, YamlPath]