# INI-style configuration files, read with an own tolerant line parser.
#
# configparser is deliberately not used: it rejects duplicate sections and keys, lines
# without a separator and keys before the first section, interpolates ``%(name)s`` and
# lower-cases keys. Files under test are written by arbitrary applications and often do
# all of these, and a parser that refuses or rewrites them would hide the evidence.
#
# Parsing rules (documented in every function's docstring and the reference pages):
#   * ``[name]`` starts a section (name stripped); keys before any header are in section ``''``
#   * lines whose first non-blank character is ``;`` or ``#`` are comments, blank lines skipped
#   * the first ``=`` splits key and value, both stripped; values are raw (no quote
#     stripping, no inline-comment removal, no interpolation, no continuation lines)
#   * lines without ``=`` (that are not headers or comments) are ignored
#   * duplicate sections and duplicate keys are all kept, in file order
#
# Standard library only (plus adarelib), importable on the guests' Python 3.10.

import re
from dataclasses import dataclass
from typing import Any

# internal imports
from adarelib.testset.api import testfunction
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult
from adarelib.testset.compare import regex_expected_problem
from adarelib.testset.content import decode_text, read_bytes_capped
from adarelib.testset.structured import WILDCARD_MODES, compare_count, compare_value, count_parameter_errors
from adarelib.testset.ordering import OrderingError
from adarelib.testset.valuecompare import ordered_setup
from adarelib.testset.valuedecode import DecodedKeyPathMissing, ValueDecodeError, decoder_setup

# configure logging
import logging

log = logging.getLogger(__name__)

COMMENT_PREFIXES = (';', '#')


@dataclass(frozen=True)
class IniEntry:
    """One ``key = value`` line."""

    section: str
    key: str
    value: str
    line: int


@dataclass(frozen=True)
class IniFile:
    """Parsed file: every section header (duplicates kept) and every entry, in file order."""

    sections: tuple[str, ...]
    entries: tuple[IniEntry, ...]


# =============================================================================
# Parsing
# =============================================================================


def _section_header(line: str) -> str | None:
    """Section name if ``line`` (stripped) is a ``[name]`` header, else None.

    A comment after the closing bracket is allowed (``[name] ; note``).
    """
    if not line.startswith('['):
        return None
    if line.endswith(']'):
        return line[1:-1].strip()
    close = line.find(']')
    if close != -1 and line[close + 1 :].lstrip().startswith(COMMENT_PREFIXES):
        return line[1:close].strip()
    return None


def parse_ini(text: str) -> IniFile:
    """Parse INI text with the tolerant rules described at the top of this module."""
    sections: list[str] = []
    entries: list[IniEntry] = []
    current = ''
    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith(COMMENT_PREFIXES):
            continue
        header = _section_header(line)
        if header is not None:
            current = header
            sections.append(header)
            continue
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        entries.append(IniEntry(current, key.strip(), value.strip(), number))
    return IniFile(tuple(sections), tuple(entries))


def _load_ini(resolved: tuple[str, str], dst: str, encoding: str | None) -> tuple[IniFile | None, TestResult | None]:
    """Read and parse the file ``ctx.resolve_globfilepath(dst)`` gave (``resolved``).

    Returns ``(ini, None)`` or ``(None, error_result)``.
    """
    path, status = resolved
    if not path:
        return None, TestResult.error([f'INI file {dst} not found ({status})'])
    log.debug(f'dst file {path} will be used for this INI test')
    try:
        raw = read_bytes_capped(path)
    except FileNotFoundError:
        return None, TestResult.error([f'INI file {path} does not exist'])
    except IsADirectoryError:
        return None, TestResult.error([f'INI file {path} is a directory'])
    except OSError as e:
        return None, TestResult.execution_error(e, f'Cannot read INI file {path}')
    try:
        text = decode_text(raw, encoding)
    except UnicodeDecodeError as e:
        return None, TestResult.execution_error(e, f'Cannot decode INI file {path}')
    except LookupError as e:
        return None, TestResult.error([f'unknown encoding {encoding!r}: {e}'])
    return parse_ini(text), None


# =============================================================================
# Matching helpers
# =============================================================================


def _same_name(a: str, b: str, case_sensitive: bool) -> bool:
    return a == b if case_sensitive else a.casefold() == b.casefold()


