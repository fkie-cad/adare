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
    def from_yaml(cls, loader: yaml.SafeLoader, node: yaml.nodes.ScalarNode):
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
    def from_yaml(cls, loader: yaml.SafeLoader, node: yaml.nodes.ScalarNode):
        return YamlPath(node.value)

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

    def __init__(self, timestamp, timestamp_format_comparison=None, timestamp_format_in_entry=None, tolerance=None, timezone=None, format=None):
        self.string = timestamp
        self.timestamp_format_comparison = timestamp_format_comparison
        self.timestamp_format_in_entry = timestamp_format_in_entry
        self.tolerance = tolerance
        # New metadata fields
        self.timezone = timezone
        self.format = format
        # Store all metadata in a dict for easy access
        self.metadata = {}
        if timezone:
            self.metadata['timezone'] = timezone
        if format:
            self.metadata['format'] = format
        if tolerance is not None:  # Only store explicitly set tolerance
            self.metadata['tolerance'] = [-abs(tolerance), abs(tolerance)]

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
        tolerance_seconds = self.tolerance if self.tolerance is not None else 1  # Default to 1 second if not specified
        if timediff < datetime.timedelta(seconds=tolerance_seconds):
            return ComparisonResult(True, f'the timestamp had a difference of {timediff}')
        return ComparisonResult(False, f'the timestamp had a difference of {timediff}')

    @classmethod
    def from_yaml(cls, loader: yaml.SafeLoader, node: yaml.nodes.MappingNode):
        """Create YamlTimestamp from YAML mapping node, supporting new metadata fields."""
        mapping = loader.construct_mapping(node)
        
        # Handle the case where the first argument might be positional (timestamp value)
        if 'timestamp' not in mapping and len(mapping) > 0:
            # If no 'timestamp' key, use the first key-value as the timestamp
            first_key = next(iter(mapping.keys()))
            if isinstance(first_key, str) and not first_key.startswith(('timezone', 'format', 'tolerance')):
                mapping['timestamp'] = first_key
                mapping.pop(first_key, None)
        
        return YamlTimestamp(**mapping)

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
    def from_yaml(cls, loader: yaml.SafeLoader, node: yaml.nodes.ScalarNode):
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
        match = compiled_regex.match(entry)
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
    def from_yaml(cls, loader: yaml.SafeLoader, node: yaml.nodes.ScalarNode):
        return YamlRegexStringAll()

    @classmethod
    def to_yaml(cls, dumper, data):
        return dumper.represent_scalar(cls.yaml_tag, data.string)

    def compare(self, entry: str, variables: 'VariableRegistry' = None) -> ComparisonResult:
        return ComparisonResult(True)


YAML_CUSTOM_TAGS = [YamlRegexString, YamlRegexStringAll, YamlTimestamp, YamlString, YamlPath]
