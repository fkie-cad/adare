"""Ordered comparisons in value testfunctions: the shared parameters and ``values_compare``.

Value testfunctions (``json.value_matches``, ``xml.attribute_matches``, ...) take
``comparison_type``, ``value_type``, ``tolerance`` and the timestamp parameters
``time_format``, ``timestamp_epoch``, ``timestamp_unit`` and ``utc_offset``. With all of them
at their defaults a function compares exactly as before (``==``, ``!re``, placeholders,
``regex_match``). Setting any of them switches to :func:`adarelib.testset.ordering.compare`
("ordered mode"); a ``!re``/``!timestamp`` tag or ``regex_match`` is then a parameter
conflict (ERROR). An ``expected_value`` that is exactly one ``{{ name }}`` placeholder is the
saved variable's value (:func:`saved_value`): a number or text (``save_variable``, a command's
``capture``) or a point in time (``save_timestamp``); a regex variable, a timestamp with a
tolerance or interval, text around the placeholder or a variable not set yet is an ERROR.

:func:`compare_pair` is the body of the ``<collection>.values_compare`` functions: two values,
``first <comparison_type> second + offset``, from one file or from ``dst`` and ``other_dst``
(:func:`structured_values_compare`). ``value_decode`` (:mod:`adarelib.testset.valuedecode`)
decodes the values read from the file before they are compared.

Result rules: bad parameters, a side that selects several values, a value that is no number
or timestamp -> ERROR; a side that selects nothing, or a comparison that does not hold -> FAILED.

Standard library only (plus adarelib), importable on Python 3.10.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from adarelib.constants import StatusEnum
from adarelib.event.event import TestResult
from adarelib.testset.compare import resolve_key_path
from adarelib.testset.ordering import OrderingError, TimeFormat, compare, parameter_errors
from adarelib.testset.structured import StructuredFormat, load_data, text
from adarelib.testset.valuedecode import ValueDecodeError, ValueDecoder, build_decoder

ORDERED_PARAMETERS = (
    'comparison_type',
    'value_type',
    'tolerance',
    'time_format',
    'timestamp_epoch',
    'timestamp_unit',
    'utc_offset',
)


def is_ordered(parameters: dict[str, Any]) -> bool:
    """Whether a test's ``parameters`` ask for an ordered comparison (any of them not at its default)."""
    defaults = {'comparison_type': 'equals', 'value_type': 'auto'}
    return any(parameters.get(name, defaults.get(name)) != defaults.get(name) for name in ORDERED_PARAMETERS)


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
    """Why ``expected`` cannot be compared in order (a regex); empty when it can.

    Placeholders are checked by :func:`saved_value`.
    """
    errors = []
    if regex_match:
        errors.append('regex_match cannot be combined with an ordered comparison (comparison_type, value_type, ...)')
    if _is_yaml_tag(expected):
        errors.append(
            f'a {getattr(expected, "yaml_tag", type(expected).__name__)} tag in expected_value cannot be '
            'compared in order; '
            'give a plain number or timestamp'
        )
    return errors


_LONE_PLACEHOLDER = re.compile(r'\s*\{\{\s*([^{}]+?)\s*\}\}\s*')
_PLAIN_VARIABLE_TYPES = ('string', 'int', 'integer', 'float')


def _nonzero_tolerance(tolerance: Any) -> bool:
    if isinstance(tolerance, (list, tuple)):
        return any(bool(t) for t in tolerance)
    return bool(tolerance)