def _entries(ini: IniFile, section: str, key: str, case_sensitive: bool) -> list[IniEntry]:
    """All entries for ``key`` in every occurrence of ``section``."""
    return [
        e
        for e in ini.entries
        if _same_name(e.section, section, case_sensitive) and _same_name(e.key, key, case_sensitive)
    ]


def _expected_text(expected: Any) -> Any:
    """INI values are text: compare a YAML number/bool as its text (``8080``, ``true``)."""
    if isinstance(expected, bool):
        return 'true' if expected else 'false'
    if isinstance(expected, (int, float)):
        return str(expected)
    return expected


def _where(section: str, key: str) -> str:
    return f'key "{key}" in section [{section}]'


# =============================================================================
# Testfunctions
# =============================================================================


@testfunction(
    name='section_exists',
    description='tests if an INI file contains a section',
    category=HostModeCategory.FILE_CONTENT,
)
def section_exists(ctx, dst: str, section: str, case_sensitive: bool = True, encoding: str = None):
    """Pass when the INI file ``dst`` has at least one ``[section]`` header.

    Use for: checking a settings file gained a section. For "absent" use ``expect_to_fail``
    (or ini.value_count with ``expected_count: 0`` for a key).

    Args:
        dst: Guest path to the INI file; a glob must match exactly one path. A missing,
            unreadable or undecodable file is an error.
        section: Section name without brackets, compared after stripping. Keys before the
            first header belong to section ``''``, which exists only as a header ``[]``.
        case_sensitive: ``False`` compares section names case-insensitively.
        encoding: Text encoding; default auto: a BOM wins, BOM-less UTF-16 is recognised,
            everything else is read as UTF-8. An unknown name is an error.

    Example:
        function: ini.section_exists
        parameter:
          dst: /home/user/.config/app/settings.ini
          section: General
    """
    ini, error = _load_ini(ctx.resolve_globfilepath(dst), dst, encoding)
    if error is not None:
        return error
    found = [s for s in ini.sections if _same_name(s, section, case_sensitive)]
    if found:
        return TestResult.success([f'section [{section}] found ({len(found)} header(s))'])
    return TestResult.failed([f'section [{section}] not found', f'sections: {", ".join(ini.sections) or "(none)"}'])


@testfunction(
    name='contains_key',
    description='tests if an INI file contains a key in a section',
    category=HostModeCategory.FILE_CONTENT,
)
def contains_key(ctx, dst: str, section: str, key: str, case_sensitive: bool = True, encoding: str = None):
    """Pass when ``section`` of the INI file ``dst`` has a ``key = ...`` line (an empty value counts).

    Use for: checking a setting was written, whatever its value. For "absent" use
    ini.value_count with ``expected_count: 0``.

    Args:
        dst: Guest path to the INI file; a glob must match exactly one path. A missing,
            unreadable or undecodable file is an error.
        section: Section name without brackets; ``''`` = keys before the first header.
            Duplicate sections are searched together.
        key: Key name, compared after stripping. The first ``=`` on a line splits key and
            value; lines without ``=`` are ignored, so a bare word is not a key.
        case_sensitive: ``False`` compares section and key names case-insensitively.
        encoding: Text encoding; default auto: a BOM wins, BOM-less UTF-16 is recognised,
            everything else is read as UTF-8. An unknown name is an error.

    Example:
        function: ini.contains_key
        parameter:
          dst: /home/user/.config/app/settings.ini
          section: General
          key: last_opened
    """
    ini, error = _load_ini(ctx.resolve_globfilepath(dst), dst, encoding)
    if error is not None:
        return error
    found = _entries(ini, section, key, case_sensitive)
    if found:
        return TestResult.success([f'{_where(section, key)} exists with value: {found[0].value}'])
    return TestResult.failed([f'{_where(section, key)} does not exist'])


