# external imports
import bisect
import codecs
import re

# internal imports
from adarelib.testset.api import testfunction, TestContext
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult
from adarelib.testset.content import decode_text, parse_byte_string, read_bytes_capped
from adarelib.testset.structured import compare_count, count_parameter_errors

# configure logging
import logging

log = logging.getLogger(__name__)

CONTENT_TYPES = ('string', 'bytes', 'hex')

# codecs whose encoder writes a byte order mark: search the BOM-less forms instead
_BOM_CODECS = {
    'utf-16': ('utf-16-le', 'utf-16-be'),
    'utf-32': ('utf-32-le', 'utf-32-be'),
    'utf-8-sig': ('utf-8',),
}

Pattern = bytes | re.Pattern


def _placeholder_problems(ctx: TestContext, content, instead: str) -> list[str]:
    """An error for ``content`` holding a ``!re``/``!timestamp`` placeholder: it would be searched literally."""
    if isinstance(content, str) and ctx.has_placeholders(content):
        return [
            f'content {content!r} holds a !re or !timestamp placeholder, which is not supported here; use {instead}'
        ]
    return []


def _expand_encodings(encodings: list[str] | str | None) -> list[str]:
    """Concrete codec names for ``encodings``.

    :raises ValueError: not a list of names
    :raises LookupError: unknown encoding
    """
    if encodings is None:
        return ['utf-8']
    if isinstance(encodings, str):
        encodings = [encodings]
    if not isinstance(encodings, list) or not encodings or not all(isinstance(e, str) for e in encodings):
        raise ValueError(f'encoding must be a name or a non-empty list of names, got {encodings!r}')
    if len(encodings) > 1 and all(len(e) == 1 for e in encodings):
        # a playbook string (encodings: utf-8) arrives split into characters
        joined = ''.join(encodings)
        raise ValueError(
            f'encoding must be a name or a list of names, got the characters of {joined!r}; write the name as one string'
        )
    names: list[str] = []
    for encoding in encodings:
        name = codecs.lookup(encoding).name
        for concrete in _BOM_CODECS.get(name, (name,)):
            if concrete not in names:
                names.append(concrete)
    return names


def _caseless_pattern(content: str, encoding: str) -> re.Pattern:
    """Regex over bytes matching ``content`` with every character in any of its single-character cases.

    :raises UnicodeEncodeError: a character of ``content`` cannot be encoded
    """
    parts = []
    for char in content:
        alternatives = [char.encode(encoding)]
        for variant in (char.lower(), char.upper(), char.casefold(), char.swapcase()):
            if len(variant) != 1:
                continue
            try:
                encoded = variant.encode(encoding)
            except UnicodeEncodeError:
                continue
            if encoded not in alternatives:
                alternatives.append(encoded)
        parts.append(b'(?:' + b'|'.join(re.escape(a) for a in alternatives) + b')')
    return re.compile(b''.join(parts))


def _string_patterns(content: str, encodings, case_sensitive: bool) -> list[tuple[str, Pattern]]:
    """One search pattern per distinct encoded form of ``content``.

    :raises ValueError: bad ``encodings`` or ``content`` not encodable in one of them
    :raises LookupError: unknown encoding
    """
    patterns: list[tuple[str, Pattern]] = []
    seen: set[bytes] = set()
    for encoding in _expand_encodings(encodings):
        try:
            pattern: Pattern = content.encode(encoding) if case_sensitive else _caseless_pattern(content, encoding)
        except UnicodeEncodeError as e:
            raise ValueError(f'content cannot be encoded as {encoding}: {e}') from e
        key = pattern if isinstance(pattern, bytes) else pattern.pattern
        if key not in seen:
            seen.add(key)
            patterns.append((encoding, pattern))
    return patterns


def _bytes_pattern(content: str, content_type: str) -> bytes:
    """The byte sequence ``content`` stands for in ``bytes`` or ``hex`` mode.

    :raises ValueError: content that is not a valid byte string / hex string
    """
    if content_type == 'hex':
        try:
            return bytes.fromhex(content)
        except ValueError as e:
            raise ValueError(f'content is not a hex string: {e}') from e
    return parse_byte_string(content)


