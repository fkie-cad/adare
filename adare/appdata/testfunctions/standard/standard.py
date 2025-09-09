# external imports
import attrs
from pathlib import Path
import csv
import re
import json
import sqlite3
import hashlib
import os
import stat
import platform
from datetime import datetime
from typing import ClassVar, Optional, Union

# internal imports
from adarelib.testset.basictest import BasicTest, Parameter
from adarelib.event.event import TestResult
from adarelib.constants import StatusEnum

# configure logging
import logging
log = logging.getLogger(__name__)




@attrs.define
class FileExistsParameter(Parameter):
    dst: str


@attrs.define
class FileExists(BasicTest):
    testname: ClassVar[str] = 'file_exists'
    testdescription: ClassVar[str] = 'tests if a file with path destination(dst)  is existing'

    name: str
    parameter: FileExistsParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            if Path(self.parameter.dst).is_file():
                return TestResult.success()
            else:
                return TestResult.failed([f'file with path {self.parameter.dst} does not exist'])
        except (OSError, PermissionError) as e:
            return TestResult.execution_error(e, f"Cannot check file existence for {self.parameter.dst}")


@attrs.define
class FileDoesNotExistParameter(Parameter):
    dst: str


@attrs.define
class FileDoesNotExist(BasicTest):
    testname: ClassVar[str] = 'file_does_not_exist'
    testdescription: ClassVar[str] = 'tests if a file with path destination(dst) is NOT existing'

    name: str
    parameter: FileDoesNotExistParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            if not Path(self.parameter.dst).is_file():
                return TestResult.success()
            else:
                return TestResult.failed([f'file with path {self.parameter.dst} does exist'])
        except (OSError, PermissionError) as e:
            return TestResult.execution_error(e, f"Cannot check file existence for {self.parameter.dst}")



@attrs.define
class DirExistsParameter(Parameter):
    dst: str


@attrs.define
class DirExists(BasicTest):
    testname: ClassVar[str] = 'dir_exists'
    testdescription: ClassVar[str] = 'tests if a directory with path destination(dst) is existing'

    name: str
    parameter: DirExistsParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            if Path(self.parameter.dst).is_dir():
                return TestResult.success()
            else:
                return TestResult.failed([f'directory with path {self.parameter.dst} does not exist'])
        except (OSError, PermissionError) as e:
            return TestResult.execution_error(e, f"Cannot check directory existence for {self.parameter.dst}")


@attrs.define
class DirDoesNotExistParameter(Parameter):
    dst: str


@attrs.define
class DirDoesNotExist(BasicTest):
    testname: ClassVar[str] = 'dir_does_not_exist'
    testdescription: ClassVar[str] = 'tests if a directory with path destination(dst) is NOT existing'

    name: str
    parameter: DirDoesNotExistParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            if not Path(self.parameter.dst).is_dir():
                return TestResult.success()
            else:
                return TestResult.failed([f'directory with path {self.parameter.dst} does exist'])
        except (OSError, PermissionError) as e:
            return TestResult.execution_error(e, f"Cannot check directory existence for {self.parameter.dst}")


@attrs.define
class DirContentParameter(Parameter):
    dst: str
    files: list


@attrs.define
class DirContent(BasicTest):
    testname: ClassVar[str] = 'dir_content'
    testdescription: ClassVar[str] = 'tests if a directory has the expected files/folders'

    name: str
    parameter: DirContentParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.error([f'directory with path {self.parameter.dst} can\'t be used, because no unambiguous directory could be identified (because {status})'])
            
            log.debug(f'dst directory {dst} will be used for test {self.name}')

            dir_content = [str(p) for p in Path(dst).iterdir()]
            expected_missing_files = [
                file for file in self.parameter.files if file not in dir_content
            ]
            additional_files = [
                file for file in dir_content if file not in self.parameter.files
            ]
            if expected_missing_files:
                details = [f'expected missing files: {expected_missing_files}']
                if additional_files:
                    details.append(f'additional files: {additional_files}')
                return TestResult.failed(details)

            return TestResult.success()
        except (OSError, PermissionError) as e:
            return TestResult.execution_error(e, f"Cannot read directory content for {self.parameter.dst}")


@attrs.define
class FileContentMatchesRegexParameter(Parameter):
    dst: str
    regex: str


