# external imports
# The stdlib parser, deliberately and exclusively -- this module used to import lxml.
#
# ONE parser on every guest, by design. These testfunctions produce forensic evidence
# that is compared ACROSS OS versions (the paper's section 5.2 asserts that Ubuntu
# 20.04 writes `visited` as integer -1 while 22.04/24.04 write a subsecond timestamp).
# If the parser varied by guest, a cross-version difference could be an artifact of
# the measuring instrument instead of the platform, and the comparison would no longer
# be sound. Falling back to ElementTree only where lxml is missing would have created
# exactly that split: lxml on 22.04/24.04, ElementTree on 20.04 -- i.e. the parser
# differing along the very axis under study. So the instrument is held constant and
# lxml is not used at all.
#
# lxml was not removed for taste. It cannot be installed uniformly: on Ubuntu 20.04
# (focal, Python 3.8, aarch64) the pinned version has no wheel, so pip attempts a
# source build needing libxml2-dev/libxslt1-dev, absent from a minimal server guest.
# That single ModuleNotFoundError at import time made the ENTIRE xml collection
# unavailable, so every xml.* assertion on 20.04 failed as an execution error while
# 22.04 and 24.04 passed -- run 01KYMYDVD7VDS5TNJZPSNWKVDB died that way.
#
# The cost is XPath expressiveness: ElementPath is a documented subset (child and
# descendant steps, prefixed names, [@attr='value'] and [tag='value'] predicates).
# Every XPath in every shipped playbook, example and unit test was inventoried and
# all of them fall inside it -- no functions, axes, unions or positional predicates
# anywhere. An expression outside the subset raises rather than mis-evaluating; see
# _xpath().
import xml.etree.ElementTree as ET

import re
from typing import Optional

# internal imports
from adarelib.testset.api import testfunction, TestContext
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult
from adarelib.testset.compare import compare_with_single_placeholder, regex_expected_problem
from adarelib.testset.structured import StructuredFormat, compare_count, count_parameter_errors
from adarelib.testset.ordering import OrderingError
from adarelib.testset.valuecompare import ordered_setup, structured_values_compare
from adarelib.testset.valuedecode import DecodedKeyPathMissing, ValueDecodeError, decoder_setup

# configure logging
import logging

log = logging.getLogger(__name__)


# =============================================================================
# Module-level helper functions (deduplicated)
# =============================================================================


def _parse_xml(filepath):
    """Parse XML file and return root element"""
    try:
        tree = ET.parse(filepath)
        return tree.getroot()
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML format: {e}") from e


# Constructs ElementPath does not implement. Listed so an expression using one is
# REFUSED outright instead of being evaluated to the wrong answer -- see _xpath().
_UNSUPPORTED_XPATH_TOKENS = ('(', '::', '..', '|')


def _xpath(root, xpath, namespaces=None):
    """Select the elements matching *xpath*, relative to *root*.

    ElementPath needs an explicit relative start, so two absolute forms are
    translated (both appear in shipped tests, and both raise if passed through):

    * ``//tag`` -> ``.//tag`` — search all descendants of *root*.
    * ``/tag``  -> matched against *root* itself, since ElementPath cannot express
      "the document element" and ``findall('/tag')`` simply raises. ``/a/b`` becomes
      ``./b`` evaluated on *root* when *root* is ``a``, and matches nothing when it
      is not, which is what an absolute path means.

    Everything else is passed through unchanged: child and descendant steps, prefixed
    names resolved via *namespaces*, and ``[@attr='value']`` / ``[tag='value']``
    predicates (either quote style).

    Raises:
        ValueError: If *xpath* uses a construct ElementPath does not implement.
            Raising is the point. ``findall()`` handed an unsupported construct
            generally returns ``[]``, which every caller here reads as "no elements
            matched" — so an assertion would FAIL with a plausible message about the
            artifact under test while the real cause was the expression. In a
            forensic result a loud error beats a silently wrong verdict.
    """
    offending = [t for t in _UNSUPPORTED_XPATH_TOKENS if t in xpath]
    if offending:
        raise ValueError(
            f"XPath '{xpath}' uses {', '.join(offending)}, which ElementPath (the "
            f'stdlib XPath subset ADARE uses for every guest) does not implement. '
            f"Restate it using child/descendant steps and [@attr='value'] or "
            f"[tag='value'] predicates."
        )

    if xpath.startswith('//'):
        return root.findall(f'.{xpath}', namespaces or {})
    if xpath.startswith('/'):
        # Absolute: the first step must BE the root element.
        steps = xpath[1:].split('/', 1)
        first, rest = steps[0], (steps[1] if len(steps) > 1 else '')
        root_tag = root.tag
        if namespaces and ':' in first:
            prefix, local = first.split(':', 1)
            if prefix in namespaces:
                first = f'{{{namespaces[prefix]}}}{local}'
        if root_tag != first:
            return []
        return root.findall(f'./{rest}', namespaces or {}) if rest else [root]
    return root.findall(xpath, namespaces or {})


