# external imports
# The loader imports this file under a path-derived module name and never puts the collection
# directory on sys.path, so neither import can resolve to this module.
try:
    import tomllib  # Python 3.11+
except ImportError:  # the guests' Python 3.10: the API-compatible backport
    import tomli as tomllib

# internal imports
from adarelib.testset import structured
from adarelib.testset.api import testfunction
from adarelib.testset.basictest import HostModeCategory


def _load(path: str):
    """Read a TOML document (binary mode, as tomllib requires; TOML is always UTF-8)."""
    with open(path, 'rb') as f:
        return tomllib.load(f)


# TOMLDecodeError (a ValueError) covers syntax errors, duplicate keys and invalid dates/times;
# bytes that are not UTF-8 raise UnicodeDecodeError, which structured.load_data maps to ERROR.
TOML = structured.StructuredFormat(label='TOML', load=_load, errors=(tomllib.TOMLDecodeError,))


@testfunction(
    name='contains_key',
    description='tests if a TOML file contains the specified key path (tables, arrays of tables)',
    category=HostModeCategory.FILE_CONTENT,
)
def contains_key(ctx, dst: str, key_path: str):
    """Pass when ``key_path`` resolves to at least one value in TOML file ``dst``.

    Use for: checking that a settings/config file gained a key. To also check the value use
    toml.value_matches; to check that a key is absent use toml.value_count with
    ``expected_count: 0`` (or ``expect_to_fail: true`` here: a missing file stays an error).

    Args:
        dst: Guest path to the TOML file (UTF-8). A glob must match exactly one path;
            ``archive.zip!/member.toml`` reads an archive member. A missing, unreadable or
            invalid file is an error.
        key_path: Dot path from the root table; ``[server]`` / ``server.port = 1`` are both
            ``server.port``. An array of tables (``[[items]]``) is an array: ``items[*].name``
            for all entries, ``items[0].name`` / ``items[-1].name`` for one. ``*`` expands all
            values of a table (``profiles.*.enabled``). Keys with dots (quoted TOML keys such
            as ``"app.window"``) use quotes in brackets: ``['app.window'].width``.

    Example:
        function: toml.contains_key
        parameter:
          dst: /home/user/.config/app/settings.toml
          key_path: server.port
    """
    return structured.contains_key(ctx, dst, key_path, TOML)


@testfunction(
    name='value_matches',
    description='tests if the TOML value at a key path matches the expected value (dates/times as ISO strings)',
    category=HostModeCategory.FILE_CONTENT,
)
def value_matches(
    ctx,
    dst: str,
    key_path: str,
    expected_value: str | int | float | bool | None,
    regex_match: bool = False,
    wildcard_mode: str = 'any',
):
    """Pass when the TOML value at ``key_path`` in ``dst`` equals (or matches) ``expected_value``.

    Use for: asserting a setting/field value. If the path yields several values (a wildcard,
    or an array value, whose elements are then compared one by one) ``wildcard_mode``
    decides. Values keep their TOML types (integers, floats, booleans, strings); dates and
    times become ISO 8601 strings: ``1979-05-27``, ``07:32:00``, ``1979-05-27T07:32:00``
    (local) or ``1979-05-27T07:32:00-08:00`` (``Z`` becomes ``+00:00``).

    Args:
        dst: Guest path to the TOML file; a glob must match exactly one path. A missing or
            invalid file is an error; an unresolvable key path fails.
        key_path: Dot path from the root table (syntax as in toml.contains_key), e.g.
            ``items[*].name`` for every ``[[items]]`` entry.
        expected_value: Compared with Python ``==``, which is type-sensitive (``5`` != ``"5"``).
            A ``!re`` tag (``re.match``) or ``{{placeholder}}`` compares ``str(value)``.
        regex_match: Treat a string ``expected_value`` as a regex searched (``re.search``,
            unanchored) in ``str(value)``. An invalid regex is an error.
        wildcard_mode: ``any`` (default): one value must match; ``all``: every value must
            match. Other values are an error.

    Example:
        function: toml.value_matches
        parameter:
          dst: /home/user/.config/app/settings.toml
          key_path: items[*].name
          expected_value: Example Entry
    """
    return structured.value_matches(ctx, dst, key_path, expected_value, TOML, regex_match, wildcard_mode)


@testfunction(
    name='value_count',
    description='tests how many TOML values exist at a key path, optionally only those matching a value (0 = absent)',
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
    """Pass when the number of values at ``key_path`` in TOML file ``dst`` compares to ``expected_count``.

    Use for: counting entries (``items[*]`` for ``[[items]]``) and asserting absence:
    ``expected_count: 0`` passes when the key path selects nothing (or nothing matches
    ``expected_value``), while a missing or invalid file is still an error. A path that
    selects one array counts its elements when ``expected_value`` is given; without it every
    selected value counts once.

    Args:
        dst: Guest path to the TOML file; a glob must match exactly one path.
        key_path: Dot path from the root table (syntax as in toml.contains_key).
        expected_count: Non-negative integer to compare with.
        expected_value: Only count values equal to this (normalised as in toml.value_matches).
            ``None`` (default) counts every value.
        regex_match: Treat a string ``expected_value`` as a regex searched in ``str(value)``.
        comparison_type: ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or
            ``less_equal``. Other values are an error.

    Example:
        function: toml.value_count
        parameter:
          dst: /home/user/.config/app/settings.toml
          key_path: items[*]
          expected_count: 2
    """
    return structured.value_count(
        ctx, dst, key_path, expected_count, TOML, expected_value, regex_match, comparison_type
    )
