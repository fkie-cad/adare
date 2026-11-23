# external imports
import datetime
import decimal
import re
from typing import TYPE_CHECKING

import attr
import yaml

from adarelib.testset.timeinterval import parse_timestamp_text

if TYPE_CHECKING:
    from adarelib.common.variables import VariableRegistry

# configure logging
import logging

log = logging.getLogger(__name__)


@attr.define
class ComparisonResult:
    success: bool
    details: str | None = attr.Factory(str)
    additional_information: dict = attr.Factory(dict)
    exception: Exception | None = None


class YamlCustomTag(yaml.YAMLObject):
    string: str

    def set_variables(self, variables: 'VariableRegistry'):
        if variables:
            self.string = variables.resolve_in_string(self.string, for_regex=False)


class YamlString(YamlCustomTag):
    yaml_tag = '!s'

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
        return ComparisonResult(False)


class YamlPath(YamlCustomTag):
    yaml_tag = '!path'

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
        return ComparisonResult(False)


_TIMESTAMP_OPTIONS = (
    'timezone',
    'format',
    'tolerance',
    'after',
    'before',
    'precision',
    'localtime',
    'timestamp_format_comparison',
    'timestamp_format_in_entry',
    'epoch',
    'unit',
)

# Numeric timestamps: years an artifact value may count from, and how many
# microseconds one unit is, as (numerator, denominator) for exact integer math.
TIMESTAMP_EPOCHS = (1970, 1601, 2001)
TIMESTAMP_UNITS = {'s': (1_000_000, 1), 'ms': (1000, 1), 'us': (1, 1), 'ns': (1, 1000), '100ns': (1, 10)}
_NUMERIC_TIMESTAMP = re.compile(r'([+-]?)(\d+)(?:\.(\d+))?')


def _validate_epoch(epoch) -> int:
    is_number = not isinstance(epoch, bool) and isinstance(epoch, (int, str)) and str(epoch).strip().isdigit()
    if is_number and int(epoch) in TIMESTAMP_EPOCHS:
        return int(epoch)
    raise ValueError(f'!timestamp epoch must be one of {", ".join(map(str, TIMESTAMP_EPOCHS))}, got {epoch!r}')


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _tolerance_bounds(tolerance) -> list:
    """``[lower, upper]`` seconds allowed for expected minus actual.

    A number ``n`` allows ``[-n, n]``; a two-number list ``[a, b]`` allows ``[min, max]``.

    :raises ValueError: anything else
    """
    if _is_number(tolerance):
        return [-abs(tolerance), abs(tolerance)]
    if isinstance(tolerance, (list, tuple)) and len(tolerance) == 2 and all(_is_number(t) for t in tolerance):
        return [min(tolerance), max(tolerance)]
    raise ValueError(f'!timestamp tolerance must be a number or a list of two numbers, got {tolerance!r}')


def _validate_unit(unit) -> str:
    if isinstance(unit, str) and unit in TIMESTAMP_UNITS:
        return unit
    raise ValueError(f'!timestamp unit must be one of {", ".join(TIMESTAMP_UNITS)}, got {unit!r}')


def numeric_timestamp_to_datetime(value, epoch: int = 1970, unit: str = 's') -> datetime.datetime:
    """Convert a number of ``unit`` since 1 January of ``epoch`` into a naive datetime (no zone applied).

    ``value`` is an int, a float or a string of digits (optionally signed, optionally with a
    fraction). Integer arithmetic keeps ns/100ns values exact down to the microsecond, the
    resolution of ``datetime``; finer digits are truncated. Raises ``ValueError`` for anything else.
    """
    numerator, denominator = TIMESTAMP_UNITS[_validate_unit(unit)]
    epoch = _validate_epoch(epoch)
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f'numeric timestamp expected, got {type(value).__name__} {value!r}')
    text = format(decimal.Decimal(repr(value)), 'f') if isinstance(value, float) else str(value).strip()
    match = _NUMERIC_TIMESTAMP.fullmatch(text)
    if not match:
        raise ValueError(f'numeric timestamp expected (epoch {epoch}, unit {unit}), got {value!r}')
    sign, whole, fraction = match.group(1), match.group(2), match.group(3) or ''
    scaled = int(sign + whole + fraction)
    microseconds = scaled * numerator // (denominator * 10 ** len(fraction))
    try:
        return datetime.datetime(epoch, 1, 1) + datetime.timedelta(microseconds=microseconds)
    except OverflowError as e:
        raise ValueError(f'numeric timestamp {value!r} (epoch {epoch}, unit {unit}) is out of range') from e


