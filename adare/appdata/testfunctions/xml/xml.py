# external imports
from lxml import etree as ET
import re
from typing import Optional, Union, Dict

# internal imports
from adarelib.testset.api import testfunction, TestContext
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult

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
    except ET.XMLSyntaxError as e:
        raise ValueError(f"Invalid XML format: {e}")


def _find_elements(root, xpath, namespaces=None):
    """Find elements using XPath with namespace support"""
    try:
        # Use lxml's xpath() method for full XPath support
        if namespaces:
            return root.xpath(xpath, namespaces=namespaces)
        else:
            return root.xpath(xpath)
    except (AttributeError, SyntaxError, ET.XPathEvalError) as e:
        raise ValueError(f"Invalid XPath expression '{xpath}': {e}")


def _compare_values(ctx, actual_text, expected_text, regex_match=False, case_sensitive=True):
    """Compare values using the same logic as JSON testfunctions"""
    expected_str = str(expected_text)

    if not ctx.has_placeholders(expected_str):
        # No placeholders - check for regex_match flag
        if regex_match:
            # Regex matching
            try:
                flags = 0 if case_sensitive else re.IGNORECASE
                pattern = re.compile(expected_text, flags)
                if pattern.search(actual_text):
                    return True, f'text "{actual_text}" matches regex "{expected_text}"'
                else:
                    return False, f'text "{actual_text}" does not match regex "{expected_text}"'
            except re.error as e:
                return False, f'Invalid regex pattern: {expected_text} - {e}'
        else:
            # Direct text comparison
            if case_sensitive:
                success = actual_text == expected_text
            else:
                success = actual_text.lower() == expected_text.lower()

            if success:
                return True, f'text matches expected: {actual_text}'
            else:
                return False, f'expected "{expected_text}", got "{actual_text}"'
    else:
        # Has placeholders - use placeholder system (handles regex and timestamp with tolerance)
        placeholder_names = ctx.get_placeholders(expected_str)
        if len(placeholder_names) == 1:
            placeholder_name = placeholder_names[0]
            try:
                return ctx.compare_with_placeholder(placeholder_name, actual_text)
            except Exception as e:
                return False, f"placeholder comparison error: {e}"
        else:
            return False, f"expected 1 placeholder for single value comparison, got {len(placeholder_names)}"


def _handle_wildcard_matching(ctx, elements, expected_text, wildcard_mode, xpath, regex_match=False, case_sensitive=True):
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
        is_match, message = _compare_values(ctx, element_text, expected_text, regex_match, case_sensitive)
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
            return TestResult.success([
                f'XPath "{xpath}" matched {len(matches)}/{len(elements)} elements (mode: any)',
                f'matching text: {", ".join(match_details)}'
            ])
        else:
            return TestResult.failed([
                f'XPath "{xpath}" matched 0/{len(elements)} elements (mode: any)',
                f'expected: "{expected_text}"',
                f'got texts: {[text for _, text, _ in non_matches[:5]]}'
            ])
    else:  # wildcard_mode == 'all'
        if not non_matches:
            return TestResult.success([
                f'XPath "{xpath}" matched all {len(elements)} elements (mode: all)',
                f'all elements have text: "{expected_text}"'
            ])
        else:
            non_match_details = [f"element[{i}]: '{text}'" for i, text, _ in non_matches[:3]]
            if len(non_matches) > 3:
                non_match_details.append(f"... and {len(non_matches) - 3} more non-matches")
            return TestResult.failed([
                f'XPath "{xpath}" matched {len(matches)}/{len(elements)} elements (mode: all)',
                f'expected: "{expected_text}"',
                f'non-matching texts: {", ".join(non_match_details)}'
            ])


def _compare_count(actual_count, expected_count, comparison_type):
    """Compare counts based on comparison type"""
    if comparison_type == 'equals':
        return actual_count == expected_count, f"count is {actual_count}, expected {expected_count}"
    elif comparison_type == 'greater':
        return actual_count > expected_count, f"count is {actual_count}, expected > {expected_count}"
    elif comparison_type == 'less':
        return actual_count < expected_count, f"count is {actual_count}, expected < {expected_count}"
    elif comparison_type == 'greater_equal':
        return actual_count >= expected_count, f"count is {actual_count}, expected >= {expected_count}"
    elif comparison_type == 'less_equal':
        return actual_count <= expected_count, f"count is {actual_count}, expected <= {expected_count}"
    else:
        raise ValueError(f"Invalid comparison type: {comparison_type}")


