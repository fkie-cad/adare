# external imports
import plistlib
import xml.parsers.expat

# internal imports
from adarelib.testset import structured, valuecompare
from adarelib.testset.api import testfunction
from adarelib.testset.basictest import HostModeCategory


def _load(path: str):
    """Read an XML or binary property list (the format is detected from the content)."""
    with open(path, 'rb') as f:
        return plistlib.load(f)


# What plistlib.load raises for content that is not a valid property list (same on 3.10 and 3.13):
# InvalidFileException (a ValueError) for unknown headers, entity declarations and every corrupt
# binary plist; ExpatError for malformed XML; ValueError for an XML plist with a wrong structure,
# an unknown element, or a bad integer/real/base64 value; AttributeError for an unparsable <date>;
# LookupError for an unknown encoding in the XML declaration.
PLIST = structured.StructuredFormat(
    label='plist',
    load=_load,
    errors=(plistlib.InvalidFileException, xml.parsers.expat.ExpatError, ValueError, AttributeError, LookupError),
)


@testfunction(
    name='contains_key',
    description='tests if a property list (XML or binary plist) contains the specified key path',
    category=HostModeCategory.FILE_CONTENT,
)
def contains_key(ctx, dst: str, key_path: str):
    """Pass when ``key_path`` resolves to at least one value in property list ``dst``.

    Use for: checking that a preferences/settings plist gained a key. To also check the value
    use plist.value_matches; to check that a key is absent use plist.value_count with
    ``expected_count: 0`` (or ``expect_to_fail: true`` here: a missing file stays an error).

    Args:
        dst: Guest path to the plist; XML and binary plists are detected from the content. A
            glob must match exactly one path; ``archive.zip!/member.plist`` reads an archive
            member. A missing, unreadable or invalid file is an error.
        key_path: Dot path from the root dictionary, e.g. ``window.frame``. Keys that contain
            dots use quotes in brackets (``['com.example.lastVersion']``, also mid-path:
            ``recent['com.example.doc'].name``). ``*`` expands all values of a dictionary,
            ``name[*]`` all elements of array ``name``, ``name[0]`` / ``name[-1]`` one
            element; a leading ``[0]`` / ``[*]`` addresses a top-level array.

    Example:
        function: plist.contains_key
        parameter:
          dst: /home/user/Library/Preferences/com.example.app.plist
          key_path: "['com.example.lastVersion']"
    """
    return structured.contains_key(ctx, dst, key_path, PLIST)


@testfunction(
    name='value_matches',
    description='tests if the property list value at a key path matches the expected value (dates as ISO strings, data as hex)',
    category=HostModeCategory.FILE_CONTENT,
)
def value_matches(
    ctx,
    dst: str,
    key_path: str,
    expected_value: str | int | float | bool | None,
    regex_match: bool = False,
    wildcard_mode: str = 'any',
    comparison_type: str = 'equals',
    value_type: str = 'auto',
    tolerance: int | float | None = None,
    time_format: str | None = None,
    timestamp_epoch: int | None = None,
    timestamp_unit: str | None = None,
    utc_offset: str | None = None,
):
    """Pass when the plist value at ``key_path`` in ``dst`` equals (or matches) ``expected_value``.

    Use for: asserting a preference value. If the path yields several values (a wildcard, or
    an array value, whose elements are then compared one by one) ``wildcard_mode`` decides.
    Values are normalised before comparing: ``<date>`` becomes an ISO 8601 string without
    zone (plist dates are UTC, ``2024-01-15T10:30:00``), ``<data>`` a lowercase hex string
    (``0a1b``), ``<integer>``/``<real>``/``<true/>`` stay numbers and booleans.

    With ``comparison_type`` (``greater``, ``less``, ...), ``tolerance`` or the time
    parameters the value is compared as a number or timestamp; to compare two values of one
    file use plist.values_compare.

    Args:
        dst: Guest path to the plist (XML or binary, detected from the content); a glob must
            match exactly one path. A missing or invalid file is an error; an unresolvable key
            path fails.
        key_path: Dot path from the root dictionary; ``['com.example.key']`` for keys with
            dots, ``*`` all values of a dictionary, ``name[*]`` / ``name[0]`` array elements,
            a leading ``[0]`` / ``[*]`` for a top-level array.
        expected_value: Compared with Python ``==``, which is type-sensitive (``5`` != ``"5"``).
            A ``!re`` tag (``re.match``) or ``{{placeholder}}`` compares ``str(value)``.
        regex_match: Treat a string ``expected_value`` as a regex searched (``re.search``,
            unanchored) in ``str(value)``. An invalid regex is an error.
        wildcard_mode: ``any`` (default): one value must match; ``all``: every value must
            match. Other values are an error.
        comparison_type: ``equals`` (default), ``not_equals``, ``greater``, ``less``,
            ``greater_equal`` or ``less_equal``. Anything but ``equals``, or any parameter
            below, compares the value with ``expected_value`` as a number or point in time
            (ordered mode; ``less`` = earlier); a ``!re`` tag, ``{{placeholder}}`` or
            ``regex_match`` is then an error, and so is a value that is no number or timestamp.
        value_type: ``auto`` (default; numbers if both sides are numbers, else timestamps),
            ``number`` or ``timestamp``.
        tolerance: Allowed difference for ``equals``/``not_equals`` (seconds for timestamps).
        time_format: ``strptime`` format of text timestamps on both sides; default ISO 8601 or RFC 2822.
        timestamp_epoch: Read numbers as a count since 1 January of ``1970``, ``1601`` or ``2001``.
        timestamp_unit: Unit of that count: ``s`` (default), ``ms``, ``us``, ``ns`` or ``100ns``.
        utc_offset: Zone of timestamps without one (``+02:00``); default UTC.

    Example:
        function: plist.value_matches
        parameter:
          dst: /home/user/Library/Preferences/com.example.app.plist
          key_path: "['com.example.lastLaunch']"
          expected_value: !re '^2024-01-15T'
    """
    return structured.value_matches(
        ctx,
        dst,
        key_path,
        expected_value,
        PLIST,
        regex_match,
        wildcard_mode,
        comparison_type=comparison_type,
        value_type=value_type,
        tolerance=tolerance,
        time_format=time_format,
        timestamp_epoch=timestamp_epoch,
        timestamp_unit=timestamp_unit,
        utc_offset=utc_offset,
    )