def saved_value(ctx: Any, value: Any, name: str = 'expected_value', timestamps: bool = True) -> tuple[Any, list[str]]:
    """``value`` for an ordered comparison: a lone ``{{ var }}`` becomes the saved variable's value.

    Values without a placeholder pass unchanged. A variable of type string/int/float gives its
    ``resolved_value``; a ``timestamp`` without tolerance or interval (``save_timestamp``,
    ``!timestamp``) gives its point in time, read by ``ctx.parse_expected_timestamp`` (format,
    ``localtime``), unless ``timestamps`` is false. Returns ``(value, errors)``; errors for text
    around the placeholder, a variable not set before the test, a regex variable, a timestamp with
    tolerance or interval, or a timestamp that cannot be read.
    """
    if not isinstance(value, str) or not ctx.has_placeholders(value):
        return value, []
    match = _LONE_PLACEHOLDER.fullmatch(value)
    if match is None:
        return value, [
            f'{name} {value!r} mixes text with a {{{{placeholder}}}}; an ordered comparison takes one '
            'saved variable alone ("{{ name }}") or a plain number or timestamp'
        ]
    var = match.group(1).strip()
    metadata = ctx.get_placeholder_metadata(var) or {}
    resolved = metadata.get('resolved_value')
    if not metadata or resolved is None or '{{' in str(resolved):
        return value, [f'variable {var} not set before the test ({name}); an ordered comparison needs its saved value']
    kind = metadata.get('type', 'string')
    if kind == 'timestamp' and timestamps:
        if metadata.get('interval') or _nonzero_tolerance(metadata.get('tolerance')):
            return value, [
                f'variable {var} is a timestamp with a tolerance or interval, which compares on its own; '
                f'drop the ordered parameters, or save a plain timestamp for {name}'
            ]
        try:
            return ctx.parse_expected_timestamp(resolved, metadata), []
        except (ValueError, OverflowError, OSError) as e:
            return value, [f'variable {var} = {resolved!r} is no timestamp: {e}']
    if kind in _PLAIN_VARIABLE_TYPES:
        return resolved, []
    wanted = 'a number or timestamp' if timestamps else 'a number'
    return value, [f'variable {var} is of type {kind}; {name} in an ordered comparison needs {wanted}']


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
) -> tuple[OrderedComparison | None, Any, TestResult | None]:
    """``(comparison or None, expected, None)``, or ``(None, expected, error_result)``.

    For the value testfunctions: call it before reading the file, then compare each value with
    ``comparison.compare(value, expected)`` when the comparison is not ``None`` (else with the
    function's own comparison and the ``expected`` given). In ordered mode the returned
    ``expected`` has a lone ``{{ var }}`` replaced by the saved value (:func:`saved_value`).
    """
    try:
        ordered = ordered_comparison(
            comparison_type, value_type, tolerance, time_format, timestamp_epoch, timestamp_unit, utc_offset
        )
    except OrderingError as e:
        return None, expected, TestResult.error([str(e)])
    if ordered is None:
        return None, expected, None
    conflicts = expected_conflicts(ctx, expected, regex_match)
    if conflicts:
        return None, expected, TestResult.error(conflicts)
    resolved, errors = saved_value(ctx, expected)
    if errors:
        return None, expected, TestResult.error(errors)
    return ordered, resolved, None


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
    label: str,
    values: list[Any],
    other_label: str,
    other_values: list[Any],
    ordered: OrderedComparison,
    decoder: ValueDecoder | None = None,
) -> TestResult:
    """Pass when the value of ``values`` <op> the value of ``other_values`` + offset.

    ``label`` / ``other_label`` name each side in messages (``key path "a.b"``). A side that
    selects several values is an ERROR (checked first), one that selects nothing FAILED.
    ``decoder`` (``value_decode``) decodes both values first; a decode failure is an ERROR.
    """
    first, first_problem = _single(label, values)
    second, second_problem = _single(other_label, other_values)
    problems = [p for p in (first_problem, second_problem) if p is not None]
    if problems:
        errors = [p for p in problems if p.status == StatusEnum.ERROR]
        return (errors or problems)[0]
    if decoder is not None:
        try:
            first, second = decoder(first), decoder(second)
        except ValueDecodeError as e:
            return TestResult.error([f'{label} / {other_label}: {e}'])
    try:
        holds, message = ordered.compare(first, second)
    except OrderingError as e:
        return TestResult.error([f'{label} = {text(first)!r}, {other_label} = {text(second)!r}: {e}'])
    details = [f'{label} = {text(first)!r}, {other_label} = {text(second)!r}', message]
    return TestResult.success(details) if holds else TestResult.failed(details)


Select = Callable[[Any, str, bool], tuple[str, list[Any]]]


def _key_path_side(data: Any, key_path: str, _first: bool) -> tuple[str, list[Any]]:
    return f'key path "{key_path}"', resolve_key_path(data, key_path)


def values_compare(
    ctx: Any,
    dst: str,
    key_path: str,
    other_key_path: str,
    fmt: StructuredFormat,
    ordered: OrderedComparison,
    other_dst: str | None = None,
    decoder: ValueDecoder | None = None,
    select: Select | None = None,
) -> TestResult:
    """Body of ``<collection>.values_compare``: ``key_path`` in ``dst``, ``other_key_path`` in ``other_dst``.

    ``other_dst`` ``None`` (or empty) reads the second value from ``dst`` as well; otherwise it is
    loaded exactly like ``dst`` (glob, archive member, a missing file is an ERROR).
    ``select(data, path, first)`` returns ``(label, values)`` of one side; the default resolves
    a key path (JSON, YAML, TOML, plist). A ``ValueError`` it raises is an execution error.
    """
    data, error = load_data(ctx, dst, fmt)
    if error is not None:
        return error
    other_data = data
    if other_dst:
        other_data, error = load_data(ctx, other_dst, fmt)
        if error is not None:
            return error
    pick = select or _key_path_side
    try:
        label, values = pick(data, key_path, True)
        other_label, other_values = pick(other_data, other_key_path, False)
    except ValueError as e:
        return TestResult.execution_error(e, f'{fmt.label} processing error')
    if other_dst:
        label, other_label = f'{label} in {dst}', f'{other_label} in {other_dst}'
    return compare_pair(label, values, other_label, other_values, ordered, decoder)


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
    other_dst: str | None = None,
    value_decode: Any = None,
    decoded_key_path: Any = None,
    select: Select | None = None,
) -> TestResult:
    """:func:`values_compare` with the parameters validated first (bad ones -> ERROR).

    ``offset`` may be a lone ``{{ var }}``: the saved number (:func:`saved_value`).
    """
    offset, errors = saved_value(ctx, offset, 'offset', timestamps=False)
    if errors:
        return TestResult.error(errors)
    try:
        ordered = build_comparison(
            comparison_type, value_type, tolerance, time_format, timestamp_epoch, timestamp_unit, utc_offset, offset
        )
        decoder = build_decoder(value_decode, decoded_key_path)
    except (OrderingError, ValueDecodeError) as e:
        return TestResult.error([str(e)])
    if other_dst is not None and not isinstance(other_dst, str):
        return TestResult.error([f'other_dst must be a path, got {other_dst!r}'])
    return values_compare(ctx, dst, key_path, other_key_path, fmt, ordered, other_dst, decoder, select)