def _search_patterns(content, content_type, encodings, case_sensitive) -> list[tuple[str, Pattern]]:
    """Validate the search parameters and build the patterns.

    :raises ValueError, LookupError: invalid parameters
    """
    if not isinstance(content, str) or not content:
        raise ValueError(f'content must be a non-empty string, got {content!r}')
    if content_type not in CONTENT_TYPES:
        raise ValueError(f"invalid content_type {content_type!r} (allowed: {', '.join(CONTENT_TYPES)})")
    if content_type == 'string':
        return _string_patterns(content, encodings, case_sensitive)
    if not case_sensitive:
        raise ValueError(f'case_sensitive: false works with content_type string only, not {content_type}')
    pattern = _bytes_pattern(content, content_type)
    if not pattern:
        raise ValueError('content is empty')
    return [(content_type, pattern)]


def _spans(data: bytes, pattern: Pattern) -> list[tuple[int, int]]:
    """``(start, end)`` of the non-overlapping occurrences of ``pattern`` in ``data``."""
    if isinstance(pattern, bytes):
        spans = []
        start = data.find(pattern)
        while start != -1:
            spans.append((start, start + len(pattern)))
            start = data.find(pattern, start + len(pattern))
        return spans
    return [m.span() for m in pattern.finditer(data)]


def _count_forms(data: bytes, patterns: list[tuple[str, Pattern]]) -> list[tuple[str, int]]:
    """Occurrences per form; a match overlapping one already counted (in an earlier form) is skipped.

    Text in one UTF-16 byte order also matches the other order shifted by one byte; those
    overlapping matches are the same bytes and count once.
    """
    taken: list[tuple[int, int]] = []  # sorted, non-overlapping
    counts = []
    for label, pattern in patterns:
        n = 0
        for start, end in _spans(data, pattern):
            i = bisect.bisect_left(taken, (start, end))
            before = taken[i - 1] if i else None
            after = taken[i] if i < len(taken) else None
            if (before and before[1] > start) or (after and after[0] < end):
                continue
            taken.insert(i, (start, end))
            n += 1
        counts.append((label, n))
    return counts


def _read(path: str, dst: str, status: str) -> tuple[bytes, TestResult | None]:
    """Read the resolved ``path`` of ``dst``; return ``(data, None)`` or ``(b'', error_result)``."""
    if not path:
        return b'', TestResult.error(
            [f'file {dst} can\'t be used, because no unambiguous file could be identified ({status})']
        )
    log.debug(f'dst file {path} will be used for this text test')
    try:
        return read_bytes_capped(path), None
    except FileNotFoundError:
        return b'', TestResult.error([f'file {path} does not exist'])
    except IsADirectoryError:
        return b'', TestResult.error([f'{path} is a directory, not a file'])
    except OSError as e:
        return b'', TestResult.execution_error(e, f'Cannot read file {path}')