def _evaluate_xpath(root, xpath, result_type, namespaces=None):
    """Evaluate XPath and convert result based on type"""
    try:
        # Use lxml's xpath() method for full XPath support
        if result_type == 'text':
            elements = root.xpath(xpath, namespaces=namespaces or {})
            if elements:
                return elements[0].text or ""
            else:
                return ""
        elif result_type == 'number':
            elements = root.xpath(xpath, namespaces=namespaces or {})
            if elements:
                text = elements[0].text or "0"
                return float(text)
            else:
                return 0.0
        elif result_type == 'boolean':
            elements = root.xpath(xpath, namespaces=namespaces or {})
            return len(elements) > 0
        else:
            raise ValueError(f"Unsupported result type: {result_type}")

    except (AttributeError, SyntaxError, ValueError, ET.XPathEvalError) as e:
        raise ValueError(f"XPath evaluation error '{xpath}': {e}")


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
            default_ns = root.tag[1:root.tag.find('}')]
            namespaces[''] = default_ns

        # Extract namespace prefixes from attributes
        for attr_name in root.attrib:
            if attr_name.startswith('xmlns:'):
                prefix = attr_name[6:]  # Remove 'xmlns:' prefix
                namespaces[prefix] = root.attrib[attr_name]
            elif attr_name == 'xmlns':
                namespaces[''] = root.attrib[attr_name]

        return root, namespaces
    except ET.XMLSyntaxError as e:
        raise ValueError(f"Invalid XML format: {e}")


# =============================================================================
# Test functions
# =============================================================================

@testfunction(
    name='element_exists',
    description='tests if XML element exists at specified XPath',
    category=HostModeCategory.FILE_CONTENT,
)
def element_exists(ctx: TestContext, dst: str, xpath: str, namespaces: Dict[str, str] = None):
    try:
        dst_resolved, status = ctx.resolve_globfilepath(dst)
        if not dst_resolved:
            return TestResult.failed([f'XML file {dst} not found ({status})'])

        log.debug(f'dst file {dst_resolved} will be used for test element_exists')

        try:
            root = _parse_xml(dst_resolved)
            elements = _find_elements(root, xpath, namespaces)

            if elements:
                return TestResult.success([f'element found at XPath "{xpath}" ({len(elements)} matches)'])
            else:
                return TestResult.failed([f'no element found at XPath "{xpath}"'])

        except ValueError as e:
            return TestResult.execution_error(e, f"XML processing error")
        except FileNotFoundError:
            return TestResult.failed([f'XML file {dst_resolved} does not exist'])
        except (PermissionError, OSError) as e:
            return TestResult.execution_error(e, f"Cannot read XML file {dst_resolved}")

    except Exception as e:
        log.error(f"Unexpected error in XML element exists test: {e}", exc_info=True)
        return TestResult.execution_error(e, "Unexpected error in XML element exists test")


@testfunction(
    name='element_text_matches',
    description='tests if XML element text content matches expected value with placeholder support for regex and timestamp tolerance',
    category=HostModeCategory.FILE_CONTENT,
)
def element_text_matches(ctx: TestContext, dst: str, xpath: str, expected_text: str = '', regex_match: bool = False, case_sensitive: bool = True, wildcard_mode: str = "any", namespaces: Dict[str, str] = None):
    try:
        dst_resolved, status = ctx.resolve_globfilepath(dst)
        if not dst_resolved:
            return TestResult.failed([f'XML file {dst} not found ({status})'])

        log.debug(f'dst file {dst_resolved} will be used for test element_text_matches')

        try:
            root = _parse_xml(dst_resolved)
            elements = _find_elements(root, xpath, namespaces)

            if not elements:
                return TestResult.failed([f'no elements found at XPath "{xpath}"'])

            # Handle multiple elements based on wildcard mode
            if len(elements) > 1:
                return _handle_wildcard_matching(ctx, elements, expected_text, wildcard_mode, xpath, regex_match, case_sensitive)
            else:
                # Single element matching
                element_text = elements[0].text or ""
                is_match, message = _compare_values(ctx, element_text, expected_text, regex_match, case_sensitive)
                if is_match:
                    return TestResult.success([message])
                else:
                    return TestResult.failed([message])

        except ValueError as e:
            return TestResult.execution_error(e, f"XML processing error")
        except FileNotFoundError:
            return TestResult.failed([f'XML file {dst_resolved} does not exist'])
        except (PermissionError, OSError) as e:
            return TestResult.execution_error(e, f"Cannot read XML file {dst_resolved}")

    except Exception as e:
        log.error(f"Unexpected error in XML element text matches test: {e}", exc_info=True)
        return TestResult.execution_error(e, "Unexpected error in XML element text matches test")