def _find_elements(root, xpath, namespaces=None):
    """Find elements using XPath with namespace support"""
    try:
        return _xpath(root, xpath, namespaces)
    except (AttributeError, SyntaxError, KeyError) as e:
        raise ValueError(f"Invalid XPath expression '{xpath}': {e}") from e


def _compare_values(
    ctx, actual_text, expected_text, regex_match=False, case_sensitive=True, ordered=None, what='text', decoder=None
):
    """Compare values using the same logic as JSON testfunctions (``ordered``: ordered mode)"""
    if decoder is not None:
        try:
            actual_text = decoder(actual_text, as_text=True)
        except DecodedKeyPathMissing as e:  # decoded fine, the key is not in it: no match
            return False, str(e)
    if ordered is not None:
        return ordered.compare(actual_text, expected_text)
    expected_str = str(expected_text)

    if not ctx.has_placeholders(expected_str):
        # No placeholders - check for regex_match flag
        if regex_match:
            # Regex matching
            try:
                flags = 0 if case_sensitive else re.IGNORECASE
                pattern = re.compile(expected_text, flags)
                if pattern.search(actual_text):
                    return True, f'{what} "{actual_text}" matches regex "{expected_text}"'
                return False, f'{what} "{actual_text}" does not match regex "{expected_text}"'
            except re.error as e:
                raise re.error(f'invalid regex pattern {expected_text!r}: {e}') from e
        else:
            # Direct text comparison
            success = actual_text == expected_text if case_sensitive else actual_text.lower() == expected_text.lower()

            if success:
                return True, f'{what} matches expected: {actual_text}'
            return False, f'expected "{expected_text}", got "{actual_text}"'
    else:
        # Has placeholders - use placeholder system (handles regex and timestamp with tolerance)
        return compare_with_single_placeholder(ctx, expected_str, actual_text)


def _handle_wildcard_matching(
    ctx,
    elements,
    expected_text,
    wildcard_mode,
    xpath,
    regex_match=False,
    case_sensitive=True,
    ordered=None,
    decoder=None,
):
    """Handle matching logic for multiple elements with 'any' or 'all' modes"""
    if not elements:
        return TestResult.failed([f'no elements found at XPath "{xpath}"'])

    # Validate wildcard_mode
    if wildcard_mode not in ['any', 'all']:
        return TestResult.execution_error(None, f"Invalid wildcard_mode: {wildcard_mode}. Must be 'any' or 'all'")

    matches = []
    non_matches = []

    # Check each element's text against expected using unified comparison method
    for i, element in enumerate(elements):
        element_text = element.text or ""
        is_match, message = _compare_values(
            ctx, element_text, expected_text, regex_match, case_sensitive, ordered, decoder=decoder
        )
        if is_match:
            matches.append((i, element_text, message))
        else:
            non_matches.append((i, element_text, message))

    # Apply wildcard mode logic
    if wildcard_mode == 'any':
        if matches:
            match_details = [f"element[{i}]: '{text}'" for i, text, _ in matches[:3]]
            if len(matches) > 3:
                match_details.append(f"... and {len(matches) - 3} more matches")
            return TestResult.success(
                [
                    f'XPath "{xpath}" matched {len(matches)}/{len(elements)} elements (mode: any)',
                    f'matching text: {", ".join(match_details)}',
                ]
            )
        return TestResult.failed(
            [
                f'XPath "{xpath}" matched 0/{len(elements)} elements (mode: any)',
                f'expected: "{expected_text}"',
                f'got texts: {[text for _, text, _ in non_matches[:5]]}',
            ]
        )
    # wildcard_mode == 'all'
    if not non_matches:
        return TestResult.success(
            [
                f'XPath "{xpath}" matched all {len(elements)} elements (mode: all)',
                f'all elements have text: "{expected_text}"',
            ]
        )
    non_match_details = [f"element[{i}]: '{text}'" for i, text, _ in non_matches[:3]]
    if len(non_matches) > 3:
        non_match_details.append(f"... and {len(non_matches) - 3} more non-matches")
    return TestResult.failed(
        [
            f'XPath "{xpath}" matched {len(matches)}/{len(elements)} elements (mode: all)',
            f'expected: "{expected_text}"',
            f'non-matching texts: {", ".join(non_match_details)}',
        ]
    )