@testfunction(
    name='occurrence_count',
    description='tests how often a string or byte sequence occurs in a (text or binary) file',
    category=HostModeCategory.FILE_CONTENT,
)
def occurrence_count(
    ctx: TestContext,
    dst: str,
    content: str,
    expected_count: int,
    content_type: str = 'string',
    encoding: list[str] | str | None = None,
    case_sensitive: bool = True,
    comparison_type: str = 'equals',
):
    r"""Pass when the number of non-overlapping occurrences of ``content`` in ``dst`` satisfies ``comparison_type``.

    Use for: how many times a word or value appears in any file (``expected_count: N``),
    binary ones included (a database, a cache, a memory dump), in one or several encodings
    at once; asserting a value was wiped: ``expected_count: 0``. For line-based text use text.line_count.

    Args:
        dst: Guest path to the file; a glob must match exactly one path. A missing file is an
            error. The raw bytes are searched, nothing is decoded.
        content: What to find; must not be empty. Its meaning depends on ``content_type``.
            A ``!re`` or ``!timestamp`` placeholder is an error: for patterns use
            text.line_count with ``regex_match``.
        expected_count: Non-negative integer to compare against; anything else is an error.
        content_type: ``string`` (default): ``content`` encoded in each of ``encoding``.
            ``bytes``: ASCII characters stand for their byte, Python escapes (``\x00``, ``\n``,
            ``\\``) are decoded; a non-ASCII character or an unknown escape is an error (write
            ``\xNN``, or use ``string`` with an encoding). ``hex``: hex digits, whitespace
            allowed (``4d 5a 90 00``).
        encoding: Encoding(s) for ``string`` mode: one name (``utf-16-le``) or a list (default ``[utf-8]``), e.g.
            ``[utf-8, utf-16-le]``. Occurrences of the distinct encoded forms are summed (the
            same text stored once in each of two forms counts twice); a match on bytes already
            counted for an earlier form is skipped. ``utf-16``/``utf-32`` search both byte
            orders without BOM. Forms are matched at any byte offset, not aligned to
            characters. Unknown encodings, or ``content`` not encodable in one, are an error.
        case_sensitive: ``False`` matches each character in any of its one-character case
            forms (``a``/``A``, ``ä``/``Ä``); case mappings to several characters (German
            sharp s to ``SS``) are not matched. ``string`` mode only, otherwise an error.
        comparison_type: ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or
            ``less_equal``; other values are an error.

    Example:
        function: text.occurrence_count
        parameter:
          dst: /home/user/data/cache.bin
          content: secret-token
          encoding: [utf-8, utf-16-le]
          expected_count: 0
    """
    problems = count_parameter_errors(expected_count, comparison_type)
    problems += _placeholder_problems(ctx, content, 'text.line_count with regex_match')
    if problems:
        return TestResult.error(problems)
    try:
        patterns = _search_patterns(content, content_type, encoding, case_sensitive)
    except (ValueError, LookupError) as e:
        return TestResult.error([str(e)])
    path, status = ctx.resolve_globfilepath(dst)
    data, error = _read(path, dst, status)
    if error is not None:
        return error
    counts = _count_forms(data, patterns)
    actual = sum(n for _, n in counts)
    ok, message = compare_count(actual, expected_count, comparison_type)
    found = ', '.join(f'{n} as {label}' for label, n in counts)
    details = [f'{actual} occurrence(s) of {content!r} in {len(data)} bytes ({found})', message]
    return TestResult.success(details) if ok else TestResult.failed(details)


def _split_lines(text: str) -> list[str]:
    """Lines split at ``\\n``, ``\\r\\n`` or ``\\r``; a final line break ends the last line."""
    if not text:
        return []
    lines = re.split(r'\r\n|\r|\n', text)
    if lines[-1] == '':
        lines.pop()
    return lines