class YamlTimestamp(YamlCustomTag):
    yaml_tag = '!timestamp'

    def __init__(
        self,
        timestamp=None,
        timestamp_format_comparison=None,
        timestamp_format_in_entry=None,
        tolerance=None,
        timezone=None,
        format=None,
        after=None,
        before=None,
        precision=None,
        localtime=None,
        epoch=None,
        unit=None,
    ):
        # Interval form: `!timestamp {after: '{{t0}}', before: '{{t1}}'}` checks
        # after <= value <= before; the lower bound stands in as the timestamp.
        if timestamp is None and after is None:
            raise ValueError('!timestamp needs a timestamp, or an interval with after/before')
        if (after is None) != (before is None):
            raise ValueError('!timestamp interval needs both after and before')
        if (epoch is not None or unit is not None) and tolerance is None and after is None:
            # Without either the value is compared as an exact string and epoch/unit would be ignored.
            raise ValueError('!timestamp epoch/unit need a tolerance or an after/before interval')
        self.string = timestamp if timestamp is not None else after
        self.after = after
        self.before = before
        self.precision = precision
        self.timestamp_format_comparison = timestamp_format_comparison
        self.timestamp_format_in_entry = timestamp_format_in_entry
        if tolerance is not None and not _is_number(tolerance):
            tolerance = _tolerance_bounds(tolerance)  # a list: validated and sorted
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
            self.metadata['tolerance'] = _tolerance_bounds(tolerance)
        if after is not None:
            self.metadata['interval'] = [after, before]
        if precision is not None:
            self.metadata['precision'] = precision
        if localtime is not None:  # the artifact stores the guest's local time without an offset
            self.metadata['localtime'] = bool(localtime)
        # A numeric artifact value counts `unit`s since 1 January of `epoch` (see numeric_timestamp_to_datetime).
        if epoch is not None:
            self.metadata['epoch'] = _validate_epoch(epoch)
        if unit is not None:
            self.metadata['unit'] = _validate_unit(unit)

    def __repr__(self):
        if self.after is not None:
            return f'{self.yaml_tag} [{self.after}, {self.before}]'
        return f'{self.yaml_tag} {self.string}'

    @property
    def has_interval(self) -> bool:
        return self.after is not None

    def compare(self, entry: str) -> ComparisonResult:
        """Direct comparison for a testfunction holding the tag (runs normally convert it to a placeholder).

        Honours ``epoch``/``unit`` for a numeric ``entry`` and a list ``tolerance``; default 1 second.
        """
        if 'epoch' in self.metadata or 'unit' in self.metadata:
            try:
                data_timestamp = numeric_timestamp_to_datetime(
                    entry, self.metadata.get('epoch', 1970), self.metadata.get('unit', 's')
                )
            except ValueError as e:
                return ComparisonResult(False, 'data timestamp couldn\'t be parsed', exception=e)
        elif not self.timestamp_format_in_entry:
            try:
                data_timestamp = parse_timestamp_text(entry)
            except (ValueError, OverflowError) as e:
                return ComparisonResult(False, 'data timestamp couldn\'t be parsed', exception=e)
        else:
            try:
                data_timestamp = datetime.datetime.strptime(entry, self.timestamp_format_in_entry)
            except ValueError as e:
                return ComparisonResult(False, 'data timestamp couldn\'t be parsed', exception=e)
        if not self.timestamp_format_comparison:
            try:
                timestamp = parse_timestamp_text(self.string)
            except (ValueError, OverflowError) as e:
                return ComparisonResult(False, 'comparison timestamp couldn\'t be parsed', exception=e)
        else:
            try:
                timestamp = datetime.datetime.strptime(self.string, self.timestamp_format_comparison)
            except ValueError as e:
                return ComparisonResult(False, 'comparison timestamp couldn\'t be parsed', exception=e)

        lower, upper = _tolerance_bounds(self.tolerance if self.tolerance is not None else 1)
        try:
            diff = (timestamp - data_timestamp).total_seconds()
        except TypeError as e:  # one side has a zone, the other not
            return ComparisonResult(False, 'timestamps with and without a time zone cannot be compared', exception=e)
        message = f'the timestamp had a difference of {datetime.timedelta(seconds=abs(diff))}'
        return ComparisonResult(lower <= diff <= upper, message)

    @classmethod
    def from_yaml(cls, loader: yaml.SafeLoader, node: yaml.nodes.MappingNode):
        """Create YamlTimestamp from YAML mapping node, supporting new metadata fields."""
        # deep: a list value (tolerance: [-5, 10]) would otherwise still be empty here
        mapping = loader.construct_mapping(node, deep=True)

        # Handle the case where the first argument might be positional (timestamp value)
        if 'timestamp' not in mapping and len(mapping) > 0:
            # If no 'timestamp' key, use the first key-value as the timestamp
            first_key = next(iter(mapping.keys()))
            if isinstance(first_key, str) and first_key not in _TIMESTAMP_OPTIONS:
                mapping['timestamp'] = first_key
                mapping.pop(first_key, None)

        return YamlTimestamp(**mapping)

    @classmethod
    def to_yaml(cls, dumper, data):
        return dumper.represent_scalar(cls.yaml_tag, data.string)


class YamlRegexString(YamlCustomTag):
    yaml_tag = '!re'

    def __init__(self, string: str):
        self.string = string

    def __repr__(self):
        return f'{self.yaml_tag} {self.string}'

    @classmethod
    def from_yaml(cls, loader: yaml.SafeLoader, node: yaml.nodes.ScalarNode):
        # A literal pattern is checked when the playbook loads; one with {{ variables }}
        # can only be compiled after they are resolved (an invalid one is an ERROR then).
        if '{{' not in node.value:
            try:
                re.compile(node.value)
            except re.error as e:
                raise yaml.constructor.ConstructorError(
                    None, None, f'invalid regular expression in !re {node.value!r}: {e}', node.start_mark
                ) from e
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
            return ComparisonResult(False, f'regex {self.string} could not be compiled', exception=e)
        match = compiled_regex.match(entry)
        if not match:
            return ComparisonResult(False)
        return ComparisonResult(True)


class YamlRegexStringAll(YamlRegexString):
    yaml_tag = '!reALL'

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