def _evaluate_xpath(root, xpath, result_type, namespaces=None):
    """Evaluate XPath and convert result based on type"""
    try:
        if result_type == 'text':
            elements = _xpath(root, xpath, namespaces)
            if elements:
                return elements[0].text or ""
            return ""
        if result_type == 'number':
            elements = _xpath(root, xpath, namespaces)
            if elements:
                text = elements[0].text or "0"
                return float(text)
            return 0.0
        if result_type == 'boolean':
            elements = _xpath(root, xpath, namespaces)
            return len(elements) > 0
        raise ValueError(f"Unsupported result type: {result_type}")

    except (AttributeError, SyntaxError, KeyError, ValueError) as e:
        raise ValueError(f"XPath evaluation error '{xpath}': {e}") from e


def _parse_xml_with_namespaces(filepath):
    """Parse XML and extract namespace information"""
    try:
        # Parse the file and get namespace info
        tree = ET.parse(filepath)
        root = tree.getroot()

        # Extract namespaces from the root element
        # Note: ElementTree doesn't have great namespace introspection
        # This is a basic implementation
        namespaces = {}

        # Check for default namespace
        if root.tag.startswith('{'):
            default_ns = root.tag[1 : root.tag.find('}')]
            namespaces[''] = default_ns

        # Extract namespace prefixes from attributes
        for attr_name in root.attrib:
            if attr_name.startswith('xmlns:'):
                prefix = attr_name[6:]  # Remove 'xmlns:' prefix
                namespaces[prefix] = root.attrib[attr_name]
            elif attr_name == 'xmlns':
                namespaces[''] = root.attrib[attr_name]

        return root, namespaces
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML format: {e}") from e


# =============================================================================
# Test functions
# =============================================================================


@testfunction(
    name='element_exists',
    description='tests if XML element exists at specified XPath',
    category=HostModeCategory.FILE_CONTENT,
)
def element_exists(ctx: TestContext, dst: str, xpath: str, namespaces: dict[str, str] = None):
    """Pass when ``xpath`` selects at least one element in XML file ``dst``.

    Use for: checking a config/profile XML gained an entry. For "absent" use xml.element_count
    with ``expected_count: 0``.

    Args:
        dst: Guest path to the XML file; a glob must match exactly one path. A missing file
            or malformed XML is an execution error.
        xpath: ElementTree ``ElementPath`` subset, evaluated on the root element:
            ``//tag`` (any depth), ``/root/child`` (first step must be the root tag),
            ``child/grandchild``, predicates ``[@attr='v']``, ``[tag='v']``, ``[@attr]``.
            Any ``(``, ``::``, ``..`` or ``|`` (even inside a quoted value) is an execution
            error, so no functions such as ``text()``.
        namespaces: Prefix -> URI map for prefixed names in ``xpath`` (``{ns: 'http://...'}`` +
            ``//ns:item``); ``{uri}tag`` also works without it.

    Example:
        function: xml.element_exists
        parameter:
          dst: /home/user/data/list.xml
          xpath: "//entry[@ref='item-42']"
    """
    dst_resolved, status = ctx.resolve_globfilepath(dst)
    if not dst_resolved:
        return TestResult.error([f'XML file {dst} not found ({status})'])

    log.debug(f'dst file {dst_resolved} will be used for test element_exists')

    try:
        root = _parse_xml(dst_resolved)
        elements = _find_elements(root, xpath, namespaces)

        if elements:
            return TestResult.success([f'element found at XPath "{xpath}" ({len(elements)} matches)'])
        return TestResult.failed([f'no element found at XPath "{xpath}"'])

    except ValueError as e:
        return TestResult.execution_error(e, "XML processing error")
    except FileNotFoundError:
        return TestResult.error([f'XML file {dst_resolved} does not exist'])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot read XML file {dst_resolved}")