@testfunction(
    name='line_count',
    description='tests the number of text lines that contain a string or match a regex',
    category=HostModeCategory.FILE_CONTENT,
)
def line_count(
    ctx: TestContext,
    dst: str,
    content: str,
    expected_count: int,
    comparison_type: str = 'equals',
    encoding: str | None = None,
    regex_match: bool = False,
    case_sensitive: bool = True,
):
    """Pass when the number of lines of text file ``dst`` containing ``content`` satisfies ``comparison_type``.

    Use for: counting log or history entries (exactly 2 lines with a file name); asserting
    a line is gone: ``expected_count: 0``. For binary files use text.occurrence_count.

    Args:
        dst: Guest path to the text file; a glob must match exactly one path. A missing file
            or content not valid in the encoding is an error; an empty file has 0 lines.
            Lines end at ``\\n``, ``\\r\\n`` or ``\\r``.
        content: Substring a line must contain (see ``case_sensitive``); an empty string
            counts every line. With ``regex_match`` a regex searched in each line
            (``re.search``); an invalid regex is an error. A ``!re`` or ``!timestamp``
            placeholder is an error: write the pattern with ``regex_match``.
        expected_count: Non-negative integer to compare against; anything else is an error.
        comparison_type: ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or
            ``less_equal``; other values are an error.
        encoding: Text encoding; ``None`` (default) detects a BOM (UTF-8/16/32) and BOM-less
            UTF-16, else reads UTF-8. A BOM always wins. Unknown names are an error.
        regex_match: Treat ``content`` as a regex (see ``content``).
        case_sensitive: ``True`` (default) matches case exactly. ``False`` compares the
            substring after casefolding line and ``content`` (``Report`` = ``REPORT``,
            sharp s = ``ss``), or compiles the regex with ``re.IGNORECASE``. A non-boolean
            is an error.

    Example:
        function: text.line_count
        parameter:
          dst: /home/user/data/app.log
          content: 'deleted: .*report'
          regex_match: true
          expected_count: 1
          comparison_type: greater_equal
    """
    problems = count_parameter_errors(expected_count, comparison_type)
    if not isinstance(content, str):
        problems.append(f'content must be a string, got {content!r}')
    else:
        problems += _placeholder_problems(ctx, content, 'regex_match: true with a plain pattern')
    if not isinstance(case_sensitive, bool):
        problems.append(f'case_sensitive must be true or false, got {case_sensitive!r}')
    if problems:
        return TestResult.error(problems)
    try:
        if encoding is not None:
            codecs.lookup(encoding)
        regex = re.compile(content, 0 if case_sensitive else re.IGNORECASE) if regex_match else None
    except (LookupError, TypeError) as e:
        return TestResult.error([f'invalid encoding {encoding!r}: {e}'])
    except re.error as e:
        return TestResult.error([f'invalid regex {content!r}: {e}'])
    path, status = ctx.resolve_globfilepath(dst)
    data, error = _read(path, dst, status)
    if error is not None:
        return error
    try:
        lines = _split_lines(decode_text(data, encoding))
    except UnicodeDecodeError as e:
        return TestResult.execution_error(e, f'Cannot decode {dst} as {encoding or "UTF-8/UTF-16"}')
    if regex is not None:
        matching = sum(1 for line in lines if regex.search(line))
        what = f'match regex "{content}"'
    elif case_sensitive:
        matching = sum(1 for line in lines if content in line)
        what = f'contain "{content}"'
    else:
        folded = content.casefold()
        matching = sum(1 for line in lines if folded in line.casefold())
        what = f'contain "{content}"'
    if not case_sensitive:
        what += ' (case-insensitive)'
    ok, message = compare_count(matching, expected_count, comparison_type)
    details = [f'{matching} of {len(lines)} line(s) {what}', message]
    return TestResult.success(details) if ok else TestResult.failed(details)


def _line_matcher(pattern: str, regex: bool, case_sensitive: bool):
    """A predicate ``line -> bool`` for one pattern of lines_in_order.

    :raises re.error: invalid regex
    """
    if regex:
        try:
            compiled = re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)
        except re.error as e:
            raise re.error(f'invalid regex pattern {pattern!r}: {e}') from e
        return lambda line: compiled.search(line) is not None
    if case_sensitive:
        return lambda line: pattern in line
    folded = pattern.casefold()
    return lambda line: folded in line.casefold()


def _order_parameter_errors(ctx: TestContext, patterns, regex, case_sensitive) -> list[str]:
    """Problems with the parameters of lines_in_order (an ERROR, the file is never read)."""
    if not isinstance(patterns, list) or not patterns:
        return [f'patterns must be a non-empty list of strings, got {patterns!r}']
    problems = []
    for i, pattern in enumerate(patterns, 1):
        if not isinstance(pattern, str) or not pattern:
            problems.append(f'pattern {i} must be a non-empty string, got {pattern!r}')
        else:
            problems += _placeholder_problems(ctx, pattern, 'regex: true with a plain pattern')
    for name, value in (('regex', regex), ('case_sensitive', case_sensitive)):
        if not isinstance(value, bool):
            problems.append(f'{name} must be true or false, got {value!r}')
    return problems


def _first_after(lines: list[str], matches, after: int) -> int | None:
    """Index of the first line after index ``after`` that ``matches``, or None."""
    for index in range(after + 1, len(lines)):
        if matches(lines[index]):
            return index
    return None