@testfunction(
    name='attribute_matches',
    description='tests if XML element attribute matches expected value with regex and timestamp tolerance support',
    category=HostModeCategory.FILE_CONTENT,
)
def attribute_matches(ctx: TestContext, dst: str, xpath: str, attribute: str, expected_value: str, regex_match: bool = False, case_sensitive: bool = True, namespaces: Dict[str, str] = None):
    try:
        dst_resolved, status = ctx.resolve_globfilepath(dst)
        if not dst_resolved:
            return TestResult.failed([f'XML file {dst} not found ({status})'])

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

            # _compare_values uses "text" wording; for attributes we use the same logic
            # but need to adjust messages for attribute context
            expected_str = str(expected_value)

            if not ctx.has_placeholders(expected_str):
                # No placeholders - check for regex_match flag
                if regex_match:
                    # Regex matching
                    try:
                        flags = 0 if case_sensitive else re.IGNORECASE
                        pattern = re.compile(expected_value, flags)
                        if pattern.search(actual_value):
                            is_match, message = True, f'attribute value "{actual_value}" matches regex "{expected_value}"'
                        else:
                            is_match, message = False, f'attribute value "{actual_value}" does not match regex "{expected_value}"'
                    except re.error as e:
                        is_match, message = False, f'Invalid regex pattern: {expected_value} - {e}'
                else:
                    # Direct value comparison
                    if case_sensitive:
                        success = actual_value == expected_value
                    else:
                        success = actual_value.lower() == expected_value.lower()

                    if success:
                        is_match, message = True, f'attribute value matches expected: {actual_value}'
                    else:
                        is_match, message = False, f'expected "{expected_value}", got "{actual_value}"'
            else:
                # Has placeholders - use placeholder system
                placeholder_names = ctx.get_placeholders(expected_str)
                if len(placeholder_names) == 1:
                    placeholder_name = placeholder_names[0]
                    try:
                        is_match, message = ctx.compare_with_placeholder(placeholder_name, actual_value)
                    except Exception as e:
                        is_match, message = False, f"placeholder comparison error: {e}"
                else:
                    is_match, message = False, f"expected 1 placeholder for single value comparison, got {len(placeholder_names)}"

            if is_match:
                return TestResult.success([message])
            else:
                return TestResult.failed([message])

        except ValueError as e:
            return TestResult.execution_error(e, f"XML processing error")
        except FileNotFoundError:
            return TestResult.failed([f'XML file {dst_resolved} does not exist'])
        except (PermissionError, OSError) as e:
            return TestResult.execution_error(e, f"Cannot read XML file {dst_resolved}")

    except Exception as e:
        return TestResult.execution_error(e, "Unexpected error in XML attribute matches test")


@testfunction(
    name='element_count',
    description='tests the number of XML elements matching XPath expression',
    category=HostModeCategory.FILE_CONTENT,
)
def element_count(ctx: TestContext, dst: str, xpath: str, expected_count: int = 0, comparison_type: str = 'equals', namespaces: Dict[str, str] = None):
    try:
        dst_resolved, status = ctx.resolve_globfilepath(dst)
        if not dst_resolved:
            return TestResult.failed([f'XML file {dst} not found ({status})'])

        log.debug(f'dst file {dst_resolved} will be used for test element_count')

        try:
            root = _parse_xml(dst_resolved)
            elements = _find_elements(root, xpath, namespaces)
            actual_count = len(elements)

            success, message = _compare_count(actual_count, expected_count, comparison_type)

            if success:
                return TestResult.success([f'element count matches: {message}'])
            else:
                return TestResult.failed([f'element count mismatch: {message}'])

        except ValueError as e:
            return TestResult.execution_error(e, f"XML processing error")
        except FileNotFoundError:
            return TestResult.failed([f'XML file {dst_resolved} does not exist'])
        except (PermissionError, OSError) as e:
            return TestResult.execution_error(e, f"Cannot read XML file {dst_resolved}")

    except Exception as e:
        return TestResult.execution_error(e, "Unexpected error in XML element count test")