@testfunction(
    name='value_matches',
    description='tests if an INI value equals or matches an expected value (regex and placeholders supported)',
    category=HostModeCategory.FILE_CONTENT,
)
def value_matches(
    ctx,
    dst: str,
    section: str,
    key: str,
    expected_value: str | int | float | bool,
    regex_match: bool = False,
    case_sensitive: bool = True,
    encoding: str = None,
    wildcard_mode: str = 'any',
    comparison_type: str = 'equals',
    value_type: str = 'auto',
    tolerance: int | float | None = None,
    time_format: str | None = None,
    timestamp_epoch: int | None = None,
    timestamp_unit: str | None = None,
    utc_offset: str | None = None,
    value_decode: list[str] | str | None = None,
    decoded_key_path: str | None = None,
):
    """Pass when the value of ``key`` in ``section`` of ``dst`` equals (or matches) ``expected_value``.

    Use for: asserting a setting's value. With duplicate keys or sections, one matching
    occurrence is enough (``wildcard_mode: all``: every occurrence must match). A missing
    key fails.

    With ``comparison_type`` (``greater``, ``less``, ...), ``tolerance`` or the time
    parameters the value is compared as a number or timestamp.

    Args:
        dst: Guest path to the INI file; a glob must match exactly one path. A missing,
            unreadable or undecodable file is an error.
        section: Section name without brackets; ``''`` = keys before the first header.
        key: Key name; the first ``=`` on a line splits key and value.
        expected_value: Compared with the raw value text (stripped; quotes and inline
            comments are kept, ``a = "x" ; note`` has the value ``"x" ; note``). A YAML
            number or boolean is compared as its text (``8080``, ``true``/``false``). A
            ``!re``/``!timestamp`` tag or ``{{placeholder}}`` is matched by type.
        regex_match: Search ``expected_value`` as a Python regex (``re.search``, unanchored).
            An invalid regex is an error even when the key is absent.
        case_sensitive: ``False`` compares section and key names case-insensitively; values
            are always compared as given.
        encoding: Text encoding; default auto (BOM, BOM-less UTF-16, else UTF-8).
        wildcard_mode: With several occurrences, ``any`` (default): one must match; ``all``:
            every one must match. Other values are an error.
        comparison_type: ``equals`` (default), ``not_equals``, ``greater``, ``less``,
            ``greater_equal`` or ``less_equal``. Anything but ``equals``, or any parameter
            below, compares the value with ``expected_value`` as a number or point in time
            (ordered mode; ``less`` = earlier); ``!re`` / ``regex_match`` are then errors, a lone
            ``{{ name }}`` is the saved variable; a value that is no number or timestamp is an error.
        value_type: ``auto`` (default; numbers if both sides are numbers, else timestamps),
            ``number`` or ``timestamp``.
        tolerance: Allowed difference for ``equals``/``not_equals`` (seconds for timestamps).
        time_format: ``strptime`` format of text timestamps on both sides; default ISO 8601 or RFC 2822.
        timestamp_epoch: Read numbers as a count since 1 January of ``1970``, ``1601`` or ``2001``.
        timestamp_unit: Unit of that count: ``s`` (default), ``ms``, ``us``, ``ns`` or ``100ns``.
        utc_offset: Zone of timestamps without one (``+02:00``); default UTC.
        value_decode: Decode the value read from the file before comparing: one step or a
            list applied in order: ``url`` (percent-decoding), ``base64``, ``hex``, ``utf16``
            (bytes as UTF-16 text), ``json`` (parse, then take ``decoded_key_path``). Bytes
            left at the end are UTF-8 text, else hex. A value a step cannot decode, or an
            unknown step, is an error.
        decoded_key_path: Key path into the value ``json`` decoded (dot path as in json.value_matches);
            it must select one value: none fails (the value decoded, the key is not in it), several are an error.
            Required with ``json``, an error without it.

    Example:
        function: ini.value_matches
        parameter:
          dst: /home/user/.config/app/settings.ini
          section: General
          key: language
          expected_value: de_DE
    """
    if wildcard_mode not in WILDCARD_MODES:
        return TestResult.error([f"Invalid wildcard_mode: {wildcard_mode}. Must be 'any' or 'all'"])
    decoder, problem = decoder_setup(value_decode, decoded_key_path)
    if problem is not None:
        return problem
    ordered, expected_value, problem = ordered_setup(
        ctx,
        expected_value,
        regex_match,
        comparison_type,
        value_type,
        tolerance,
        time_format,
        timestamp_epoch,
        timestamp_unit,
        utc_offset,
    )
    if problem is not None:
        return problem
    if ordered is None:
        problem = regex_expected_problem(ctx, [expected_value], regex_match)
        if problem is not None:
            return problem
    ini, error = _load_ini(ctx.resolve_globfilepath(dst), dst, encoding)
    if error is not None:
        return error
    found = _entries(ini, section, key, case_sensitive)
    if not found:
        return TestResult.failed([f'{_where(section, key)} does not exist'])
    expected = _expected_text(expected_value)
    results = []
    try:
        for e in found:
            v = e.value
            if decoder is not None:
                try:
                    v = decoder(v, as_text=True)
                except DecodedKeyPathMissing as missing:  # decoded fine, the key is not in it: no match
                    results.append((e, False, str(missing)))
                    continue
            if ordered is not None:
                results.append((e, *ordered.compare(v, expected)))
            else:
                results.append((e, *compare_value(ctx, v, expected, regex_match)))
    except (re.error, OrderingError, ValueDecodeError) as e:
        return TestResult.error([str(e)])
    if len(results) == 1:
        _, ok, message = results[0]
        return TestResult.success([message]) if ok else TestResult.failed([message])
    matching = [e for e, ok, _ in results if ok]
    head = f'{_where(section, key)}: {len(matching)}/{len(results)} occurrences match (mode: {wildcard_mode})'
    passed = bool(matching) if wildcard_mode == 'any' else len(matching) == len(results)
    if passed:
        return TestResult.success([head, f'matching value at line {matching[0].line}: {matching[0].value}'])
    misses = ', '.join([f'line {e.line}: {e.value}' for e, ok, _ in results if not ok][:5])
    return TestResult.failed([head, f'expected: "{expected_value}"', f'non-matching values: {misses}'])


