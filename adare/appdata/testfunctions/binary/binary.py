# external imports
import re
from collections.abc import Callable

# internal imports
from adarelib.event.event import TestResult
from adarelib.testset import binary
from adarelib.testset.api import TestContext, testfunction
from adarelib.testset.basictest import HostModeCategory
from adarelib.testset.compare import regex_expected_problem
from adarelib.testset.content import FileTooLargeError
from adarelib.testset.ordering import OrderingError, TimeFormat, compare, parameter_errors
from adarelib.testset.structured import WILDCARD_MODES, compare_count, compare_value, count_parameter_errors, text
from adarelib.testset.valuecompare import saved_value

# configure logging
import logging

log = logging.getLogger(__name__)

_TEXT_COMPARISONS = ('equals', 'not_equals')


def _run(path: str, dst: str, status: str, body: Callable[[binary.BinaryFile], TestResult]) -> TestResult:
    """Open the resolved ``path`` of ``dst`` and run ``body`` on it.

    Every problem that means "nothing was learnt about the value" is an ERROR.
    """
    if not path:
        return TestResult.error(
            [f"file {dst} can't be used, because no unambiguous file could be identified ({status})"]
        )
    log.debug(f'dst file {path} will be used for this binary test')
    try:
        handle, size = binary.open_binary(path)
    except FileNotFoundError:
        return TestResult.error([f'file {path} does not exist'])
    except IsADirectoryError:
        return TestResult.error([f'{path} is a directory, not a file'])
    except OSError as e:
        return TestResult.execution_error(e, f'Cannot read file {path}')
    with handle:
        try:
            return body(binary.BinaryFile(handle, size, path))
        except (binary.OffsetError, binary.BinaryParameterError, binary.NonFiniteValueError, OrderingError) as e:
            return TestResult.error([f'{path}: {e}'])
        except UnicodeDecodeError as e:
            return TestResult.execution_error(e, f'Cannot decode the value in {path}')
        except re.error as e:
            return TestResult.error([str(e)])
        except FileTooLargeError as e:
            return TestResult.error([str(e)])
        except OSError as e:
            return TestResult.execution_error(e, f'Cannot read file {path}')


def _is_regex_tag(value) -> bool:
    try:
        from adarelib.testset.yaml.customtags import YamlRegexString
    except ImportError:  # YAML support not installed: no !re tags can occur
        return False
    return isinstance(value, YamlRegexString)


def _text_match(ctx: TestContext, expected, regex_match: bool) -> bool:
    """Whether ``expected`` is compared as text: a ``!re`` tag, a placeholder or ``regex_match``."""
    return (
        bool(regex_match) or _is_regex_tag(expected) or (isinstance(expected, str) and ctx.has_placeholders(expected))
    )


def _as_text(expected):
    """A number written for a text value compares as its text (``42`` matches the string ``"42"``)."""
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return str(expected)
    return expected


def _shown(actual) -> str:
    return repr(actual) if isinstance(actual, float) else str(actual)


def _text_compare(ctx, actual, expected, regex_match: bool, comparison_type: str) -> tuple[bool, str]:
    ok, message = compare_value(ctx, actual, _as_text(expected), regex_match)
    if comparison_type == 'not_equals':
        return not ok, f'not_equals: {message}'
    return ok, message


def _encoding_problems(encoding) -> list[str]:
    try:
        binary.code_unit(encoding)
    except (LookupError, TypeError) as e:
        return [f'invalid encoding {encoding!r}: {e}']
    except binary.BinaryParameterError as e:
        return [str(e)]
    return []


def _offset_problems(**offsets) -> tuple[dict, list[str]]:
    """Parsed offset expressions by name (None stays None) and the problems found."""
    parsed, problems = {}, []
    for name, value in offsets.items():
        if value is None:
            parsed[name] = None
            continue
        try:
            parsed[name] = binary.parse_offset(value)
        except binary.BinaryParameterError as e:
            problems.append(f'{name}: {e}')
    return parsed, problems


