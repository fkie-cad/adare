# external imports
import yaml
import re
import attr
import datetime
import dateutil.parser
import dateutil.relativedelta
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from adarelib.common.variables import VariableRegistry

# internal imports
import adarelib.helper.regex as helper_regex

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

    def set_variables(self, variables: 'VariableRegistry'):
        if variables:
            self.string = variables.resolve_in_string(self.string, for_regex=False)


class YamlString(YamlCustomTag):
    yaml_tag = u'!s'

    def __init__(self, string: str):
        self.string = string

    def __repr__(self):
        return f'{self.yaml_tag} {self.string}'

    @classmethod
    def from_yaml(cls, loader: yaml.SafeLoader, node: yaml.nodes.MappingNode):
        return YamlString(node.value)

    @classmethod
    def to_yaml(cls, dumper, data):
        return dumper.represent_scalar(cls.yaml_tag, data.string)

    def compare(self, entry: str) -> ComparisonResult:
        if self.string == entry:
            return ComparisonResult(True)
        else:
            return ComparisonResult(False)


class YamlPath(YamlCustomTag):
    yaml_tag = u'!path'

    def __init__(self, string: str):
        self.string = string

    def __repr__(self):
        return f'{self.yaml_tag} {self.string}'

    @classmethod
    def from_yaml(cls, loader: yaml.SafeLoader, node: yaml.nodes.MappingNode):
        return YamlString(node.value)

    @classmethod
    def to_yaml(cls, dumper, data):
        return dumper.represent_scalar(cls.yaml_tag, data.string)

    def compare(self, entry: str) -> ComparisonResult:
        if self.string == entry:
            return ComparisonResult(True)
        else:
            return ComparisonResult(False)


class YamlTimestamp(YamlCustomTag):
    yaml_tag = u'!timestamp'

    def __init__(self, timestamp, timestamp_format_comparison=None, timestamp_format_in_entry=None, tolerance=1):
        self.string = timestamp
        self.timestamp_format_comparison = timestamp_format_comparison
        self.timestamp_format_in_entry = timestamp_format_in_entry
        self.tolerance = tolerance

    def __repr__(self):
        return f'{self.yaml_tag} {self.string}'

    def compare(self, entry: str) -> ComparisonResult:
        if not self.timestamp_format_in_entry:
            try:
                data_timestamp = dateutil.parser.parse(entry)
            except dateutil.parser.ParserError as e:
                return ComparisonResult(False, f'data timestamp couldn\'t be parsed', e)
        else:
            try:
                data_timestamp = datetime.datetime.strptime(entry, self.timestamp_format_in_entry)
            except ValueError as e:
                return ComparisonResult(False, f'data timestamp couldn\'t be parsed', e)
        if not self.timestamp_format_comparison:
            try:
                timestamp = dateutil.parser.parse(self.string)
            except dateutil.parser.ParserError as e:
                return ComparisonResult(False, f'comparison timestamp couldn\'t be parsed', e)
        else:
            try:
                timestamp = datetime.datetime.strptime(entry, self.timestamp_format_comparison)
            except ValueError as e:
                return ComparisonResult(False, f'data timestamp couldn\'t be parsed', e)

        timediff = abs(data_timestamp - timestamp)
        if timediff < datetime.timedelta(seconds=self.tolerance):
            return ComparisonResult(True, f'the timestamp had a difference of {timediff}')
        return ComparisonResult(False, f'the timestamp had a difference of {timediff}')

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
        return f'{self.yaml_tag} {self.string}'

    @classmethod
    def from_yaml(cls, loader: yaml.SafeLoader, node: yaml.nodes.MappingNode):
        return YamlRegexString(node.value)

    @classmethod
    def to_yaml(cls, dumper, data):
        return dumper.represent_scalar(cls.yaml_tag, data.string)

    def set_variables(self, variables: 'VariableRegistry'):
        if variables:
            self.string = variables.resolve_in_string(self.string, for_regex=True)

    def compare(self, entry: str, variables: 'VariableRegistry' = None) -> ComparisonResult:
        try:
            compiled_regex = re.compile(self.string)
        except re.error as e:
            return ComparisonResult(False, f'regex {self.string} could not be compiled', e)
        match = compiled_regex.match(self.string)
        if not match:
            return ComparisonResult(False)
        return ComparisonResult(True)


class YamlRegexStringAll(YamlRegexString):
    yaml_tag = u'!reALL'

    def __init__(self):
        super().__init__('.*')

    def __repr__(self):
        return f'{self.yaml_tag}'

    @classmethod
    def from_yaml(cls, loader: yaml.SafeLoader, node: yaml.nodes.MappingNode):
        return YamlRegexStringAll()

    @classmethod
    def to_yaml(cls, dumper, data):
        return dumper.represent_scalar(cls.yaml_tag, data.string)

    def compare(self, entry: str, variables: 'VariableRegistry' = None) -> ComparisonResult:
        return ComparisonResult(True)


YAML_CUSTOM_TAGS = [YamlRegexString, YamlRegexStringAll, YamlTimestamp, YamlString, YamlPath]
