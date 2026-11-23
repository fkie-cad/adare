"""Ordered comparisons in value testfunctions: the shared parameters and ``values_compare``.

Value testfunctions (``json.value_matches``, ``xml.attribute_matches``, ...) take
``comparison_type``, ``value_type``, ``tolerance`` and the timestamp parameters
``time_format``, ``timestamp_epoch``, ``timestamp_unit`` and ``utc_offset``. With all of them
at their defaults a function compares exactly as before (``==``, ``!re``, placeholders,
``regex_match``). Setting any of them switches to :func:`adarelib.testset.ordering.compare`
("ordered mode"); a ``!re``/``!timestamp`` tag, a ``{{placeholder}}`` or ``regex_match``
is then a parameter conflict (ERROR).

:func:`compare_pair` is the body of the ``<collection>.values_compare`` functions: two values
from one file, ``first <comparison_type> second + offset``.

Result rules: bad parameters, a side that selects several values, a value that is no number
or timestamp -> ERROR; a side that selects nothing, or a comparison that does not hold -> FAILED.

Standard library only (plus adarelib), importable on Python 3.10.
"""

from dataclasses import dataclass, field
from typing import Any

from adarelib.constants import StatusEnum
from adarelib.event.event import TestResult
from adarelib.testset.compare import resolve_key_path
from adarelib.testset.ordering import OrderingError, TimeFormat, compare, parameter_errors
from adarelib.testset.structured import StructuredFormat, load_data, text

ORDERED_PARAMETERS = (
    'comparison_type',
    'value_type',
    'tolerance',
    'time_format',
    'timestamp_epoch',
    'timestamp_unit',
    'utc_offset',
)


@dataclass(frozen=True)
class OrderedComparison:
    """The parameters of one ordered comparison (all validated)."""

    comparison_type: str = 'equals'
    value_type: str = 'auto'
    tolerance: Any = None
    offset: Any = None
    time: TimeFormat = field(default_factory=TimeFormat)

    def compare(self, actual: Any, expected: Any) -> tuple[bool, str]:
        """``actual <comparison_type> expected + offset``.

        :raises OrderingError: a value that is no number / timestamp of the compared kind
        """
        return compare(actual, expected, self.comparison_type, self.value_type, self.tolerance, self.offset, self.time)


def _time_parameter_errors(
    value_type: str, time_format: Any, timestamp_epoch: Any, timestamp_unit: Any, utc_offset: Any
) -> list[str]:
    from adarelib.testset.timeinterval import parse_utc_offset
    from adarelib.testset.yaml.customtags import TIMESTAMP_EPOCHS, TIMESTAMP_UNITS

    errors = []
    if time_format is not None and not isinstance(time_format, str):
        errors.append(f'time_format must be a strptime format string, got {time_format!r}')
    if timestamp_epoch is not None and (isinstance(timestamp_epoch, bool) or timestamp_epoch not in TIMESTAMP_EPOCHS):
        errors.append(
            f'timestamp_epoch must be one of {", ".join(map(str, TIMESTAMP_EPOCHS))}, got {timestamp_epoch!r}'
        )
    if timestamp_unit is not None:
        if timestamp_epoch is None:
            errors.append('timestamp_unit needs timestamp_epoch (the year the count starts)')
        if timestamp_unit not in TIMESTAMP_UNITS:
            errors.append(f'timestamp_unit must be one of {", ".join(TIMESTAMP_UNITS)}, got {timestamp_unit!r}')
    if utc_offset is not None and parse_utc_offset(utc_offset) is None:
        errors.append(f'invalid utc_offset {utc_offset!r} (expected e.g. +02:00)')
    timed = [n for n, v in (('time_format', time_format), ('timestamp_epoch', timestamp_epoch)) if v is not None]
    if value_type == 'number' and (timed or utc_offset is not None):
        errors.append(f'value_type number does not read timestamps; drop {", ".join(timed) or "utc_offset"}')
    return errors


def build_comparison(
    comparison_type: str = 'equals',
    value_type: str = 'auto',
    tolerance: Any = None,
    time_format: str | None = None,
    timestamp_epoch: int | None = None,
    timestamp_unit: str | None = None,
    utc_offset: str | None = None,
    offset: Any = None,
) -> OrderedComparison:
    """The validated ordered comparison.

    :raises OrderingError: invalid parameters
    """
    errors = parameter_errors(comparison_type, value_type, tolerance, offset)
    errors += _time_parameter_errors(value_type, time_format, timestamp_epoch, timestamp_unit, utc_offset)
    if errors:
        raise OrderingError('; '.join(errors))
    time = TimeFormat(
        time_format=time_format,
        epoch=timestamp_epoch,
        unit=timestamp_unit if timestamp_unit is not None else 's',
        utc_offset=utc_offset,
    )
    return OrderedComparison(comparison_type, value_type, tolerance, offset, time)


def ordered_comparison(
    comparison_type: str = 'equals',
    value_type: str = 'auto',
    tolerance: Any = None,
    time_format: str | None = None,
    timestamp_epoch: int | None = None,
    timestamp_unit: str | None = None,
    utc_offset: str | None = None,
) -> OrderedComparison | None:
    """Like :func:`build_comparison`, but ``None`` when every parameter has its default.

    ``None`` means "compare as before" (equality, ``!re``, placeholders, ``regex_match``).

    :raises OrderingError: invalid parameters
    """
    given = (tolerance, time_format, timestamp_epoch, timestamp_unit, utc_offset)
    if comparison_type == 'equals' and value_type == 'auto' and all(v is None for v in given):
        return None
    return build_comparison(
        comparison_type, value_type, tolerance, time_format, timestamp_epoch, timestamp_unit, utc_offset
    )