def _time_format(timestamp_epoch, timestamp_unit, utc_offset, time_format) -> tuple[TimeFormat | None, list[str]]:
    from adarelib.testset.yaml.customtags import numeric_timestamp_to_datetime

    if timestamp_epoch is not None:
        try:
            numeric_timestamp_to_datetime(0, timestamp_epoch, timestamp_unit)
        except ValueError as e:
            return None, [str(e).replace('!timestamp ', 'timestamp_')]
    if time_format is not None and not isinstance(time_format, str):
        return None, [f'time_format must be a strptime format string, got {time_format!r}']
    epoch = int(timestamp_epoch) if timestamp_epoch is not None else None
    return TimeFormat(time_format=time_format, epoch=epoch, unit=timestamp_unit, utc_offset=utc_offset), []


@testfunction(
    name='struct_value_matches',
    description='tests a number, string, byte sequence or timestamp read at an offset of a binary file',
    category=HostModeCategory.FILE_CONTENT,
)
def struct_value_matches(
    ctx: TestContext,
    dst: str,
    offset: int | str,
    value_format: str,
    expected_value: str | int | float | bool | None,
    comparison_type: str = 'equals',
    tolerance: int | float | None = None,
    regex_match: bool = False,
    encoding: str = 'utf-8',
    value_type: str = 'auto',
    timestamp_epoch: int | None = None,
    timestamp_unit: str = 's',
    utc_offset: str | None = None,
    time_format: str | None = None,
):
    """Pass when the value of ``value_format`` read at ``offset`` of ``dst`` compares to ``expected_value``.

    Use for: a field of a binary container no parser knows: a counter, flag, size or
    timestamp in a header, a record of an index file, a string in a metadata block that the
    file's last bytes point to. ``offset`` follows pointers (``u32be@-4``), so the field is
    found even when the block moves. For key/value string tables use
    binary.pair_value_matches; to count byte patterns use binary.pattern_count.

    Args:
        dst: Guest path to the file; a glob must match exactly one path;
            ``archive.tar!/member`` reads an archive member. A missing file is an error.
        offset: Where the value starts. An int (negative counts from the end: ``-8``) or an
            offset expression: ``u32be@-4`` (the offset stored as big-endian u32 in the last
            4 bytes), ``u32be@-4+8`` (that plus 8), ``u32le@(u32le@0+4)`` (pointer read at
            pointer+4), ``find:6b6579`` (first occurrence of the hex bytes). Integer types:
            ``u8``, ``i8``, ``u16le``/``u16be`` ... ``i64le``/``i64be``; numbers may be
            ``0x``-hex. A malformed expression, or an offset or value outside the file, is
            an error.
        value_format: ``u8``, ``i8``, ``u16le`` ... ``i64be`` (integers), ``f32le``/``be``,
            ``f64le``/``be`` (floats), ``bytes:<n>`` (n bytes, compared as lowercase hex),
            ``string:<n>`` (n bytes decoded with ``encoding``, trailing NULs dropped) or
            ``cstring`` (up to the first NUL, ``\\x00\\x00`` in UTF-16). A string not valid in
            ``encoding`` is an error.
        expected_value: What the value must be. Numbers and timestamps compare by value
            (``comparison_type``); strings compare as text, a number written here as its
            text; ``bytes:<n>`` as hex (whitespace ignored: ``de ad be ef``). A ``!re`` tag or
            ``{{placeholder}}`` compares the value's text (a ``!timestamp`` placeholder with
            ``epoch``/``unit`` reads a numeric field as a time); with an ordered
            ``comparison_type`` or ``tolerance`` a lone ``{{ name }}`` is the saved number or
            timestamp of that variable (not set yet, a regex, or a timestamp with tolerance: error).
        comparison_type: ``equals`` (default), ``not_equals``, ``greater``, ``less``,
            ``greater_equal`` or ``less_equal``. Ordered comparisons need numbers or
            timestamps (a string field is read as one); for text and ``bytes`` only
            ``equals``/``not_equals``.
        tolerance: For ``equals``/``not_equals`` of numbers or timestamps: the largest
            difference that still counts as equal (seconds for timestamps).
        regex_match: Treat a string ``expected_value`` as a regex searched (``re.search``) in
            the value's text; an invalid regex is an error.
        encoding: Encoding of ``string``/``cstring`` values (default ``utf-8``; ``utf-16-le``
            ...). Encodings without a fixed byte order (``utf-16``) are an error.
        value_type: ``auto`` (default), ``number`` or ``timestamp``. ``auto`` compares as
            timestamps when ``timestamp_epoch`` or ``time_format`` is set, else as numbers,
            else as ISO 8601 / RFC 2822 timestamps; a value of neither kind is an error.
        timestamp_epoch: Read a number as time since 1 January of 1970, 1601 or 2001
            (also a numeric ``expected_value``).
        timestamp_unit: Unit of such numbers: ``s`` (default), ``ms``, ``us``, ``ns``, ``100ns``.
        utc_offset: Zone of times without one, e.g. ``+02:00``; default UTC.
        time_format: ``strptime`` format of a string timestamp (``%d.%m.%Y %H:%M``).

    Example:
        function: binary.struct_value_matches
        parameter:
          dst: /home/user/app/cache/entry.bin
          offset: u32be@-4+8
          value_format: u32be
          timestamp_epoch: 1970
          expected_value: '2026-01-01T10:00:00Z'
          comparison_type: greater_equal
    """
    path, status = ctx.resolve_globfilepath(dst)
    problems = parameter_errors(comparison_type, value_type, tolerance)
    try:
        fmt = binary.parse_value_format(value_format)
    except binary.BinaryParameterError as e:
        problems.append(str(e))
        fmt = None
    parsed, offset_problems = _offset_problems(offset=offset)
    problems += offset_problems + _encoding_problems(encoding)
    time_fmt, time_problems = _time_format(timestamp_epoch, timestamp_unit, utc_offset, time_format)
    problems += time_problems
    ordered = comparison_type not in _TEXT_COMPARISONS
    if (ordered or tolerance is not None) and not regex_match:
        # a lone {{ variable }} compared in order is the saved number or timestamp
        expected_value, saved_problems = saved_value(ctx, expected_value)
        if saved_problems:
            return TestResult.error(problems + saved_problems)
    as_text = _text_match(ctx, expected_value, regex_match)
    textual = fmt is not None and not fmt.is_number
    if (as_text or (fmt is not None and fmt.kind == 'bytes')) and (ordered or tolerance is not None):
        problems.append(f'comparison_type {comparison_type!r} / tolerance need a number or timestamp, not text')
    if fmt is not None and fmt.kind == 'bytes' and not as_text:
        if not isinstance(expected_value, str):
            problems.append(f'expected_value for {fmt.name} must be a hex string, got {expected_value!r}')
        else:
            try:
                expected_value = bytes.fromhex(expected_value).hex()
            except ValueError as e:
                problems.append(f'expected_value for {fmt.name} is not a hex string: {e}')
    if problems:
        return TestResult.error(problems)
    plain_text = textual and not ordered and tolerance is None and value_type == 'auto' and not time_fmt.is_set

    def body(data: binary.BinaryFile) -> TestResult:
        position = binary.resolve_offset(parsed['offset'], data)
        actual = binary.read_value(data, position, fmt, encoding)
        where = f'{fmt.name} at offset {position} ({binary.describe(parsed["offset"])}): {_shown(actual)}'
        if as_text or plain_text:
            ok, message = _text_compare(ctx, actual, expected_value, regex_match, comparison_type)
        else:
            ok, message = compare(actual, expected_value, comparison_type, value_type, tolerance, None, time_fmt)
        return TestResult.success([where, message]) if ok else TestResult.failed([where, message])

    return _run(path, dst, status, body)


