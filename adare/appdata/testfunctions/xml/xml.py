# external imports
import attrs
from pathlib import Path
import xml.etree.ElementTree as ET
import re
from typing import ClassVar, Optional, Union, Dict, Any, List

# internal imports
from adarelib.testset.basictest import BasicTest, Parameter
from adarelib.event.event import TestResult
from adarelib.constants import StatusEnum

# configure logging
import logging
log = logging.getLogger(__name__)


@attrs.define
class ElementExistsParameter(Parameter):
    dst: str
    xpath: str
    namespaces: Optional[Dict[str, str]] = None


@attrs.define
class ElementExists(BasicTest):
    testname: ClassVar[str] = 'element_exists'
    testdescription: ClassVar[str] = 'tests if XML element exists at specified XPath'

    name: str
    parameter: ElementExistsParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def _parse_xml(self, filepath):
        """Parse XML file and return root element"""
        try:
            tree = ET.parse(filepath)
            return tree.getroot()
        except ET.ParseError as e:
            raise ValueError(f"Invalid XML format: {e}")

    def _find_elements(self, root, xpath, namespaces=None):
        """Find elements using XPath with namespace support"""
        try:
            if namespaces:
                return root.findall(xpath, namespaces)
            else:
                return root.findall(xpath)
        except (AttributeError, SyntaxError) as e:
            raise ValueError(f"Invalid XPath expression '{xpath}': {e}")

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.failed([f'XML file {self.parameter.dst} not found ({status})'])

            log.debug(f'dst file {dst} will be used for test {self.name}')

            xpath = self.parameter.xpath
            namespaces = self.parameter.namespaces

            try:
                root = self._parse_xml(dst)
                elements = self._find_elements(root, xpath, namespaces)

                if elements:
                    return TestResult.success([f'element found at XPath "{xpath}" ({len(elements)} matches)'])
                else:
                    return TestResult.failed([f'no element found at XPath "{xpath}"'])

            except ValueError as e:
                return TestResult.execution_error(e, f"XML processing error")
            except FileNotFoundError:
                return TestResult.failed([f'XML file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read XML file {dst}")

        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in XML element exists test")


@attrs.define
class ElementTextMatchesParameter(Parameter):
    dst: str
    xpath: str
    expected_text: str
    regex_match: Optional[bool] = False
    case_sensitive: Optional[bool] = True
    wildcard_mode: Optional[str] = "any"  # "any" or "all" for multiple elements
    namespaces: Optional[Dict[str, str]] = None


@attrs.define
class ElementTextMatches(BasicTest):
    testname: ClassVar[str] = 'element_text_matches'
    testdescription: ClassVar[str] = 'tests if XML element text content matches expected value with placeholder support for regex and timestamp tolerance'

    name: str
    parameter: ElementTextMatchesParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def _parse_xml(self, filepath):
        """Parse XML file and return root element"""
        try:
            tree = ET.parse(filepath)
            return tree.getroot()
        except ET.ParseError as e:
            raise ValueError(f"Invalid XML format: {e}")

    def _find_elements(self, root, xpath, namespaces=None):
        """Find elements using XPath with namespace support"""
        try:
            if namespaces:
                return root.findall(xpath, namespaces)
            else:
                return root.findall(xpath)
        except (AttributeError, SyntaxError) as e:
            raise ValueError(f"Invalid XPath expression '{xpath}': {e}")

    def _compare_values(self, actual_text, expected_text):
        """Compare values using the same logic as JSON testfunctions"""
        expected_str = str(expected_text)

        if not self.has_placeholders(expected_str):
            # No placeholders - check for regex_match flag
            if self.parameter.regex_match:
                # Regex matching
                try:
                    flags = 0 if self.parameter.case_sensitive else re.IGNORECASE
                    pattern = re.compile(expected_text, flags)
                    if pattern.search(actual_text):
                        return True, f'text "{actual_text}" matches regex "{expected_text}"'
                    else:
                        return False, f'text "{actual_text}" does not match regex "{expected_text}"'
                except re.error as e:
                    return False, f'Invalid regex pattern: {expected_text} - {e}'
            else:
                # Direct text comparison
                if self.parameter.case_sensitive:
                    success = actual_text == expected_text
                else:
                    success = actual_text.lower() == expected_text.lower()

                if success:
                    return True, f'text matches expected: {actual_text}'
                else:
                    return False, f'expected "{expected_text}", got "{actual_text}"'
        else:
            # Has placeholders - use placeholder system (handles regex and timestamp with tolerance)
            placeholder_names = self.get_placeholders(expected_str)
            if len(placeholder_names) == 1:
                placeholder_name = placeholder_names[0]
                try:
                    return self.compare_with_placeholder(placeholder_name, actual_text)
                except Exception as e:
                    return False, f"placeholder comparison error: {e}"
            else:
                return False, f"expected 1 placeholder for single value comparison, got {len(placeholder_names)}"

    def _handle_wildcard_matching(self, elements, expected_text, wildcard_mode, xpath):
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
            is_match, message = self._compare_values(element_text, expected_text)
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

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.failed([f'XML file {self.parameter.dst} not found ({status})'])

            log.debug(f'dst file {dst} will be used for test {self.name}')

            xpath = self.parameter.xpath
            expected_text = self.parameter.expected_text
            namespaces = self.parameter.namespaces

            try:
                root = self._parse_xml(dst)
                elements = self._find_elements(root, xpath, namespaces)

                if not elements:
                    return TestResult.failed([f'no elements found at XPath "{xpath}"'])

                # Handle multiple elements based on wildcard mode
                wildcard_mode = getattr(self.parameter, 'wildcard_mode', 'any')
                if len(elements) > 1:
                    return self._handle_wildcard_matching(elements, expected_text, wildcard_mode, xpath)
                else:
                    # Single element matching
                    element_text = elements[0].text or ""
                    is_match, message = self._compare_values(element_text, expected_text)
                    if is_match:
                        return TestResult.success([message])
                    else:
                        return TestResult.failed([message])

            except ValueError as e:
                return TestResult.execution_error(e, f"XML processing error")
            except FileNotFoundError:
                return TestResult.failed([f'XML file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read XML file {dst}")

        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in XML element text matches test")


@attrs.define
class AttributeMatchesParameter(Parameter):
    dst: str
    xpath: str
    attribute_name: str
    expected_value: str
    regex_match: Optional[bool] = False
    case_sensitive: Optional[bool] = True
    namespaces: Optional[Dict[str, str]] = None


@attrs.define
class AttributeMatches(BasicTest):
    testname: ClassVar[str] = 'attribute_matches'
    testdescription: ClassVar[str] = 'tests if XML element attribute matches expected value with regex and timestamp tolerance support'

    name: str
    parameter: AttributeMatchesParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def _parse_xml(self, filepath):
        """Parse XML file and return root element"""
        try:
            tree = ET.parse(filepath)
            return tree.getroot()
        except ET.ParseError as e:
            raise ValueError(f"Invalid XML format: {e}")

    def _find_elements(self, root, xpath, namespaces=None):
        """Find elements using XPath with namespace support"""
        try:
            if namespaces:
                return root.findall(xpath, namespaces)
            else:
                return root.findall(xpath)
        except (AttributeError, SyntaxError) as e:
            raise ValueError(f"Invalid XPath expression '{xpath}': {e}")

    def _compare_values(self, actual_value, expected_value):
        """Compare attribute values with regex and placeholder support"""
        expected_str = str(expected_value)

        if not self.has_placeholders(expected_str):
            # No placeholders - check for regex_match flag
            if self.parameter.regex_match:
                # Regex matching
                try:
                    flags = 0 if self.parameter.case_sensitive else re.IGNORECASE
                    pattern = re.compile(expected_value, flags)
                    if pattern.search(actual_value):
                        return True, f'attribute value "{actual_value}" matches regex "{expected_value}"'
                    else:
                        return False, f'attribute value "{actual_value}" does not match regex "{expected_value}"'
                except re.error as e:
                    return False, f'Invalid regex pattern: {expected_value} - {e}'
            else:
                # Direct value comparison
                if self.parameter.case_sensitive:
                    success = actual_value == expected_value
                else:
                    success = actual_value.lower() == expected_value.lower()

                if success:
                    return True, f'attribute value matches expected: {actual_value}'
                else:
                    return False, f'expected "{expected_value}", got "{actual_value}"'
        else:
            # Has placeholders - use placeholder system
            placeholder_names = self.get_placeholders(expected_str)
            if len(placeholder_names) == 1:
                placeholder_name = placeholder_names[0]
                try:
                    return self.compare_with_placeholder(placeholder_name, actual_value)
                except Exception as e:
                    return False, f"placeholder comparison error: {e}"
            else:
                return False, f"expected 1 placeholder for single value comparison, got {len(placeholder_names)}"

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.failed([f'XML file {self.parameter.dst} not found ({status})'])

            log.debug(f'dst file {dst} will be used for test {self.name}')

            xpath = self.parameter.xpath
            attribute_name = self.parameter.attribute_name
            expected_value = self.parameter.expected_value
            namespaces = self.parameter.namespaces

            try:
                root = self._parse_xml(dst)
                elements = self._find_elements(root, xpath, namespaces)

                if not elements:
                    return TestResult.failed([f'no elements found at XPath "{xpath}"'])

                # Check first matching element's attribute
                element = elements[0]
                if attribute_name not in element.attrib:
                    return TestResult.failed([f'attribute "{attribute_name}" not found in element at XPath "{xpath}"'])

                actual_value = element.attrib[attribute_name]
                is_match, message = self._compare_values(actual_value, expected_value)

                if is_match:
                    return TestResult.success([message])
                else:
                    return TestResult.failed([message])

            except ValueError as e:
                return TestResult.execution_error(e, f"XML processing error")
            except FileNotFoundError:
                return TestResult.failed([f'XML file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read XML file {dst}")

        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in XML attribute matches test")


@attrs.define
class ElementCountParameter(Parameter):
    dst: str
    xpath: str
    expected_count: int
    comparison_type: str = 'equals'  # equals, greater, less, greater_equal, less_equal
    namespaces: Optional[Dict[str, str]] = None


@attrs.define
class ElementCount(BasicTest):
    testname: ClassVar[str] = 'element_count'
    testdescription: ClassVar[str] = 'tests the number of XML elements matching XPath expression'

    name: str
    parameter: ElementCountParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def _parse_xml(self, filepath):
        """Parse XML file and return root element"""
        try:
            tree = ET.parse(filepath)
            return tree.getroot()
        except ET.ParseError as e:
            raise ValueError(f"Invalid XML format: {e}")

    def _find_elements(self, root, xpath, namespaces=None):
        """Find elements using XPath with namespace support"""
        try:
            if namespaces:
                return root.findall(xpath, namespaces)
            else:
                return root.findall(xpath)
        except (AttributeError, SyntaxError) as e:
            raise ValueError(f"Invalid XPath expression '{xpath}': {e}")

    def _compare_count(self, actual_count, expected_count, comparison_type):
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

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.failed([f'XML file {self.parameter.dst} not found ({status})'])

            log.debug(f'dst file {dst} will be used for test {self.name}')

            xpath = self.parameter.xpath
            expected_count = self.parameter.expected_count
            comparison_type = self.parameter.comparison_type
            namespaces = self.parameter.namespaces

            try:
                root = self._parse_xml(dst)
                elements = self._find_elements(root, xpath, namespaces)
                actual_count = len(elements)

                success, message = self._compare_count(actual_count, expected_count, comparison_type)

                if success:
                    return TestResult.success([f'element count matches: {message}'])
                else:
                    return TestResult.failed([f'element count mismatch: {message}'])

            except ValueError as e:
                return TestResult.execution_error(e, f"XML processing error")
            except FileNotFoundError:
                return TestResult.failed([f'XML file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read XML file {dst}")

        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in XML element count test")


@attrs.define
class XPathResultMatchesParameter(Parameter):
    dst: str
    xpath: str
    expected_result: Union[str, int, float, bool]
    result_type: str = 'text'  # text, number, boolean
    namespaces: Optional[Dict[str, str]] = None


@attrs.define
class XPathResultMatches(BasicTest):
    testname: ClassVar[str] = 'xpath_result_matches'
    testdescription: ClassVar[str] = 'tests if XPath expression result matches expected value (text, number, or boolean)'

    name: str
    parameter: XPathResultMatchesParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def _parse_xml(self, filepath):
        """Parse XML file and return root element"""
        try:
            tree = ET.parse(filepath)
            return tree.getroot()
        except ET.ParseError as e:
            raise ValueError(f"Invalid XML format: {e}")

    def _evaluate_xpath(self, root, xpath, result_type, namespaces=None):
        """Evaluate XPath and convert result based on type"""
        try:
            # Note: ElementTree has limited XPath support compared to lxml
            # This implementation covers basic functionality
            if result_type == 'text':
                elements = root.findall(xpath, namespaces or {})
                if elements:
                    return elements[0].text or ""
                else:
                    return ""
            elif result_type == 'number':
                elements = root.findall(xpath, namespaces or {})
                if elements:
                    text = elements[0].text or "0"
                    return float(text)
                else:
                    return 0.0
            elif result_type == 'boolean':
                elements = root.findall(xpath, namespaces or {})
                return len(elements) > 0
            else:
                raise ValueError(f"Unsupported result type: {result_type}")

        except (AttributeError, SyntaxError, ValueError) as e:
            raise ValueError(f"XPath evaluation error '{xpath}': {e}")

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.failed([f'XML file {self.parameter.dst} not found ({status})'])

            log.debug(f'dst file {dst} will be used for test {self.name}')

            xpath = self.parameter.xpath
            expected_result = self.parameter.expected_result
            result_type = self.parameter.result_type
            namespaces = self.parameter.namespaces

            try:
                root = self._parse_xml(dst)
                actual_result = self._evaluate_xpath(root, xpath, result_type, namespaces)

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
                return TestResult.failed([f'XML file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read XML file {dst}")

        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in XPath result matches test")


@attrs.define
class NamespaceMatchesParameter(Parameter):
    dst: str
    expected_namespaces: Dict[str, str]
    check_mode: str = 'contains'  # contains, exact


@attrs.define
class NamespaceMatches(BasicTest):
    testname: ClassVar[str] = 'namespace_matches'
    testdescription: ClassVar[str] = 'tests if XML namespace declarations match expected namespaces'

    name: str
    parameter: NamespaceMatchesParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def _parse_xml_with_namespaces(self, filepath):
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
        except ET.ParseError as e:
            raise ValueError(f"Invalid XML format: {e}")

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.failed([f'XML file {self.parameter.dst} not found ({status})'])

            log.debug(f'dst file {dst} will be used for test {self.name}')

            expected_namespaces = self.parameter.expected_namespaces
            check_mode = self.parameter.check_mode

            try:
                root, actual_namespaces = self._parse_xml_with_namespaces(dst)

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
                return TestResult.failed([f'XML file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read XML file {dst}")

        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in XML namespace matches test")