@testfunction(
    name='xpath_result_matches',
    description='tests if XPath expression result matches expected value (text, number, or boolean)',
    category=HostModeCategory.FILE_CONTENT,
)
def xpath_result_matches(ctx: TestContext, dst: str, xpath: str, expected_result: Union[str, int, float, bool] = '', result_type: str = 'text', namespaces: Dict[str, str] = None):
    try:
        dst_resolved, status = ctx.resolve_globfilepath(dst)
        if not dst_resolved:
            return TestResult.failed([f'XML file {dst} not found ({status})'])

        log.debug(f'dst file {dst_resolved} will be used for test xpath_result_matches')

        try:
            root = _parse_xml(dst_resolved)
            actual_result = _evaluate_xpath(root, xpath, result_type, namespaces)

            # Type conversion for comparison
            if result_type == 'number':
                expected_result = float(expected_result)
            elif result_type == 'boolean':
                expected_result = bool(expected_result)
            else:
                expected_result = str(expected_result)

            if actual_result == expected_result:
                return TestResult.success([f'XPath result matches: {actual_result}'])
            else:
                return TestResult.failed([f'XPath result mismatch. Expected: {expected_result}, Got: {actual_result}'])

        except ValueError as e:
            return TestResult.execution_error(e, f"XML/XPath processing error")
        except FileNotFoundError:
            return TestResult.failed([f'XML file {dst_resolved} does not exist'])
        except (PermissionError, OSError) as e:
            return TestResult.execution_error(e, f"Cannot read XML file {dst_resolved}")

    except Exception as e:
        return TestResult.execution_error(e, "Unexpected error in XPath result matches test")


@testfunction(
    name='namespace_matches',
    description='tests if XML namespace declarations match expected namespaces',
    category=HostModeCategory.FILE_CONTENT,
)
def namespace_matches(ctx: TestContext, dst: str, expected_namespaces: Dict[str, str] = None, check_mode: str = 'contains'):
    try:
        dst_resolved, status = ctx.resolve_globfilepath(dst)
        if not dst_resolved:
            return TestResult.failed([f'XML file {dst} not found ({status})'])

        log.debug(f'dst file {dst_resolved} will be used for test namespace_matches')

        try:
            root, actual_namespaces = _parse_xml_with_namespaces(dst_resolved)

            if check_mode == 'exact':
                if actual_namespaces == expected_namespaces:
                    return TestResult.success([f'namespaces match exactly: {actual_namespaces}'])
                else:
                    missing = set(expected_namespaces.items()) - set(actual_namespaces.items())
                    extra = set(actual_namespaces.items()) - set(expected_namespaces.items())
                    details = []
                    if missing:
                        details.append(f'missing: {dict(missing)}')
                    if extra:
                        details.append(f'extra: {dict(extra)}')
                    return TestResult.failed([f'namespace mismatch: {", ".join(details)}'])

            elif check_mode == 'contains':
                missing = []
                for prefix, uri in expected_namespaces.items():
                    if prefix not in actual_namespaces:
                        missing.append(f'{prefix}')
                    elif actual_namespaces[prefix] != uri:
                        missing.append(f'{prefix} (URI mismatch: expected {uri}, got {actual_namespaces[prefix]})')

                if not missing:
                    return TestResult.success([f'all expected namespaces found: {expected_namespaces}'])
                else:
                    return TestResult.failed([f'missing/incorrect namespaces: {missing}'])

            else:
                return TestResult.execution_error(None, f"Invalid check_mode: {check_mode}")

        except ValueError as e:
            return TestResult.execution_error(e, f"XML processing error")
        except FileNotFoundError:
            return TestResult.failed([f'XML file {dst_resolved} does not exist'])
        except (PermissionError, OSError) as e:
            return TestResult.execution_error(e, f"Cannot read XML file {dst_resolved}")

    except Exception as e:
        return TestResult.execution_error(e, "Unexpected error in XML namespace matches test")