@testfunction(
    name='pattern_count',
    description='tests how often a byte pattern, text or regex occurs within a region of a binary file',
    category=HostModeCategory.FILE_CONTENT,
)
def pattern_count(
    ctx: TestContext,
    dst: str,
    pattern: str,
    pattern_type: str = 'bytes',
    start: int | str = 0,
    end: int | str | None = None,
    encoding: str = 'utf-8',
    expected_count: int = 1,
    comparison_type: str = 'equals',
):
    r"""Pass when the non-overlapping occurrences of ``pattern`` in ``[start, end)`` of ``dst`` satisfy ``comparison_type``.

    Use for: counting records, markers or values inside one part of a binary file (only the
    metadata block a trailer points to, the records after a header); a regex over raw bytes;
    asserting a value is gone from that part: ``expected_count: 0``. For the whole file in
    several encodings at once use text.occurrence_count.

    Args:
        dst: Guest path to the file; a glob must match exactly one path. A missing file is an
            error; the region is read whole, up to the read cap.
        pattern: What to count; must not be empty. Its meaning depends on ``pattern_type``.
        pattern_type: ``bytes`` (default): ASCII characters stand for their byte, Python
            escapes (``\x00``) are decoded. ``hex``: hex digits, whitespace allowed
            (``00 00 01 00``). ``regex``: an ASCII regular expression over the raw bytes
            (``\x00`` escapes for other bytes; empty matches are not counted). ``text``:
            ``pattern`` encoded in ``encoding``. Invalid escapes, hex or regexes are an error.
        start: Offset where the region starts (default 0); an int (negative from the end)
            or an offset expression as in binary.struct_value_matches (``u32be@-4``).
        end: Offset where the region ends, exclusive (default: the end of the file). An
            offset outside the file, or ``end`` before ``start``, is an error.
        encoding: Encoding for ``text`` (default ``utf-8``; ``utf-16-le``, ``utf-16-be``, ...).
        expected_count: Non-negative integer to compare with (default 1); ``0`` asserts
            absence.
        comparison_type: ``equals`` (default, like every count function), ``greater``,
            ``less``, ``greater_equal`` or ``less_equal``. Use ``greater_equal`` with
            ``expected_count: 1`` for "at least once".

    Example:
        function: binary.pattern_count
        parameter:
          dst: /home/user/app/cache/entry.bin
          pattern: 'session-[0-9a-f]{8}'
          pattern_type: regex
          start: u32be@-4
          end: -4
          expected_count: 2
    """
    path, status = ctx.resolve_globfilepath(dst)
    problems = count_parameter_errors(expected_count, comparison_type)
    if isinstance(pattern, str) and ctx.has_placeholders(pattern):
        problems.append(f'pattern {pattern!r} holds a !re or !timestamp placeholder; use pattern_type regex')
    parsed, offset_problems = _offset_problems(start=start, end=end)
    problems += offset_problems
    if pattern_type == 'text':
        problems += _encoding_problems(encoding)
    if problems:
        return TestResult.error(problems)
    try:
        compiled = binary.compile_pattern(pattern, pattern_type, encoding)
    except (binary.BinaryParameterError, LookupError) as e:
        return TestResult.error([str(e)])

    def body(data: binary.BinaryFile) -> TestResult:
        first, last, raw = binary.region(data, parsed['start'], parsed['end'])
        actual = binary.count_pattern(raw, compiled)
        ok, message = compare_count(actual, expected_count, comparison_type)
        details = [f'{actual} occurrence(s) of {pattern_type} {pattern!r} in bytes [{first}, {last})', message]
        return TestResult.success(details) if ok else TestResult.failed(details)

    return _run(path, dst, status, body)


