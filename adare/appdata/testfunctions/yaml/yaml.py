# external imports
# The loader imports this file under a path-derived module name and never puts the collection
# directory on sys.path, so this is PyYAML, not this module.
import yaml

# internal imports
from adarelib.testset import structured
from adarelib.testset.api import testfunction
from adarelib.testset.basictest import HostModeCategory


def _load(path: str):
    """Read all documents (``safe_load_all``): one document is the root, several a list, none ``None``."""
    with open(path, 'rb') as f:  # bytes: PyYAML detects UTF-8/UTF-16 from the BOM
        documents = list(yaml.safe_load_all(f))
    if not documents:
        return None
    return documents[0] if len(documents) == 1 else documents


# YAMLError covers scanner/parser/composer/constructor/reader errors (also unknown tags and
# undecodable bytes); a timestamp-shaped value that is no real date (2024-02-30) raises ValueError.
YAML = structured.StructuredFormat(label='YAML', load=_load, errors=(yaml.YAMLError, ValueError))


@testfunction(
    name='contains_key',
    description='tests if a YAML file contains the specified key path (supports several documents)',
    category=HostModeCategory.FILE_CONTENT,
)
def contains_key(ctx, dst: str, key_path: str):
    """Pass when ``key_path`` resolves to at least one value in YAML file ``dst`` (``null`` counts).

    Use for: checking that a settings/config file gained a key. To also check the value use
    yaml.value_matches; to check that a key is absent use yaml.value_count with
    ``expected_count: 0`` (or ``expect_to_fail: true`` here: a missing file stays an error).

    Args:
        dst: Guest path to the YAML file (read with ``safe_load``; UTF-8, or UTF-16 with a
            BOM). A glob must match exactly one path; ``archive.zip!/member.yaml`` reads an
            archive member. A missing, unreadable or invalid file is an error. A file with
            several documents (``---``) is a top-level list, one per document; an empty file
            has no keys.
        key_path: Dot path from the root, e.g. ``display.font.size``. ``*`` expands all values
            of a mapping, ``name[*]`` all elements of sequence ``name``, ``name[0]`` /
            ``name[-1]`` one element; a leading ``[0]`` / ``[*]`` addresses a top-level
            sequence or a document of a multi-document file (``[1].kind``, ``[*].kind``).
            Keys with dots use quotes in brackets (``['app.window'].width``).

    Example:
        function: yaml.contains_key
        parameter:
          dst: /home/user/.config/app/config.yaml
          key_path: display.font.size
    """
    return structured.contains_key(ctx, dst, key_path, YAML)


@testfunction(
    name='value_matches',
    description='tests if the YAML value at a key path matches the expected value (supports wildcards with any/all modes)',
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
    """Pass when the YAML value at ``key_path`` in ``dst`` equals (or matches) ``expected_value``.

    Use for: asserting a setting/field value. If the path yields several values (a wildcard,
    or a sequence value, whose elements are then compared one by one) ``wildcard_mode``
    decides. Values keep their YAML 1.1 types (``5`` is an int, ``true``/``yes``/``on`` and
    ``false``/``no``/``off`` are booleans); dates and timestamps become ISO 8601 strings
    (``2024-01-15``, ``2024-01-15T10:30:00``, ``+00:00`` for a ``Z`` zone), ``!!binary`` a
    lowercase hex string.

    Args:
        dst: Guest path to the YAML file; a glob must match exactly one path. Several
            documents form a top-level list. A missing or invalid file is an error; an
            unresolvable key path fails.
        key_path: Dot path from the root (syntax as in yaml.contains_key), e.g.
            ``servers[*].port`` or ``[0].kind`` for the first document.
        expected_value: Compared with Python ``==``, which is type-sensitive (``5`` != ``"5"``;
            ``null`` needs ``null``). A ``!re`` tag (``re.match``) or ``{{placeholder}}``
            compares ``str(value)``.
        regex_match: Treat a string ``expected_value`` as a regex searched (``re.search``,
            unanchored) in ``str(value)``. An invalid regex is an error.
        wildcard_mode: ``any`` (default): one value must match; ``all``: every value must
            match. Other values are an error.

    Example:
        function: yaml.value_matches
        parameter:
          dst: /home/user/.config/app/config.yaml
          key_path: servers[*].port
          expected_value: 8080
          wildcard_mode: all
    """
    return structured.value_matches(ctx, dst, key_path, expected_value, YAML, regex_match, wildcard_mode)


@testfunction(
    name='value_count',
    description='tests how many YAML values exist at a key path, optionally only those matching a value (0 = absent)',
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
    """Pass when the number of values at ``key_path`` in YAML file ``dst`` compares to ``expected_count``.

    Use for: counting entries (``recent[*]``, documents ``[*]``) and asserting absence:
    ``expected_count: 0`` passes when the key path selects nothing (or nothing matches
    ``expected_value``), while a missing or invalid file is still an error. A path that
    selects one sequence counts its elements when ``expected_value`` is given; without it
    every selected value counts once.

    Args:
        dst: Guest path to the YAML file; a glob must match exactly one path. Several
            documents form a top-level list; an empty file has no values.
        key_path: Dot path from the root (syntax as in yaml.contains_key).
        expected_count: Non-negative integer to compare with.
        expected_value: Only count values equal to this (normalised as in yaml.value_matches).
            ``None`` (default) counts every value.
        regex_match: Treat a string ``expected_value`` as a regex searched in ``str(value)``.
        comparison_type: ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or
            ``less_equal``. Other values are an error.

    Example:
        function: yaml.value_count
        parameter:
          dst: /home/user/.config/app/config.yaml
          key_path: recent[*]
          expected_count: 3
          comparison_type: greater_equal
    """
    return structured.value_count(
        ctx, dst, key_path, expected_count, YAML, expected_value, regex_match, comparison_type
    )