@testfunction(
    name='value_count',
    description='tests how many property list values exist at a key path, optionally only those matching a value (0 = absent)',
    category=HostModeCategory.FILE_CONTENT,
)
def value_count(
    ctx,
    dst: str,
    key_path: str,
    expected_count: int,
    expected_value: str | int | float | bool | None = None,
    regex_match: bool = False,
    comparison_type: str = 'equals',
):
    """Pass when the number of values at ``key_path`` in plist ``dst`` compares to ``expected_count``.

    Use for: counting entries (``recent[*]``) and asserting absence: ``expected_count: 0``
    passes when the key path selects nothing (or nothing matches ``expected_value``), while a
    missing or invalid file is still an error. A path that selects one array counts its
    elements when ``expected_value`` is given; without it every selected value counts once.

    Args:
        dst: Guest path to the plist (XML or binary, detected from the content); a glob must
            match exactly one path.
        key_path: Dot path from the root dictionary (syntax as in plist.contains_key).
        expected_count: Non-negative integer to compare with.
        expected_value: Only count values equal to this (normalised as in plist.value_matches:
            dates are ISO strings, data is hex). ``None`` (default) counts every value.
        regex_match: Treat a string ``expected_value`` as a regex searched in ``str(value)``.
        comparison_type: ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or
            ``less_equal``. Other values are an error.

    Example:
        function: plist.value_count
        parameter:
          dst: /home/user/Library/Preferences/com.example.app.plist
          key_path: "['com.example.recentDocuments'][*]"
          expected_count: 0
    """
    return structured.value_count(
        ctx, dst, key_path, expected_count, PLIST, expected_value, regex_match, comparison_type
    )


@testfunction(
    name='values_compare',
    description='compares two values of one property list file as numbers or timestamps (earlier/later, within a tolerance, A = B + offset)',
    category=HostModeCategory.FILE_CONTENT,
)
def values_compare(
    ctx,
    dst: str,
    key_path: str,
    other_key_path: str,
    comparison_type: str = 'equals',
    value_type: str = 'auto',
    tolerance: int | float | None = None,
    offset: int | float | None = None,
    time_format: str | None = None,
    timestamp_epoch: int | None = None,
    timestamp_unit: str | None = None,
    utc_offset: str | None = None,
):
    """Pass when the value at ``key_path`` compares to the value at ``other_key_path`` (+ ``offset``).

    Use for: relations inside one file: a last-saved value later than the first-opened one,
    two timestamps within a few seconds of each other, a counter one above another
    (``comparison_type: equals`` with ``offset: 1``). To compare one value with a constant
    use plist.value_matches with ``comparison_type``.

    Args:
        dst: Guest path to the plist (XML or binary, detected from the content); a glob must
            match exactly one path. A missing or invalid file is an error. ``<date>`` values
            are UTC.
        key_path: Dot path of the first value (syntax as in plist.contains_key). It must select
            exactly one value (a one-element array counts as its element): nothing fails,
            several values are an error.
        other_key_path: Dot path of the second value; same rules.
        comparison_type: How the first value relates to the second: ``equals`` (default),
            ``not_equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal``
            (``less`` = earlier for timestamps). Other values are an error.
        value_type: ``auto`` (default; numbers if both are numbers, else timestamps),
            ``number`` or ``timestamp``. A value that is no number or timestamp is an error.
        tolerance: Allowed difference for ``equals``/``not_equals`` (seconds for timestamps).
        offset: Added to the second value before comparing (seconds for timestamps, may be
            negative): ``first <comparison_type> second + offset``.
        time_format: ``strptime`` format of text timestamps on both sides; default ISO 8601 or RFC 2822.
        timestamp_epoch: Read numbers as a count since 1 January of ``1970``, ``1601`` or ``2001``.
        timestamp_unit: Unit of that count: ``s`` (default), ``ms``, ``us``, ``ns`` or ``100ns``.
        utc_offset: Zone of timestamps without one (``+02:00``); default UTC.

    Example:
        function: plist.values_compare
        parameter:
          dst: /home/user/Library/Preferences/com.example.app.plist
          key_path: "['com.example.lastSave']"
          other_key_path: "['com.example.lastLaunch']"
          comparison_type: greater_equal
    """
    return valuecompare.structured_values_compare(
        ctx,
        dst,
        key_path,
        other_key_path,
        PLIST,
        comparison_type,
        value_type,
        tolerance,
        offset,
        time_format,
        timestamp_epoch,
        timestamp_unit,
        utc_offset,
    )