def _table_parameters(ctx, key, start, end, separator, encoding) -> tuple[dict, list[str]]:
    problems = []
    if not isinstance(key, str) or not key:
        problems.append(f'key must be a non-empty string, got {key!r}')
    elif ctx.has_placeholders(key):
        problems.append(f'key {key!r} holds a placeholder; keys are compared literally')
    parsed, offset_problems = _offset_problems(start=start, end=end)
    problems += offset_problems + _encoding_problems(encoding)
    try:
        parsed['separator'] = binary.parse_separator(separator)
    except binary.BinaryParameterError as e:
        problems.append(f'separator: {e}')
    return parsed, problems


def _table_values(data: binary.BinaryFile, parsed: dict, key: str, encoding: str) -> tuple[list[bytes], str]:
    """The raw values of ``key`` in the table region, and a description of the region."""
    first, last, raw = binary.region(data, parsed['start'], parsed['end'])
    table = binary.string_table(raw, parsed['separator'], encoding)
    values = [value for name, value in table if name == key]
    return values, f'{len(table)} key/value pair(s) in bytes [{first}, {last})'


@testfunction(
    name='pair_value_matches',
    description='tests the value of a key in a table of separator-delimited key/value strings in a binary file',
    category=HostModeCategory.FILE_CONTENT,
)
def pair_value_matches(
    ctx: TestContext,
    dst: str,
    key: str,
    expected_value: str | int | float | bool | None,
    start: int | str = 0,
    end: int | str | None = None,
    separator: str = '\x00',
    encoding: str = 'utf-8',
    regex_match: bool = False,
    wildcard_mode: str = 'any',
):
    r"""Pass when ``key`` in the key/value string table at ``[start, end)`` of ``dst`` has ``expected_value``.

    Use for: "metadata element X has value Y" in a binary container that stores its metadata
    as alternating key and value strings (``key\0value\0key\0value\0``), e.g. in a block
    that the file's last bytes point to. An absent key fails; to assert absence use
    binary.pair_count with ``expected_count: 0``.

    Args:
        dst: Guest path to the file; a glob must match exactly one path. A missing file is an
            error.
        key: Key string to look up (compared exactly after decoding).
        expected_value: The value the key must have, compared as text (a number as its
            text). A ``!re`` tag (``re.match``) or ``{{placeholder}}`` is supported. A value
            not valid in ``encoding`` is an error.
        start: Offset of the first key (default 0); an int (negative from the end) or an
            offset expression as in binary.struct_value_matches (``u32be@-4+4``).
        end: End of the table, exclusive (default: end of file). The region must hold whole
            key/value pairs: one separator after the last value is allowed, an odd number of
            strings is an error.
        separator: Bytes between the strings (default NUL), ASCII and Python escapes
            (``\x00``, ``\n``). For UTF-16 tables use ``\x00\x00``; matches are aligned to
            the encoding's code units.
        encoding: Encoding of keys and values (default ``utf-8``; ``utf-16-le``, ...).
        regex_match: Treat a string ``expected_value`` as a regex searched (``re.search``).
        wildcard_mode: When the key occurs several times: ``any`` (default): one value must
            match; ``all``: every value must match.

    Example:
        function: binary.pair_value_matches
        parameter:
          dst: /home/user/app/cache/entry.bin
          start: u32be@-4+4
          end: -4
          key: content-type
          expected_value: text/plain
    """
    path, status = ctx.resolve_globfilepath(dst)
    parsed, problems = _table_parameters(ctx, key, start, end, separator, encoding)
    if wildcard_mode not in WILDCARD_MODES:
        problems.append(f"invalid wildcard_mode {wildcard_mode!r} (allowed: {', '.join(WILDCARD_MODES)})")
    if problems:
        return TestResult.error(problems)
    problem = regex_expected_problem(ctx, [expected_value], regex_match)
    if problem is not None:
        return problem

    def body(data: binary.BinaryFile) -> TestResult:
        raw_values, where = _table_values(data, parsed, key, encoding)
        if not raw_values:
            return TestResult.failed([where, f'key "{key}" does not occur'])
        values = [raw.decode(encoding) for raw in raw_values]
        results = [(v, *_text_compare(ctx, v, expected_value, regex_match, 'equals')) for v in values]
        matching = [v for v, ok, _ in results if ok]
        if len(results) == 1:
            _, ok, message = results[0]
            return TestResult.success([where, message]) if ok else TestResult.failed([where, message])
        passed = bool(matching) if wildcard_mode == 'any' else len(matching) == len(results)
        head = f'key "{key}" occurs {len(results)} times, {len(matching)} value(s) match (mode: {wildcard_mode})'
        shown = ', '.join(f'"{text(v)}"' for v, _, _ in results[:5])
        details = [where, head, f'values: {shown}']
        return TestResult.success(details) if passed else TestResult.failed([*details, f'expected: "{expected_value}"'])

    return _run(path, dst, status, body)