@testfunction(
    name='element_text_matches',
    description='tests if XML element text content matches expected value with placeholder support for regex and timestamp tolerance',
    category=HostModeCategory.FILE_CONTENT,
)
def element_text_matches(
    ctx: TestContext,
    dst: str,
    xpath: str,
    expected_value: str,
    regex_match: bool = False,
    case_sensitive: bool = True,
    wildcard_mode: str = "any",
    namespaces: dict[str, str] = None,
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
    """Pass when the text of the element(s) selected by ``xpath`` equals/matches ``expected_value``.

    Use for: asserting an XML setting or record value, and document properties of office
    files: the author of a .docx is ``dc:creator`` in ``report.docx!/docProps/core.xml``
    (xpath ``./dc:creator``, namespaces ``{dc: 'http://purl.org/dc/elements/1.1/'}``).
    "Text" is ``element.text``: only the text before the element's first child, not
    stripped (missing -> ``''``). To count elements use xml.element_count.

    With ``comparison_type`` (``greater``, ``less``, ...), ``tolerance`` or the time
    parameters the text is compared as a number or timestamp (``case_sensitive`` is then
    ignored); to compare two values of one file use xml.values_compare.

    Args:
        dst: Guest path to the XML file; a glob must match exactly one path. A missing file
            or malformed XML is an execution error.
        xpath: ElementTree ``ElementPath`` subset, evaluated on the root element:
            ``//tag`` (any depth), ``/root/child`` (first step must be the root tag),
            ``child/grandchild``, predicates ``[@attr='v']``, ``[tag='v']``, ``[@attr]``.
            Any ``(``, ``::``, ``..`` or ``|`` (even inside a quoted value) is an execution
            error, so no functions such as ``text()``. No match fails.
        expected_value: Required. Exact expected text (``''`` for an empty element), or a regex
            with ``regex_match``. A single ``!re``/``!timestamp`` tag is matched by type
            (``case_sensitive`` then ignored); an invalid regex is an error.
        regex_match: Search ``expected_value`` as a Python regex (``re.search``, unanchored).
        case_sensitive: ``False`` compares lower-cased / uses ``re.IGNORECASE``.
        wildcard_mode: For several matched elements: ``any`` (default) or ``all`` must match;
            other values are an execution error (only checked when several elements match).
        namespaces: Prefix -> URI map for prefixed names in ``xpath`` (``{ns: 'http://...'}`` +
            ``//ns:item``); ``{uri}tag`` also works without it.
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
        function: xml.element_text_matches
        parameter:
          dst: /home/user/.config/app/settings.xml
          xpath: ./general/language
          expected_value: de_DE
    """
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
    dst_resolved, status = ctx.resolve_globfilepath(dst)
    if not dst_resolved:
        return TestResult.error([f'XML file {dst} not found ({status})'])

    log.debug(f'dst file {dst_resolved} will be used for test element_text_matches')

    try:
        root = _parse_xml(dst_resolved)
        elements = _find_elements(root, xpath, namespaces)

        if not elements:
            return TestResult.failed([f'no elements found at XPath "{xpath}"'])

        # Handle multiple elements based on wildcard mode
        if len(elements) > 1:
            return _handle_wildcard_matching(
                ctx, elements, expected_value, wildcard_mode, xpath, regex_match, case_sensitive, ordered, decoder
            )
        # Single element matching
        element_text = elements[0].text or ""
        is_match, message = _compare_values(
            ctx, element_text, expected_value, regex_match, case_sensitive, ordered, decoder=decoder
        )
        if is_match:
            return TestResult.success([message])
        return TestResult.failed([message])

    except (OrderingError, ValueDecodeError) as e:
        return TestResult.error([str(e)])
    except ValueError as e:
        return TestResult.execution_error(e, "XML processing error")
    except FileNotFoundError:
        return TestResult.error([f'XML file {dst_resolved} does not exist'])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot read XML file {dst_resolved}")


@testfunction(
    name='attribute_matches',
    description='tests if XML element attribute matches expected value with regex and timestamp tolerance support',
    category=HostModeCategory.FILE_CONTENT,
)
def attribute_matches(
    ctx: TestContext,
    dst: str,
    xpath: str,
    attribute: str,
    expected_value: str,
    regex_match: bool = False,
    case_sensitive: bool = True,
    namespaces: dict[str, str] = None,
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
    """Pass when ``attribute`` of the FIRST element selected by ``xpath`` equals/matches ``expected_value``.

    Use for: asserting attribute values (an id, a state, a timestamp ...). No matching
    element or a missing attribute fails.

    With ``comparison_type`` (``greater``, ``less``, ...), ``tolerance`` or the time
    parameters the attribute value is compared as a number or timestamp (``case_sensitive`` is then
    ignored); to compare two values of one file use xml.values_compare.

    Args:
        dst: Guest path to the XML file; a glob must match exactly one path. A missing file
            or malformed XML is an execution error.
        xpath: ElementTree ``ElementPath`` subset, evaluated on the root element:
            ``//tag`` (any depth), ``/root/child`` (first step must be the root tag),
            ``child/grandchild``, predicates ``[@attr='v']``, ``[tag='v']``, ``[@attr]``.
            Any ``(``, ``::``, ``..`` or ``|`` (even inside a quoted value) is an execution
            error, so no functions such as ``text()``.
        attribute: Attribute name; namespaced attributes need the ``{uri}name`` form.
        expected_value: Exact expected value, or a regex with ``regex_match``; a single
            ``!re``/``!timestamp`` tag is matched by type.
        regex_match: Search ``expected_value`` as a Python regex (``re.search``, unanchored).
        case_sensitive: ``False`` compares lower-cased / uses ``re.IGNORECASE``.
        namespaces: Prefix -> URI map for prefixed names in ``xpath`` (``{ns: 'http://...'}`` +
            ``//ns:item``); ``{uri}tag`` also works without it.
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
        function: xml.attribute_matches
        parameter:
          dst: /home/user/data/list.xml
          xpath: "//entry[@ref='item-42']"
          attribute: modified
          expected_value: !re '20[0-9]{2}-'
    """
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
    dst_resolved, status = ctx.resolve_globfilepath(dst)
    if not dst_resolved:
        return TestResult.error([f'XML file {dst} not found ({status})'])

    log.debug(f'dst file {dst_resolved} will be used for test attribute_matches')

    try:
        root = _parse_xml(dst_resolved)
        elements = _find_elements(root, xpath, namespaces)

        if not elements:
            return TestResult.failed([f'no elements found at XPath "{xpath}"'])

        # Check first matching element's attribute
        element = elements[0]
        if attribute not in element.attrib:
            return TestResult.failed([f'attribute "{attribute}" not found in element at XPath "{xpath}"'])

        actual_value = element.attrib[attribute]
        is_match, message = _compare_values(
            ctx, actual_value, expected_value, regex_match, case_sensitive, ordered, 'attribute value', decoder
        )
        if is_match:
            return TestResult.success([message])
        return TestResult.failed([message])

    except (OrderingError, ValueDecodeError) as e:
        return TestResult.error([str(e)])
    except ValueError as e:
        return TestResult.execution_error(e, "XML processing error")
    except FileNotFoundError:
        return TestResult.error([f'XML file {dst_resolved} does not exist'])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot read XML file {dst_resolved}")


@testfunction(
    name='element_count',
    description='tests the number of XML elements matching XPath expression',
    category=HostModeCategory.FILE_CONTENT,
)
def element_count(
    ctx: TestContext,
    dst: str,
    xpath: str,
    expected_count: int,
    comparison_type: str = 'equals',
    namespaces: dict[str, str] = None,
):
    """Pass when the number of elements selected by ``xpath`` satisfies ``comparison_type`` vs ``expected_count``.

    Use for: counting entries; ``expected_count: 0`` asserts absence
    (opposite of xml.element_exists).

    Args:
        dst: Guest path to the XML file; a glob must match exactly one path. A missing file
            or malformed XML is an execution error.
        xpath: ElementTree ``ElementPath`` subset, evaluated on the root element:
            ``//tag`` (any depth), ``/root/child`` (first step must be the root tag),
            ``child/grandchild``, predicates ``[@attr='v']``, ``[tag='v']``, ``[@attr]``.
            Any ``(``, ``::``, ``..`` or ``|`` (even inside a quoted value) is an execution
            error, so no functions such as ``text()``.
        expected_count: Required non-negative integer to compare against; anything else is an error.
        comparison_type: ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or
            ``less_equal``; other values are an error.
        namespaces: Prefix -> URI map for prefixed names in ``xpath`` (``{ns: 'http://...'}`` +
            ``//ns:item``); ``{uri}tag`` also works without it.

    Example:
        function: xml.element_count
        parameter:
          dst: /home/user/data/list.xml
          xpath: //entry
          expected_count: 1
          comparison_type: greater_equal
    """
    problems = count_parameter_errors(expected_count, comparison_type)
    if problems:
        return TestResult.error(problems)
    dst_resolved, status = ctx.resolve_globfilepath(dst)
    if not dst_resolved:
        return TestResult.error([f'XML file {dst} not found ({status})'])

    log.debug(f'dst file {dst_resolved} will be used for test element_count')

    try:
        root = _parse_xml(dst_resolved)
        elements = _find_elements(root, xpath, namespaces)
        actual_count = len(elements)

        success, message = compare_count(actual_count, expected_count, comparison_type)

        if success:
            return TestResult.success([f'element count matches: {message}'])
        return TestResult.failed([f'element count mismatch: {message}'])

    except ValueError as e:
        return TestResult.execution_error(e, "XML processing error")
    except FileNotFoundError:
        return TestResult.error([f'XML file {dst_resolved} does not exist'])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot read XML file {dst_resolved}")


@testfunction(
    name='xpath_result_matches',
    description='tests if XPath expression result matches expected value (text, number, or boolean)',
    category=HostModeCategory.FILE_CONTENT,
)
def xpath_result_matches(
    ctx: TestContext,
    dst: str,
    xpath: str,
    expected_value: str | int | float | bool,
    result_type: str = 'text',
    namespaces: dict[str, str] = None,
):
    """Pass when ``xpath`` evaluated as ``result_type`` equals ``expected_value``.

    Use for: typed checks on the first matched element. Prefer xml.element_text_matches for text.

    Args:
        dst: Guest path to the XML file; a glob must match exactly one path. A missing file
            or malformed XML is an execution error.
        xpath: ElementTree ``ElementPath`` subset, evaluated on the root element:
            ``//tag`` (any depth), ``/root/child`` (first step must be the root tag),
            ``child/grandchild``, predicates ``[@attr='v']``, ``[tag='v']``, ``[@attr]``.
            Any ``(``, ``::``, ``..`` or ``|`` (even inside a quoted value) is an execution
            error, so no functions such as ``text()``.
        expected_value: Required. Converted per ``result_type``: ``str()``, ``float()`` or ``bool()``.
            Note ``bool('false')`` is True -- use unquoted YAML ``true``/``false``.
        result_type: ``text`` (default; first element's ``.text``, ``''`` if none), ``number``
            (``float`` of that text; no match -> 0.0, non-numeric -> execution error) or
            ``boolean`` (whether anything matched). Other values are an execution error.
        namespaces: Prefix -> URI map for prefixed names in ``xpath`` (``{ns: 'http://...'}`` +
            ``//ns:item``); ``{uri}tag`` also works without it.

    Example:
        function: xml.xpath_result_matches
        parameter:
          dst: /home/user/.config/app/stats.xml
          xpath: ./counters/opened
          expected_value: 3
          result_type: number
    """
    dst_resolved, status = ctx.resolve_globfilepath(dst)
    if not dst_resolved:
        return TestResult.error([f'XML file {dst} not found ({status})'])

    log.debug(f'dst file {dst_resolved} will be used for test xpath_result_matches')

    try:
        root = _parse_xml(dst_resolved)
        actual_result = _evaluate_xpath(root, xpath, result_type, namespaces)

        # Type conversion for comparison
        if result_type == 'number':
            expected = float(expected_value)
        elif result_type == 'boolean':
            expected = bool(expected_value)
        else:
            expected = str(expected_value)

        if actual_result == expected:
            return TestResult.success([f'XPath result matches: {actual_result}'])
        return TestResult.failed([f'XPath result mismatch. Expected: {expected}, Got: {actual_result}'])

    except ValueError as e:
        return TestResult.execution_error(e, "XML/XPath processing error")
    except FileNotFoundError:
        return TestResult.error([f'XML file {dst_resolved} does not exist'])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot read XML file {dst_resolved}")


@testfunction(
    name='namespace_matches',
    description='tests if XML namespace declarations match expected namespaces',
    category=HostModeCategory.FILE_CONTENT,
)
def namespace_matches(
    ctx: TestContext, dst: str, expected_namespaces: dict[str, str] = None, check_mode: str = 'contains'
):
    """Pass when the namespaces detected in ``dst`` contain (or equal) ``expected_namespaces``.

    Use for: checking which XML dialect/schema version a file uses. Only the root element's
    own namespace is detected, under prefix ``''``: ElementTree drops ``xmlns:*`` attributes,
    so other declared prefixes are never seen and expecting them fails.

    Args:
        dst: Guest path to the XML file; a glob must match exactly one path. A missing file
            or malformed XML is an execution error.
        expected_namespaces: Required map prefix -> URI, e.g. ``{'': 'http://www.w3.org/2000/svg'}``;
            ``None`` is an execution error.
        check_mode: ``contains`` (default; every expected prefix present with that URI) or
            ``exact`` (dicts equal). Other values are an execution error.

    Example:
        function: xml.namespace_matches
        parameter:
          dst: /home/user/Pictures/logo.svg
          expected_namespaces: {'': 'http://www.w3.org/2000/svg'}
    """
    dst_resolved, status = ctx.resolve_globfilepath(dst)
    if not dst_resolved:
        return TestResult.error([f'XML file {dst} not found ({status})'])

    log.debug(f'dst file {dst_resolved} will be used for test namespace_matches')

    try:
        root, actual_namespaces = _parse_xml_with_namespaces(dst_resolved)

        if check_mode == 'exact':
            if actual_namespaces == expected_namespaces:
                return TestResult.success([f'namespaces match exactly: {actual_namespaces}'])
            missing = set(expected_namespaces.items()) - set(actual_namespaces.items())
            extra = set(actual_namespaces.items()) - set(expected_namespaces.items())
            details = []
            if missing:
                details.append(f'missing: {dict(missing)}')
            if extra:
                details.append(f'extra: {dict(extra)}')
            return TestResult.failed([f'namespace mismatch: {", ".join(details)}'])

        if check_mode == 'contains':
            missing = []
            for prefix, uri in expected_namespaces.items():
                if prefix not in actual_namespaces:
                    missing.append(f'{prefix}')
                elif actual_namespaces[prefix] != uri:
                    missing.append(f'{prefix} (URI mismatch: expected {uri}, got {actual_namespaces[prefix]})')

            if not missing:
                return TestResult.success([f'all expected namespaces found: {expected_namespaces}'])
            return TestResult.failed([f'missing/incorrect namespaces: {missing}'])

        return TestResult.execution_error(None, f"Invalid check_mode: {check_mode}")

    except ValueError as e:
        return TestResult.execution_error(e, "XML processing error")
    except FileNotFoundError:
        return TestResult.error([f'XML file {dst_resolved} does not exist'])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot read XML file {dst_resolved}")


_XML_FORMAT = StructuredFormat(label='XML', load=_parse_xml, errors=(ValueError,))


def _side_values(root, xpath, attribute, namespaces):
    """``(label, values)`` of one side: the text or ``attribute`` of every element ``xpath`` selects."""
    elements = _find_elements(root, xpath, namespaces)
    if attribute is None:
        return f'text of XPath "{xpath}"', [element.text or "" for element in elements]
    label = f'attribute "{attribute}" of XPath "{xpath}"'
    return label, [element.attrib[attribute] for element in elements if attribute in element.attrib]


@testfunction(
    name='values_compare',
    description='compares two values (element text or attribute) of one XML file (or of two files) as numbers or timestamps (earlier/later, within a tolerance, A = B + offset)',
    category=HostModeCategory.FILE_CONTENT,
)
def values_compare(
    ctx: TestContext,
    dst: str,
    xpath: str,
    other_xpath: str,
    attribute: str | None = None,
    other_attribute: str | None = None,
    comparison_type: str = 'equals',
    value_type: str = 'auto',
    tolerance: int | float | None = None,
    offset: int | float | None = None,
    time_format: str | None = None,
    timestamp_epoch: int | None = None,
    timestamp_unit: str | None = None,
    utc_offset: str | None = None,
    namespaces: dict[str, str] = None,
    other_dst: str | None = None,
    value_decode: list[str] | str | None = None,
    decoded_key_path: str | None = None,
):
    """Pass when the value selected by ``xpath`` compares to the one selected by ``other_xpath`` (+ ``offset``).

    Use for: relations inside one XML file (or between two, ``other_dst``): a last-saved
    value later than the first-opened one (two attributes, or two elements), two timestamps
    within a few seconds of each other,
    a counter one above another (``comparison_type: equals`` with ``offset: 1``). To compare
    one value with a constant use xml.element_text_matches or xml.attribute_matches with
    ``comparison_type``.

    Args:
        dst: Guest path to the XML file; a glob must match exactly one path. A missing file
            or malformed XML is an error.
        xpath: Selects the element of the first value (ElementTree ``ElementPath`` subset as in xml.element_text_matches).
            It must select exactly one element (with ``attribute``: one element that has the
            attribute): nothing fails, several are an error.
        other_xpath: Selects the element of the second value; same rules (may equal ``xpath``
            to compare two attributes of one element).
        attribute: Take the first value from this attribute (``{uri}name`` for namespaced
            attributes); ``None`` (default) takes the element text (``element.text``, before
            the first child, not stripped).
        other_attribute: The same for the second value.
        comparison_type: How the first value relates to the second: ``equals`` (default),
            ``not_equals``, ``greater``, ``less``, ``greater_equal`` or ``less_equal``
            (``less`` = earlier for timestamps). Other values are an error.
        value_type: ``auto`` (default; numbers if both are numbers, else timestamps),
            ``number`` or ``timestamp``. A value that is no number or timestamp is an error.
        tolerance: Allowed difference for ``equals``/``not_equals`` (seconds for timestamps).
        offset: Added to the second value before comparing (seconds for timestamps, may be
            negative; ``'{{ name }}'`` = a saved number): ``first <comparison_type> second + offset``.
        time_format: ``strptime`` format of text timestamps on both sides; default ISO 8601 or RFC 2822.
        timestamp_epoch: Read numbers as a count since 1 January of ``1970``, ``1601`` or ``2001``.
        timestamp_unit: Unit of that count: ``s`` (default), ``ms``, ``us``, ``ns`` or ``100ns``.
        utc_offset: Zone of timestamps without one (``+02:00``); default UTC.
        namespaces: Prefix -> URI map for prefixed names in both XPaths (``{ns: 'http://...'}`` +
            ``//ns:item``); ``{uri}tag`` also works without it.
        other_dst: Guest path of a second XML file to read ``other_xpath`` from (same rules as
            ``dst``, ``archive!/member`` included); default ``None``: ``dst``. A missing file is
            an error. Compares a file with a copy saved before an action.
        value_decode: Decode both values before comparing (steps as in xml.element_text_matches).
        decoded_key_path: With ``json`` in ``value_decode``: key path into the decoded value; it must select one
            value: none fails, several are an error.

    Example:
        function: xml.values_compare
        parameter:
          dst: /home/user/data/list.xml
          xpath: "//entry[@ref='item-42']"
          attribute: modified
          other_xpath: "//entry[@ref='item-42']"
          other_attribute: created
          comparison_type: greater_equal
    """

    def side(root, path, first):
        return _side_values(root, path, attribute if first else other_attribute, namespaces)

    return structured_values_compare(
        ctx,
        dst,
        xpath,
        other_xpath,
        _XML_FORMAT,
        comparison_type,
        value_type,
        tolerance,
        offset,
        time_format,
        timestamp_epoch,
        timestamp_unit,
        utc_offset,
        other_dst,
        value_decode,
        decoded_key_path,
        side,
    )


# host mode pulls other_dst like dst
values_compare._test_class.host_mode_path_params = ('other_dst',)