def _is_yaml_tag(value: Any) -> bool:
    try:
        from adarelib.testset.yaml.customtags import YamlCustomTag
    except ImportError:  # YAML support not installed: no tags can occur
        return False
    return isinstance(value, YamlCustomTag)


def expected_conflicts(ctx: Any, expected: Any, regex_match: bool = False) -> list[str]:
    """Why ``expected`` cannot be compared in order (a regex or placeholder); empty when it can."""
    errors = []
    if regex_match:
        errors.append('regex_match cannot be combined with an ordered comparison (comparison_type, value_type, ...)')
    if _is_yaml_tag(expected):
        errors.append(
            f'a {getattr(expected, "yaml_tag", type(expected).__name__)} tag in expected_value cannot be '
            'compared in order; '
            'give a plain number or timestamp'
        )
    elif isinstance(expected, str) and ctx.has_placeholders(expected):
        errors.append(
            'a {{placeholder}} in expected_value cannot be compared in order; give a plain number or timestamp'
        )
    return errors


def ordered_setup(
    ctx: Any,
    expected: Any,
    regex_match: bool,
    comparison_type: str = 'equals',
    value_type: str = 'auto',
    tolerance: Any = None,
    time_format: str | None = None,
    timestamp_epoch: int | None = None,
    timestamp_unit: str | None = None,
    utc_offset: str | None = None,
) -> tuple[OrderedComparison | None, TestResult | None]:
    """``(comparison or None, None)``, or ``(None, error_result)`` for bad or conflicting parameters.

    For the value testfunctions: call it before reading the file, then compare each value with
    ``comparison.compare`` when it is not ``None`` (else with the function's own comparison).
    """
    try:
        ordered = ordered_comparison(
            comparison_type, value_type, tolerance, time_format, timestamp_epoch, timestamp_unit, utc_offset
        )
    except OrderingError as e:
        return None, TestResult.error([str(e)])
    if ordered is None:
        return None, None
    conflicts = expected_conflicts(ctx, expected, regex_match)
    if conflicts:
        return None, TestResult.error(conflicts)
    return ordered, None


# ---------------------------------------------------------------------------
# values_compare
# ---------------------------------------------------------------------------


def _single(label: str, values: list[Any]) -> tuple[Any, TestResult | None]:
    """The one value a side selects; FAILED for none, ERROR for several."""
    if len(values) == 1 and isinstance(values[0], list):  # a path that selects one array: its elements
        values = values[0]
        if not values:
            return None, TestResult.failed([f'{label} selects an empty array'])
    if not values:
        return None, TestResult.failed([f'{label} does not exist'])
    if len(values) > 1:
        shown = ', '.join(text(v) for v in values[:5])
        return None, TestResult.error(
            [f'{label} selects {len(values)} values ({shown}); each side must select exactly one value']
        )
    return values[0], None


def compare_pair(
    label: str, values: list[Any], other_label: str, other_values: list[Any], ordered: OrderedComparison
) -> TestResult:
    """Pass when the value of ``values`` <op> the value of ``other_values`` + offset.

    ``label`` / ``other_label`` name each side in messages (``key path "a.b"``). A side that
    selects several values is an ERROR (checked first), one that selects nothing FAILED.
    """
    first, first_problem = _single(label, values)
    second, second_problem = _single(other_label, other_values)
    problems = [p for p in (first_problem, second_problem) if p is not None]
    if problems:
        errors = [p for p in problems if p.status == StatusEnum.ERROR]
        return (errors or problems)[0]
    try:
        holds, message = ordered.compare(first, second)
    except OrderingError as e:
        return TestResult.error([f'{label} = {text(first)!r}, {other_label} = {text(second)!r}: {e}'])
    details = [f'{label} = {text(first)!r}, {other_label} = {text(second)!r}', message]
    return TestResult.success(details) if holds else TestResult.failed(details)


def values_compare(
    ctx: Any, dst: str, key_path: str, other_key_path: str, fmt: StructuredFormat, ordered: OrderedComparison
) -> TestResult:
    """Body of ``<collection>.values_compare`` for key-path formats (JSON, YAML, TOML, plist)."""
    data, error = load_data(ctx, dst, fmt)
    if error is not None:
        return error
    return compare_pair(
        f'key path "{key_path}"',
        resolve_key_path(data, key_path),
        f'key path "{other_key_path}"',
        resolve_key_path(data, other_key_path),
        ordered,
    )


def structured_values_compare(
    ctx: Any,
    dst: str,
    key_path: str,
    other_key_path: str,
    fmt: StructuredFormat,
    comparison_type: str = 'equals',
    value_type: str = 'auto',
    tolerance: Any = None,
    offset: Any = None,
    time_format: str | None = None,
    timestamp_epoch: int | None = None,
    timestamp_unit: str | None = None,
    utc_offset: str | None = None,
) -> TestResult:
    """:func:`values_compare` with the parameters validated first (bad ones -> ERROR)."""
    try:
        ordered = build_comparison(
            comparison_type, value_type, tolerance, time_format, timestamp_epoch, timestamp_unit, utc_offset, offset
        )
    except OrderingError as e:
        return TestResult.error([str(e)])
    return values_compare(ctx, dst, key_path, other_key_path, fmt, ordered)