@testfunction(
    name='value_count',
    description='tests the number of occurrences of an INI key (optionally with a matching value)',
    category=HostModeCategory.FILE_CONTENT,
)
def value_count(
    ctx,
    dst: str,
    section: str,
    key: str,
    expected_count: int,
    expected_value: str | int | float | bool | None = None,
    regex_match: bool = False,
    comparison_type: str = 'equals',
    case_sensitive: bool = True,
    encoding: str = None,
):
    """Pass when the number of ``key`` lines in ``section`` (whose value matches ``expected_value``,
    if given) satisfies ``comparison_type`` against ``expected_count``.

    Use for: duplicate keys (lists written as repeated keys) and absence: ``expected_count: 0``
    asserts the key (or the key with that value) is not in the section.

    Args:
        dst: Guest path to the INI file; a glob must match exactly one path. A missing,
            unreadable or undecodable file is an error.
        section: Section name without brackets; ``''`` = keys before the first header.
            Occurrences in duplicate sections are added up.
        key: Key name; the first ``=`` on a line splits key and value.
        expected_count: Required non-negative integer to compare against; anything else is
            an error.
        expected_value: Count only occurrences whose raw value equals/matches this (same
            rules as ini.value_matches); ``None`` (default) counts every occurrence.
        regex_match: Search ``expected_value`` as a Python regex (``re.search``, unanchored).
            An invalid regex is an error even when the key is absent.
        comparison_type: ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or
            ``less_equal``; other values are an error.
        case_sensitive: ``False`` compares section and key names case-insensitively.
        encoding: Text encoding; default auto (BOM, BOM-less UTF-16, else UTF-8).

    Example:
        function: ini.value_count
        parameter:
          dst: /home/user/.config/app/settings.ini
          section: RecentFiles
          key: file
          expected_value: /home/user/Documents/report.txt
          expected_count: 1
    """
    resolved = ctx.resolve_globfilepath(dst)
    problems = count_parameter_errors(expected_count, comparison_type)
    if problems:
        return TestResult.error(problems)
    if expected_value is not None:
        problem = regex_expected_problem(ctx, [expected_value], regex_match)
        if problem is not None:
            return problem
    ini, error = _load_ini(resolved, dst, encoding)
    if error is not None:
        return error
    found = _entries(ini, section, key, case_sensitive)
    if expected_value is None:
        actual = len(found)
        what = f'{actual} occurrence(s) of {_where(section, key)}'
    else:
        expected = _expected_text(expected_value)
        try:
            actual = sum(1 for e in found if compare_value(ctx, e.value, expected, regex_match)[0])
        except re.error as e:
            return TestResult.error([str(e)])
        what = f'{actual} occurrence(s) of {_where(section, key)} match "{expected_value}"'
    ok, message = compare_count(actual, expected_count, comparison_type)
    details = [what, message]
    return TestResult.success(details) if ok else TestResult.failed(details)
