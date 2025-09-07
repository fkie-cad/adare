# external imports
import attrs
from pathlib import Path
import csv
import re
from typing import ClassVar, Optional

# internal imports
from adarelib.testset.basictest import BasicTest, Parameter
from adarelib.event.event import TestResult
from adarelib.constants import StatusEnum
import adarelib.testset.yaml.customtags as yml

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


def _row_match(row, comparison_list):
    for item_index, item in enumerate(row):
        match = False
        comparison_element = comparison_list[item_index]
        if type(comparison_element) in yml.YAML_CUSTOM_TAGS:
            match = comparison_element.compare(item)
        elif comparison_element == item:
            match = True
        if not match:
            return False
    return True


@attrs.define
class CsvContainsLineMatchingRegexParameter(Parameter):
    dst: str
    entry: list


@attrs.define
class CsvContainsLineMatchingRegex(BasicTest):
    testname: ClassVar[str] = 'csv_contains_line_matching_regex'
    testdescription: ClassVar[str] = 'tests if row in a csv file exists that matches the given entry layout'

    name: str
    parameter: CsvContainsLineMatchingRegexParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.error([f'file with path {self.parameter.dst} can\'t be used, because no unambiguous file could be identified (because {status})'])

            log.debug(f'dst file {dst} will be used for test {self.name}')
            comparison_list = []
            for entry in self.parameter.entry:
                if entry is str:
                    comparison_list.append(yml.YamlString(entry))
                else:
                    comparison_list.append(entry)

            try:
                with open(dst, 'r') as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if _row_match(row, comparison_list):
                            return TestResult.success()
                return TestResult.failed([f'entry {self.parameter.entry} does not exist in file'])
            except FileNotFoundError:
                return TestResult.failed([f'file with path {self.parameter.dst} does not exist'])
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
    