@testfunction(
    name='pair_count',
    description='tests how often a key (optionally with a value) occurs in a key/value string table of a binary file',
    category=HostModeCategory.FILE_CONTENT,
)
def pair_count(
    ctx: TestContext,
    dst: str,
    key: str,
    expected_count: int,
    expected_value: str | int | float | bool | None = None,
    start: int | str = 0,
    end: int | str | None = None,
    separator: str = '\x00',
    encoding: str = 'utf-8',
    regex_match: bool = False,
    comparison_type: str = 'equals',
):
    r"""Pass when the number of entries of ``key`` (with ``expected_value``, if given) in the table satisfies ``comparison_type``.

    Use for: asserting a metadata element is absent from a key/value string table
    (``expected_count: 0``) or occurs a given number of times. The table is read as in
    binary.pair_value_matches.

    Args:
        dst: Guest path to the file; a glob must match exactly one path. A missing file is an
            error.
        key: Key string to count.
        expected_count: Non-negative integer to compare with; ``0`` asserts absence.
        expected_value: Only count entries whose value matches this (as in
            binary.pair_value_matches). ``None`` (default) counts every entry of ``key``.
        start: Offset of the first key (default 0); int or offset expression.
        end: End of the table, exclusive (default: end of file).
        separator: Bytes between the strings (default NUL), ASCII and Python escapes.
        encoding: Encoding of keys and values (default ``utf-8``).
        regex_match: Treat a string ``expected_value`` as a regex searched in each value.
        comparison_type: ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or
            ``less_equal``.

    Example:
        function: binary.pair_count
        parameter:
          dst: /home/user/app/cache/entry.bin
          start: u32be@-4+4
          end: -4
          key: alt-source
          expected_count: 0
    """
    path, status = ctx.resolve_globfilepath(dst)
    parsed, problems = _table_parameters(ctx, key, start, end, separator, encoding)
    problems += count_parameter_errors(expected_count, comparison_type)
    if problems:
        return TestResult.error(problems)
    problem = regex_expected_problem(ctx, [expected_value], regex_match)
    if problem is not None:
        return problem

    def body(data: binary.BinaryFile) -> TestResult:
        raw_values, where = _table_values(data, parsed, key, encoding)
        if expected_value is None:
            actual = len(raw_values)
            what = f'key "{key}" occurs {actual} time(s)'
        else:
            values = [raw.decode(encoding) for raw in raw_values]
            actual = sum(1 for v in values if _text_compare(ctx, v, expected_value, regex_match, 'equals')[0])
            what = f'{actual} of {len(values)} value(s) of key "{key}" match "{expected_value}"'
        ok, message = compare_count(actual, expected_count, comparison_type)
        details = [where, what, message]
        return TestResult.success(details) if ok else TestResult.failed(details)

    return _run(path, dst, status, body)