@testfunction(
    name='lines_in_order',
    description='tests that lines matching each of several patterns occur in the given order',
    category=HostModeCategory.FILE_CONTENT,
)
def lines_in_order(
    ctx: TestContext,
    dst: str,
    patterns: list,
    regex: bool = False,
    case_sensitive: bool = True,
    encoding: str | None = 'utf-8',
):
    """Pass when each of ``patterns`` matches a line of text file ``dst`` after the line of the pattern before it.

    Use for: the order of events in a log (a service started, then a file was opened, then
    deleted); a sequence of steps in a history or journal file. Lines between the matched
    ones are ignored. For how often one pattern occurs use text.line_count; for JSON Lines
    records use jsonl.lines_in_order.

    Each pattern takes the earliest line after the line of the previous pattern, so two
    patterns never match the same line; when that fails, no other choice of lines would
    pass either. Details list the matched line numbers (counted from 1); a FAILED result
    names the first pattern without a later line and, if it occurs only before, those
    earlier line numbers.

    Args:
        dst: Guest path to the text file; a glob must match exactly one path, an archive
            member (``logs.tar.gz!/service.log``) is read like a file. A missing file or
            content not valid in the encoding is an error. Lines end at ``\\n``, ``\\r\\n``
            or ``\\r``.
        patterns: Non-empty list of non-empty strings, in the expected order. Each is a
            substring a line must contain, or with ``regex`` a regex searched in each line
            (``re.search``). An empty list, a non-string, an invalid regex, or a ``!re`` /
            ``{{placeholder}}`` value is an error: write regexes as plain strings with ``regex``.
        regex: Treat every pattern as a regex.
        case_sensitive: ``True`` (default) matches case exactly; ``False`` compares substrings
            after casefolding, or compiles the regexes with ``re.IGNORECASE``.
        encoding: Text encoding, default ``utf-8``; ``None`` also detects BOM-less UTF-16.
            A BOM always wins. Unknown names are an error.

    Example:
        function: text.lines_in_order
        parameter:
          dst: /var/log/app/service.log
          patterns:
            - 'service started'
            - 'opened .*report\\.txt'
            - 'deleted .*report\\.txt'
          regex: true
    """
    problems = _order_parameter_errors(ctx, patterns, regex, case_sensitive)
    if problems:
        return TestResult.error(problems)
    try:
        if encoding is not None:
            codecs.lookup(encoding)
        matchers = [_line_matcher(p, regex, case_sensitive) for p in patterns]
    except (LookupError, TypeError) as e:
        return TestResult.error([f'invalid encoding {encoding!r}: {e}'])
    except re.error as e:
        return TestResult.error([str(e)])
    path, status = ctx.resolve_globfilepath(dst)
    data, error = _read(path, dst, status)
    if error is not None:
        return error
    try:
        lines = _split_lines(decode_text(data, encoding))
    except UnicodeDecodeError as e:
        return TestResult.execution_error(e, f'Cannot decode {dst} as {encoding or "UTF-8/UTF-16"}')

    matched: list[str] = []
    previous = -1
    for number, (pattern, matches) in enumerate(zip(patterns, matchers, strict=True), 1):
        index = _first_after(lines, matches, previous)
        if index is None:
            earlier = [i + 1 for i in range(previous + 1) if matches(lines[i])]
            where = f'after line {previous + 1}' if previous >= 0 else 'in the file'
            message = f'pattern {number} {pattern!r} matches no line {where} ({len(lines)} line(s))'
            if earlier:
                shown = ', '.join(str(n) for n in earlier[:10]) + (', ...' if len(earlier) > 10 else '')
                message += f'; it occurs only earlier, on line(s) {shown}: out of order'
            return TestResult.failed([message, *matched])
        matched.append(f'pattern {number} {pattern!r} matched line {index + 1}')
        previous = index
    lines_found = ', '.join(m.rsplit(' ', 1)[1] for m in matched)
    return TestResult.success([f'{len(patterns)} pattern(s) matched in order on lines {lines_found}', *matched])