@attrs.define
class FileContentMatchesRegex(BasicTest):
    testname: ClassVar[str] = 'file_content_matches_regex'
    testdescription: ClassVar[str] = 'tests if file content matches a given regex expression'

    name: str
    parameter: FileContentMatchesRegexParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.error([f'file with path {self.parameter.dst} can\'t be used, because no unambiguous file could be identified (because {status})'])
            
            log.debug(f'dst file {dst} will be used for test {self.name}')
            
            try:
                with open(dst, 'r') as f:
                    data = f.read()
            except FileNotFoundError:
                return TestResult.failed([f'file with path {self.parameter.dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read file {dst}")
            
            # Test regex compilation first
            try:
                pattern = re.compile(self.parameter.regex)
            except re.error as e:
                return TestResult.execution_error(e, f"Invalid regex pattern: {self.parameter.regex}")
            
            if pattern.search(data):
                return TestResult.success()
            else:
                return TestResult.failed(['file content does not match regex expression'])
                
        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in file content regex test")


def _row_matches_pattern(test_instance, row, entry_pattern):
    """Check if a CSV row matches the expected pattern using placeholder system.
    
    Returns:
        tuple: (is_match: bool, failed_columns: list, column_count_match: bool)
    """
    column_count_match = len(row) == len(entry_pattern)
    if not column_count_match:
        log.info(f"Row column count mismatch: got {len(row)} columns {row}, expected {len(entry_pattern)} columns {entry_pattern}")
        return False, [f"column_count({len(row)} != {len(entry_pattern)})"], False
    
    failed_columns = []
    
    # Check each column individually
    for i, (actual_value, expected_pattern) in enumerate(zip(row, entry_pattern)):
        expected_str = str(expected_pattern)
        
        if test_instance.has_placeholders(expected_str):
            # Has placeholder - use tolerance comparison
            placeholder_names = test_instance.get_placeholders(expected_str)
            if len(placeholder_names) == 1:
                placeholder_name = placeholder_names[0]
                try:
                    success, message = test_instance.compare_with_placeholder(placeholder_name, actual_value)
                    if not success:
                        failed_columns.append(f"col{i}({message})")
                except Exception as e:
                    log.error(f"Error in placeholder comparison for column {i}: {e}")
                    failed_columns.append(f"col{i}(placeholder_error: {e})")
            else:
                failed_columns.append(f"col{i}(invalid_placeholder: expected 1 placeholder, got {len(placeholder_names)})")
        else:
            # Direct string comparison
            if actual_value != expected_str:
                failed_columns.append(f"col{i}('{actual_value}' != '{expected_str}')")
    
    is_match = len(failed_columns) == 0
    
    # Log failures only if there were any
    if failed_columns:
        log.info(f"Row {row} failed pattern match: {', '.join(failed_columns)}")
    
    return is_match, failed_columns, column_count_match


@attrs.define
class CsvContainsLineParameter(Parameter):
    dst: str
    entry: list


@attrs.define
class CsvContainsLine(BasicTest):
    testname: ClassVar[str] = 'csv_contains_line'
    testdescription: ClassVar[str] = 'tests if row in a csv file exists that matches the given entry layout'

    name: str
    parameter: CsvContainsLineParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                # List files in directory to help with debugging
                try:
                    from pathlib import Path
                    search_path = Path(self.parameter.dst).parent if '/' in self.parameter.dst or '\\' in self.parameter.dst else Path('.')
                    available_files = [str(p.name) for p in search_path.iterdir() if p.is_file()]
                    files_info = f"Available files in directory: {available_files}" if available_files else "No files found in directory"
                except Exception:
                    files_info = "Could not list directory contents"
                
                return TestResult.execution_error(None, f'file with path {self.parameter.dst} can\'t be used, because no unambiguous file could be identified (because {status}). {files_info}')

            log.debug(f'dst file {dst} will be used for test {self.name}')
            
            # The entry pattern will be used directly with the placeholder system
            entry_pattern = self.parameter.entry

            try:
                with open(dst, 'r') as f:
                    reader = csv.reader(f)
                    rows = list(reader)
                    
                    # Track best matching rows for detailed error reporting
                    match_results = []
                    
                    for i, row in enumerate(rows):
                        is_match, failed_columns, column_count_match = _row_matches_pattern(self, row, entry_pattern)
                        if is_match:
                            return TestResult.success()
                        
                        # Store match details for error reporting
                        match_results.append({
                            'row_index': i,
                            'row': row,
                            'failed_columns': failed_columns,
                            'column_count_match': column_count_match,
                            'failure_count': len(failed_columns)
                        })
                
                # Log file contents for debugging when test fails
                log.info(f"CSV file '{dst}' contents for failed test '{self.name}':")
                for i, row in enumerate(rows):
                    log.info(f"  Row {i}: {row}")
                log.info(f"Expected entry pattern: {entry_pattern}")
                
                # Find the best matching rows (least number of failed columns)
                if match_results:
                    # Sort by failure count (ascending), then by whether column count matches
                    best_matches = sorted(match_results, key=lambda x: (x['failure_count'], not x['column_count_match']))
                    
                    # Build structured failure details
                    failure_details = [
                        f'no matching row found for pattern: {entry_pattern}',
                        f'analyzed {len(rows)} rows in CSV file'
                    ]
                    
                    # Add up to 3 best matching rows with detailed failures
                    failure_details.append('closest matches:')
                    for i, match in enumerate(best_matches[:3]):
                        failure_details.append(f'  [{i+1}] row {match["row_index"]}: {match["row"]}')
                        failure_details.append(f'      failures: {", ".join(match["failed_columns"])}')
                    
                    return TestResult.failed(failure_details)
                else:
                    return TestResult.failed([
                        f'no matching row found for pattern: {entry_pattern}',
                        'no rows found in CSV file to analyze'
                    ])
            except FileNotFoundError:
                return TestResult.execution_error(None, f'file with path {self.parameter.dst} does not exist')
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read CSV file {dst}")
            except csv.Error as e:
                return TestResult.execution_error(e, f"CSV parsing error in file {dst}")
                
        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in CSV line matching test")

@attrs.define
class FileContentEqualsParameter(Parameter):
    dst: str
    content: str

@attrs.define
class FileContentEquals(BasicTest):
    testname: ClassVar[str] = 'file_content_equals'
    testdescription: ClassVar[str] = 'tests if file content equals the given content'

    name: str
    parameter: FileContentEqualsParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.error([f'file with path {self.parameter.dst} can\'t be used, because no unambiguous file could be identified (because {status})'])
            
            log.debug(f'dst file {dst} will be used for test {self.name}')
            try:
                with open(dst, 'r') as f:
                    data = f.read()
            except FileNotFoundError:
                return TestResult.failed([f'file with path {self.parameter.dst} does not exist'])
            except (PermissionError, OSError, UnicodeDecodeError) as e:
                return TestResult.execution_error(e, f"Cannot read file {dst}")
                
            # Check if we have placeholders that need special handling
            expected_content = self.parameter.content
            
            if not self.has_placeholders(expected_content):
                # No placeholders - direct comparison (content already fully resolved by client)
                success = data.strip() == expected_content.strip()
                message = "Direct content comparison"
            else:
                # Has placeholders - special handling needed
                try:
                    success, message = self._handle_placeholders_comparison(data.strip(), expected_content)
                except Exception as e:
                    return TestResult.execution_error(e, "Error in placeholder comparison logic")
                
            if success:
                return TestResult.success([message])
            else:
                # Show diff for debugging
                try:
                    import difflib
                    expected_for_diff = expected_content
                    diff_lines = list(difflib.unified_diff(
                        expected_for_diff.splitlines(keepends=True),
                        data.splitlines(keepends=True),
                        fromfile='expected',
                        tofile='actual',
                        lineterm=''
                    ))
                    diff_output = ''.join(diff_lines) if diff_lines else 'Content differs but no line-by-line diff available'
                    
                    return TestResult.failed([
                        message,
                        f'Diff:\n{diff_output}'
                    ])
                except Exception as e:
                    return TestResult.execution_error(e, "Error generating diff output")
                    
        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in file content equals test")


@attrs.define
class SqliteQueryResultParameter(Parameter):
    dst: str
    query: str
    expected_rows: Optional[int] = None
    expected_result: Optional[list] = None

@attrs.define
class SqliteQueryResult(BasicTest):
    testname: ClassVar[str] = 'sqlite_query_result'
    testdescription: ClassVar[str] = 'executes SQL query against SQLite database and validates result'

    name: str
    parameter: SqliteQueryResultParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.error([f'database file {self.parameter.dst} can\'t be used, because no unambiguous file could be identified (because {status})'])
            
            log.debug(f'dst database {dst} will be used for test {self.name}')
            
            # Handle variables in query and expected results
            query = self.parameter.query
            if self.has_placeholders(query):
                query = self.resolve_variables(query)
            
            expected_result = self.parameter.expected_result
            if expected_result and self.has_placeholders(str(expected_result)):
                expected_result = self.resolve_variables(str(expected_result))
                try:
                    expected_result = json.loads(expected_result) if isinstance(expected_result, str) else expected_result
                except json.JSONDecodeError:
                    pass
            
            try:
                conn = sqlite3.connect(dst)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute(query)
                rows = cursor.fetchall()
                
                # Convert to list of dicts for easier comparison
                result = [dict(row) for row in rows]
                
                conn.close()
                
                # Check expected row count
                if self.parameter.expected_rows is not None:
                    if len(result) != self.parameter.expected_rows:
                        return TestResult.failed([f'expected {self.parameter.expected_rows} rows, got {len(result)}'])
                
                # Check expected result content
                if expected_result is not None:
                    if result != expected_result:
                        return TestResult.failed([f'query result does not match expected result. Got: {result}'])
                
                return TestResult.success([f'query returned {len(result)} rows'])
                
            except sqlite3.Error as e:
                return TestResult.execution_error(e, f"SQLite error executing query: {query}")
            except FileNotFoundError:
                return TestResult.failed([f'database file {dst} does not exist'])
                
        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in SQLite query test")


@attrs.define
class JsonContainsKeyParameter(Parameter):
    dst: str
    key_path: str

@attrs.define
class JsonContainsKey(BasicTest):
    testname: ClassVar[str] = 'json_contains_key'
    testdescription: ClassVar[str] = 'tests if JSON file contains specified key path (supports dot notation like "user.profile.name")'

    name: str
    parameter: JsonContainsKeyParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def _get_nested_value(self, data, key_path):
        """Navigate nested dictionary using dot notation"""
        keys = key_path.split('.')
        current = data
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None, False
        return current, True

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.error([f'JSON file {self.parameter.dst} can\'t be used, because no unambiguous file could be identified (because {status})'])
            
            log.debug(f'dst file {dst} will be used for test {self.name}')
            
            # Handle variables in key path
            key_path = self.parameter.key_path
            if self.has_placeholders(key_path):
                key_path = self.resolve_variables(key_path)
            
            try:
                with open(dst, 'r') as f:
                    data = json.load(f)
                    
                value, exists = self._get_nested_value(data, key_path)
                
                if exists:
                    return TestResult.success([f'key path "{key_path}" exists with value: {value}'])
                else:
                    return TestResult.failed([f'key path "{key_path}" does not exist'])
                    
            except json.JSONDecodeError as e:
                return TestResult.execution_error(e, f"Invalid JSON in file {dst}")
            except FileNotFoundError:
                return TestResult.failed([f'JSON file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read JSON file {dst}")
                
        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in JSON contains key test")


@attrs.define
class JsonValueMatchesParameter(Parameter):
    dst: str
    key_path: str
    expected_value: Union[str, int, float, bool, None]
    regex_match: Optional[bool] = False

@attrs.define
class JsonValueMatches(BasicTest):
    testname: ClassVar[str] = 'json_value_matches'
    testdescription: ClassVar[str] = 'tests if JSON value at key path matches expected value or regex'

    name: str
    parameter: JsonValueMatchesParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def _get_nested_value(self, data, key_path):
        """Navigate nested dictionary using dot notation"""
        keys = key_path.split('.')
        current = data
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None, False
        return current, True

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.error([f'JSON file {self.parameter.dst} can\'t be used, because no unambiguous file could be identified (because {status})'])
            
            log.debug(f'dst file {dst} will be used for test {self.name}')
            
            # Handle variables in key path and expected value
            key_path = self.parameter.key_path
            if self.has_placeholders(key_path):
                key_path = self.resolve_variables(key_path)
            
            expected_value = self.parameter.expected_value
            if self.has_placeholders(str(expected_value)):
                expected_value = self.resolve_variables(str(expected_value))
                # Try to convert back to appropriate type
                if expected_value.lower() == 'true':
                    expected_value = True
                elif expected_value.lower() == 'false':
                    expected_value = False
                elif expected_value.lower() == 'null':
                    expected_value = None
                elif expected_value.isdigit():
                    expected_value = int(expected_value)
                else:
                    try:
                        expected_value = float(expected_value)
                    except ValueError:
                        pass  # Keep as string
            
            try:
                with open(dst, 'r') as f:
                    data = json.load(f)
                    
                value, exists = self._get_nested_value(data, key_path)
                
                if not exists:
                    return TestResult.failed([f'key path "{key_path}" does not exist'])
                
                if self.parameter.regex_match and isinstance(expected_value, str):
                    # Regex matching
                    try:
                        pattern = re.compile(expected_value)
                        if pattern.search(str(value)):
                            return TestResult.success([f'value "{value}" matches regex "{expected_value}"'])
                        else:
                            return TestResult.failed([f'value "{value}" does not match regex "{expected_value}"'])
                    except re.error as e:
                        return TestResult.execution_error(e, f"Invalid regex pattern: {expected_value}")
                else:
                    # Direct value comparison
                    if value == expected_value:
                        return TestResult.success([f'value matches expected: {value}'])
                    else:
                        return TestResult.failed([f'expected "{expected_value}", got "{value}"'])
                    
            except json.JSONDecodeError as e:
                return TestResult.execution_error(e, f"Invalid JSON in file {dst}")
            except FileNotFoundError:
                return TestResult.failed([f'JSON file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read JSON file {dst}")
                
        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in JSON value matches test")


@attrs.define
class JsonArrayContainsParameter(Parameter):
    dst: str
    array_path: str
    expected_element: Union[str, int, float, bool, dict, list]

@attrs.define
class JsonArrayContains(BasicTest):
    testname: ClassVar[str] = 'json_array_contains'
    testdescription: ClassVar[str] = 'tests if JSON array at specified path contains expected element'

    name: str
    parameter: JsonArrayContainsParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def _get_nested_value(self, data, key_path):
        """Navigate nested dictionary using dot notation"""
        keys = key_path.split('.')
        current = data
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None, False
        return current, True

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.error([f'JSON file {self.parameter.dst} can\'t be used, because no unambiguous file could be identified (because {status})'])
            
            log.debug(f'dst file {dst} will be used for test {self.name}')
            
            # Handle variables in array path and expected element
            array_path = self.parameter.array_path
            if self.has_placeholders(array_path):
                array_path = self.resolve_variables(array_path)
            
            expected_element = self.parameter.expected_element
            if self.has_placeholders(str(expected_element)):
                expected_element = self.resolve_variables(str(expected_element))
                # Try to parse as JSON if it looks like structured data
                try:
                    expected_element = json.loads(expected_element)
                except json.JSONDecodeError:
                    pass  # Keep as string
            
            try:
                with open(dst, 'r') as f:
                    data = json.load(f)
                    
                array, exists = self._get_nested_value(data, array_path)
                
                if not exists:
                    return TestResult.failed([f'array path "{array_path}" does not exist'])
                
                if not isinstance(array, list):
                    return TestResult.failed([f'path "{array_path}" is not an array, got {type(array).__name__}'])
                
                if expected_element in array:
                    return TestResult.success([f'array contains expected element: {expected_element}'])
                else:
                    return TestResult.failed([f'array does not contain expected element: {expected_element}'])
                    
            except json.JSONDecodeError as e:
                return TestResult.execution_error(e, f"Invalid JSON in file {dst}")
            except FileNotFoundError:
                return TestResult.failed([f'JSON file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read JSON file {dst}")
                
        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in JSON array contains test")


@attrs.define
class FileHashMatchesParameter(Parameter):
    dst: str
    expected_hash: str
    hash_type: str = 'sha256'  # md5, sha1, sha256, sha512

@attrs.define
class FileHashMatches(BasicTest):
    testname: ClassVar[str] = 'file_hash_matches'
    testdescription: ClassVar[str] = 'tests if file hash matches expected value'

    name: str
    parameter: FileHashMatchesParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def _calculate_hash(self, filepath, hash_type):
        """Calculate file hash"""
        hash_algos = {
            'md5': hashlib.md5,
            'sha1': hashlib.sha1,
            'sha256': hashlib.sha256,
            'sha512': hashlib.sha512
        }
        
        if hash_type.lower() not in hash_algos:
            raise ValueError(f"Unsupported hash type: {hash_type}")
        
        hasher = hash_algos[hash_type.lower()]()
        
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        
        return hasher.hexdigest()

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.error([f'file {self.parameter.dst} can\'t be used, because no unambiguous file could be identified (because {status})'])
            
            log.debug(f'dst file {dst} will be used for test {self.name}')
            
            # Handle variables in expected hash
            expected_hash = self.parameter.expected_hash
            if self.has_placeholders(expected_hash):
                expected_hash = self.resolve_variables(expected_hash)
            
            expected_hash = expected_hash.lower()
            
            try:
                actual_hash = self._calculate_hash(dst, self.parameter.hash_type)
                
                if actual_hash == expected_hash:
                    return TestResult.success([f'{self.parameter.hash_type.upper()} hash matches: {actual_hash}'])
                else:
                    return TestResult.failed([f'{self.parameter.hash_type.upper()} hash mismatch. Expected: {expected_hash}, Got: {actual_hash}'])
                    
            except FileNotFoundError:
                return TestResult.failed([f'file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read file {dst}")
            except ValueError as e:
                return TestResult.execution_error(e, "Hash calculation error")
                
        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in file hash test")


@attrs.define
class FileTimestampsParameter(Parameter):
    dst: str
    timestamp_type: str = 'modified'  # modified, accessed, created
    comparison_type: str = 'equals'  # equals, before, after, between, within_last
    expected_time: Optional[Union[str, int, float]] = None
    time_format: Optional[str] = None  # strptime format
    tolerance_seconds: Optional[int] = None
    start_time: Optional[Union[str, int, float]] = None  # For 'between' comparison
    end_time: Optional[Union[str, int, float]] = None    # For 'between' comparison
    within_duration: Optional[str] = None  # For 'within_last' e.g., "1h", "30m", "2d"

@attrs.define
class FileTimestamps(BasicTest):
    testname: ClassVar[str] = 'file_timestamps'
    testdescription: ClassVar[str] = 'tests file timestamps with various comparison types and formats'

    name: str
    parameter: FileTimestampsParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def _parse_duration(self, duration_str):
        """Parse duration string like '1h', '30m', '2d' to seconds"""
        units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        
        if not duration_str or not duration_str[-1] in units:
            raise ValueError(f"Invalid duration format: {duration_str}")
        
        try:
            value = int(duration_str[:-1])
            unit = duration_str[-1]
            return value * units[unit]
        except ValueError:
            raise ValueError(f"Invalid duration format: {duration_str}")

    def _parse_timestamp(self, timestamp, time_format=None):
        """Parse timestamp to Unix timestamp"""
        if isinstance(timestamp, (int, float)):
            return float(timestamp)
        
        # Handle variables
        if self.has_placeholders(str(timestamp)):
            timestamp = self.resolve_variables(str(timestamp))
        
        # Try parsing as number first
        try:
            return float(timestamp)
        except (ValueError, TypeError):
            pass
        
        # Parse with custom format
        if time_format:
            try:
                dt = datetime.strptime(timestamp, time_format)
                return dt.timestamp()
            except ValueError:
                pass
        
        # Try common formats
        common_formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%d',
            '%m/%d/%Y %H:%M:%S',
            '%m/%d/%Y'
        ]
        
        for fmt in common_formats:
            try:
                dt = datetime.strptime(timestamp, fmt)
                return dt.timestamp()
            except ValueError:
                continue
        
        raise ValueError(f"Cannot parse timestamp: {timestamp}")

    def _get_file_timestamp(self, filepath, timestamp_type):
        """Get file timestamp based on type"""
        stat_info = os.stat(filepath)
        
        if timestamp_type == 'modified':
            return stat_info.st_mtime
        elif timestamp_type == 'accessed':
            return stat_info.st_atime
        elif timestamp_type == 'created':
            # On Unix, st_ctime is not creation time but change time
            # On Windows, it is creation time
            if platform.system() == 'Windows':
                return stat_info.st_ctime
            else:
                # Try to get birth time on systems that support it
                try:
                    return stat_info.st_birthtime
                except AttributeError:
                    # Fall back to change time
                    return stat_info.st_ctime
        else:
            raise ValueError(f"Unsupported timestamp type: {timestamp_type}")

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.error([f'file {self.parameter.dst} can\'t be used, because no unambiguous file could be identified (because {status})'])
            
            log.debug(f'dst file {dst} will be used for test {self.name}')
            
            try:
                actual_time = self._get_file_timestamp(dst, self.parameter.timestamp_type)
                comparison_type = self.parameter.comparison_type
                
                if comparison_type == 'equals':
                    expected_time = self._parse_timestamp(self.parameter.expected_time, self.parameter.time_format)
                    
                    tolerance = self.parameter.tolerance_seconds or 0
                    if abs(actual_time - expected_time) <= tolerance:
                        return TestResult.success([f'{self.parameter.timestamp_type} timestamp matches (±{tolerance}s): {datetime.fromtimestamp(actual_time)}'])
                    else:
                        return TestResult.failed([f'{self.parameter.timestamp_type} timestamp mismatch. Expected: {datetime.fromtimestamp(expected_time)}, Got: {datetime.fromtimestamp(actual_time)}'])
                
                elif comparison_type == 'before':
                    expected_time = self._parse_timestamp(self.parameter.expected_time, self.parameter.time_format)
                    if actual_time < expected_time:
                        return TestResult.success([f'{self.parameter.timestamp_type} timestamp is before {datetime.fromtimestamp(expected_time)}'])
                    else:
                        return TestResult.failed([f'{self.parameter.timestamp_type} timestamp is not before {datetime.fromtimestamp(expected_time)}'])
                
                elif comparison_type == 'after':
                    expected_time = self._parse_timestamp(self.parameter.expected_time, self.parameter.time_format)
                    if actual_time > expected_time:
                        return TestResult.success([f'{self.parameter.timestamp_type} timestamp is after {datetime.fromtimestamp(expected_time)}'])
                    else:
                        return TestResult.failed([f'{self.parameter.timestamp_type} timestamp is not after {datetime.fromtimestamp(expected_time)}'])
                
                elif comparison_type == 'between':
                    start_time = self._parse_timestamp(self.parameter.start_time, self.parameter.time_format)
                    end_time = self._parse_timestamp(self.parameter.end_time, self.parameter.time_format)
                    if start_time <= actual_time <= end_time:
                        return TestResult.success([f'{self.parameter.timestamp_type} timestamp is between {datetime.fromtimestamp(start_time)} and {datetime.fromtimestamp(end_time)}'])
                    else:
                        return TestResult.failed([f'{self.parameter.timestamp_type} timestamp is not between {datetime.fromtimestamp(start_time)} and {datetime.fromtimestamp(end_time)}'])
                
                elif comparison_type == 'within_last':
                    duration_seconds = self._parse_duration(self.parameter.within_duration)
                    current_time = datetime.now().timestamp()
                    threshold_time = current_time - duration_seconds
                    
                    if actual_time >= threshold_time:
                        return TestResult.success([f'{self.parameter.timestamp_type} timestamp is within last {self.parameter.within_duration}'])
                    else:
                        return TestResult.failed([f'{self.parameter.timestamp_type} timestamp is not within last {self.parameter.within_duration}'])
                
                else:
                    return TestResult.error([f'Unsupported comparison type: {comparison_type}'])
                    
            except FileNotFoundError:
                return TestResult.failed([f'file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot access file {dst}")
            except ValueError as e:
                return TestResult.execution_error(e, "Timestamp parsing/comparison error")
                
        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in file timestamps test")


@attrs.define
class FilePermissionsParameter(Parameter):
    dst: str
    expected_permissions: str  # octal like '755' or symbolic like 'rwxr-xr-x'
    check_owner: Optional[str] = None
    check_group: Optional[str] = None

@attrs.define
class FilePermissions(BasicTest):
    testname: ClassVar[str] = 'file_permissions'
    testdescription: ClassVar[str] = 'tests file permissions, owner, and group'

    name: str
    parameter: FilePermissionsParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def _parse_permissions(self, perm_str):
        """Parse permission string to octal"""
        if perm_str.isdigit():
            # Already octal
            return int(perm_str, 8)
        
        # Parse symbolic notation like 'rwxr-xr-x'
        if len(perm_str) == 9:
            perms = 0
            # Owner permissions
            if perm_str[0] == 'r': perms |= stat.S_IRUSR
            if perm_str[1] == 'w': perms |= stat.S_IWUSR
            if perm_str[2] == 'x': perms |= stat.S_IXUSR
            # Group permissions
            if perm_str[3] == 'r': perms |= stat.S_IRGRP
            if perm_str[4] == 'w': perms |= stat.S_IWGRP
            if perm_str[5] == 'x': perms |= stat.S_IXGRP
            # Other permissions
            if perm_str[6] == 'r': perms |= stat.S_IROTH
            if perm_str[7] == 'w': perms |= stat.S_IWOTH
            if perm_str[8] == 'x': perms |= stat.S_IXOTH
            return perms
        
        raise ValueError(f"Invalid permission format: {perm_str}")

    def _get_owner_group(self, filepath):
        """Get file owner and group names"""
        try:
            import pwd
            import grp
            stat_info = os.stat(filepath)
            owner = pwd.getpwuid(stat_info.st_uid).pw_name
            group = grp.getgrgid(stat_info.st_gid).gr_name
            return owner, group
        except ImportError:
            # Windows doesn't have pwd/grp modules
            return None, None
        except (KeyError, OSError):
            return None, None

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.error([f'file {self.parameter.dst} can\'t be used, because no unambiguous file could be identified (because {status})'])
            
            log.debug(f'dst file {dst} will be used for test {self.name}')
            
            # Handle variables in expected permissions
            expected_permissions = self.parameter.expected_permissions
            if self.has_placeholders(expected_permissions):
                expected_permissions = self.resolve_variables(expected_permissions)
            
            check_owner = self.parameter.check_owner
            if check_owner and self.has_placeholders(check_owner):
                check_owner = self.resolve_variables(check_owner)
            
            check_group = self.parameter.check_group
            if check_group and self.has_placeholders(check_group):
                check_group = self.resolve_variables(check_group)
            
            try:
                stat_info = os.stat(dst)
                actual_perms = stat_info.st_mode & 0o777
                expected_perms = self._parse_permissions(expected_permissions)
                
                results = []
                success = True
                
                # Check permissions
                if actual_perms == expected_perms:
                    results.append(f'permissions match: {oct(actual_perms)[-3:]}')
                else:
                    results.append(f'permission mismatch. Expected: {oct(expected_perms)[-3:]}, Got: {oct(actual_perms)[-3:]}')
                    success = False
                
                # Check owner and group if specified
                if check_owner or check_group:
                    owner, group = self._get_owner_group(dst)
                    
                    if check_owner:
                        if owner == check_owner:
                            results.append(f'owner matches: {owner}')
                        else:
                            results.append(f'owner mismatch. Expected: {check_owner}, Got: {owner}')
                            success = False
                    
                    if check_group:
                        if group == check_group:
                            results.append(f'group matches: {group}')
                        else:
                            results.append(f'group mismatch. Expected: {check_group}, Got: {group}')
                            success = False
                
                if success:
                    return TestResult.success(results)
                else:
                    return TestResult.failed(results)
                    
            except FileNotFoundError:
                return TestResult.failed([f'file {dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot access file {dst}")
            except ValueError as e:
                return TestResult.execution_error(e, "Permission parsing error")
                
        except Exception as e:
            return TestResult.execution_error(e, "Unexpected error in file permissions test")


# Windows-only registry tests
if platform.system() == 'Windows':
    try:
        import winreg
        
        @attrs.define
        class RegistryKeyExistsParameter(Parameter):
            key_path: str  # Full registry path like "HKEY_LOCAL_MACHINE\Software\Microsoft\Windows\CurrentVersion"

        @attrs.define
        class RegistryKeyExists(BasicTest):
            testname: ClassVar[str] = 'registry_key_exists'
            testdescription: ClassVar[str] = 'tests if Windows registry key exists (Windows only)'

            name: str
            parameter: RegistryKeyExistsParameter
            description: Optional[str] = ''
            variable_metadata: Optional[dict] = None

            def _parse_registry_path(self, key_path):
                """Parse registry path into root key and subkey"""
                hive_mapping = {
                    'HKEY_CLASSES_ROOT': winreg.HKEY_CLASSES_ROOT,
                    'HKCR': winreg.HKEY_CLASSES_ROOT,
                    'HKEY_CURRENT_USER': winreg.HKEY_CURRENT_USER,
                    'HKCU': winreg.HKEY_CURRENT_USER,
                    'HKEY_LOCAL_MACHINE': winreg.HKEY_LOCAL_MACHINE,
                    'HKLM': winreg.HKEY_LOCAL_MACHINE,
                    'HKEY_USERS': winreg.HKEY_USERS,
                    'HKU': winreg.HKEY_USERS,
                    'HKEY_CURRENT_CONFIG': winreg.HKEY_CURRENT_CONFIG,
                    'HKCC': winreg.HKEY_CURRENT_CONFIG
                }
                
                # Split path
                parts = key_path.replace('/', '\\').split('\\', 1)
                if len(parts) != 2:
                    raise ValueError(f"Invalid registry path format: {key_path}")
                
                hive_name = parts[0].upper()
                subkey = parts[1]
                
                if hive_name not in hive_mapping:
                    raise ValueError(f"Invalid registry hive: {hive_name}")
                
                return hive_mapping[hive_name], subkey

            def test(self):
                try:
                    # Handle variables in key path
                    key_path = self.parameter.key_path
                    if self.has_placeholders(key_path):
                        key_path = self.resolve_variables(key_path)
                    
                    try:
                        hive, subkey = self._parse_registry_path(key_path)
                        
                        try:
                            key = winreg.OpenKey(hive, subkey)
                            winreg.CloseKey(key)
                            return TestResult.success([f'registry key exists: {key_path}'])
                        except FileNotFoundError:
                            return TestResult.failed([f'registry key does not exist: {key_path}'])
                        except PermissionError:
                            return TestResult.execution_error(None, f"Permission denied accessing registry key: {key_path}")
                            
                    except ValueError as e:
                        return TestResult.execution_error(e, "Registry path parsing error")
                        
                except Exception as e:
                    return TestResult.execution_error(e, "Unexpected error in registry key exists test")

        @attrs.define
        class RegistryValueMatchesParameter(Parameter):
            key_path: str  # Registry key path
            value_name: str  # Value name within the key
            expected_value: Union[str, int, bytes]
            value_type: Optional[str] = None  # REG_SZ, REG_DWORD, REG_BINARY, etc.

        @attrs.define
        class RegistryValueMatches(BasicTest):
            testname: ClassVar[str] = 'registry_value_matches'
            testdescription: ClassVar[str] = 'tests if Windows registry value matches expected value (Windows only)'

            name: str
            parameter: RegistryValueMatchesParameter
            description: Optional[str] = ''
            variable_metadata: Optional[dict] = None

            def _parse_registry_path(self, key_path):
                """Parse registry path into root key and subkey"""
                hive_mapping = {
                    'HKEY_CLASSES_ROOT': winreg.HKEY_CLASSES_ROOT,
                    'HKCR': winreg.HKEY_CLASSES_ROOT,
                    'HKEY_CURRENT_USER': winreg.HKEY_CURRENT_USER,
                    'HKCU': winreg.HKEY_CURRENT_USER,
                    'HKEY_LOCAL_MACHINE': winreg.HKEY_LOCAL_MACHINE,
                    'HKLM': winreg.HKEY_LOCAL_MACHINE,
                    'HKEY_USERS': winreg.HKEY_USERS,
                    'HKU': winreg.HKEY_USERS,
                    'HKEY_CURRENT_CONFIG': winreg.HKEY_CURRENT_CONFIG,
                    'HKCC': winreg.HKEY_CURRENT_CONFIG
                }
                
                # Split path
                parts = key_path.replace('/', '\\').split('\\', 1)
                if len(parts) != 2:
                    raise ValueError(f"Invalid registry path format: {key_path}")
                
                hive_name = parts[0].upper()
                subkey = parts[1]
                
                if hive_name not in hive_mapping:
                    raise ValueError(f"Invalid registry hive: {hive_name}")
                
                return hive_mapping[hive_name], subkey

            def _format_registry_type(self, reg_type):
                """Convert winreg type constants to readable names"""
                type_names = {
                    winreg.REG_BINARY: 'REG_BINARY',
                    winreg.REG_DWORD: 'REG_DWORD',
                    winreg.REG_DWORD_LITTLE_ENDIAN: 'REG_DWORD_LITTLE_ENDIAN',
                    winreg.REG_DWORD_BIG_ENDIAN: 'REG_DWORD_BIG_ENDIAN',
                    winreg.REG_EXPAND_SZ: 'REG_EXPAND_SZ',
                    winreg.REG_LINK: 'REG_LINK',
                    winreg.REG_MULTI_SZ: 'REG_MULTI_SZ',
                    winreg.REG_NONE: 'REG_NONE',
                    winreg.REG_RESOURCE_LIST: 'REG_RESOURCE_LIST',
                    winreg.REG_SZ: 'REG_SZ'
                }
                return type_names.get(reg_type, f'UNKNOWN_TYPE_{reg_type}')

            def test(self):
                try:
                    # Handle variables
                    key_path = self.parameter.key_path
                    if self.has_placeholders(key_path):
                        key_path = self.resolve_variables(key_path)
                    
                    value_name = self.parameter.value_name
                    if self.has_placeholders(value_name):
                        value_name = self.resolve_variables(value_name)
                    
                    expected_value = self.parameter.expected_value
                    if self.has_placeholders(str(expected_value)):
                        expected_value = self.resolve_variables(str(expected_value))
                        # Try to convert back to appropriate type
                        if isinstance(expected_value, str) and expected_value.isdigit():
                            expected_value = int(expected_value)
                    
                    try:
                        hive, subkey = self._parse_registry_path(key_path)
                        
                        try:
                            key = winreg.OpenKey(hive, subkey)
                            actual_value, reg_type = winreg.QueryValueEx(key, value_name)
                            winreg.CloseKey(key)
                            
                            # Type checking if specified
                            if self.parameter.value_type:
                                expected_type_name = self.parameter.value_type.upper()
                                actual_type_name = self._format_registry_type(reg_type)
                                
                                if expected_type_name != actual_type_name:
                                    return TestResult.failed([f'registry value type mismatch. Expected: {expected_type_name}, Got: {actual_type_name}'])
                            
                            # Value comparison
                            if actual_value == expected_value:
                                return TestResult.success([f'registry value matches: {actual_value} ({self._format_registry_type(reg_type)})'])
                            else:
                                return TestResult.failed([f'registry value mismatch. Expected: {expected_value}, Got: {actual_value} ({self._format_registry_type(reg_type)})'])
                                
                        except FileNotFoundError:
                            return TestResult.failed([f'registry key or value does not exist: {key_path}\\{value_name}'])
                        except PermissionError:
                            return TestResult.execution_error(None, f"Permission denied accessing registry: {key_path}\\{value_name}")
                            
                    except ValueError as e:
                        return TestResult.execution_error(e, "Registry path parsing error")
                        
                except Exception as e:
                    return TestResult.execution_error(e, "Unexpected error in registry value matches test")
                    
    except ImportError:
        # winreg not available, skip registry tests
        log.info("Windows registry tests not available (winreg module not found)")
    
