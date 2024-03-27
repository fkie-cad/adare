# external imports
import attrs
from pathlib import Path
import csv
import re
from typing import ClassVar, Optional

# internal imports
from adarevm.testset.basictest import BasicTest, Parameter
from adarelib.types import TestSuccess, TestFailed, TestResult
import adarelib.customyaml.customtags as yml

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
    params: FileExistsParameter
    description: Optional[str] = ''

    def test(self):
        if Path(self.params.dst).is_file():
            result = TestResult(
                status=TestSuccess(),
            )

        else:
            result = TestResult(
                status=TestFailed(),
                details=[f'file with path {self.params.dst} does not exist']
            )
        self.log_test_event(result)


@attrs.define
class FileDoesNotExistParameter(Parameter):
    dst: str


@attrs.define
class FileDoesNotExist(BasicTest):
    testname: ClassVar[str] = 'file_does_not_exist'
    testdescription: ClassVar[str] = 'tests if a file with path destination(dst) is NOT existing'

    name: str
    params: FileDoesNotExistParameter
    description: Optional[str] = ''

    def test(self):
        if not Path(self.params.dst).is_file():
            result = TestResult(
                status=TestSuccess(),
            )
        else:
            result = TestResult(
                status=TestFailed(),
                details=[f'file with path {self.params.dst} does exist']
            )
        self.log_test_event(result)



@attrs.define
class DirExistsParameter(Parameter):
    dst: str


@attrs.define
class DirExists(BasicTest):
    testname: ClassVar[str] = 'dir_exists'
    testdescription: ClassVar[str] = 'tests if a directory with path destination(dst) is existing'

    name: str
    params: DirExistsParameter
    description: Optional[str] = ''

    def test(self):
        if Path(self.params.dst).is_dir():
            result = TestResult(
                status=TestSuccess(),
            )
        else:
            result = TestResult(
                status=TestFailed(),
                details=[f'directory with path {self.params.dst} does not exist']
            )
        self.log_test_event(result)


@attrs.define
class DirDoesNotExistParameter(Parameter):
    dst: str


@attrs.define
class DirDoesNotExist(BasicTest):
    testname: ClassVar[str] = 'dir_does_not_exist'
    testdescription: ClassVar[str] = 'tests if a directory with path destination(dst) is NOT existing'

    name: str
    params: DirDoesNotExistParameter
    description: Optional[str] = ''

    def test(self):
        if not Path(self.params.dst).is_dir():
            result = TestResult(
                status=TestSuccess(),
            )
        else:
            result = TestResult(
                status=TestFailed(),
                details=[f'directory with path {self.params.dst} does exist']
            )
        self.log_test_event(result)


@attrs.define
class DirContentParameter(Parameter):
    dst: str
    files: list


@attrs.define
class DirContent(BasicTest):
    testname: ClassVar[str] = 'dir_content'
    testdescription: ClassVar[str] = 'tests if a directory has the expected files/folders'

    name: str
    params: DirContentParameter
    description: Optional[str] = ''

    def test(self):
        dst, status = self.resolve_globfilepath(self.params.dst)
        if not dst:
            result = TestResult(
                status=TestFailed(),
                details=[f'directory with path {self.params.dst} can\'t be used, because no unambiguous directory could be identified (because {status})']
            )
            self.log_test_event(result)
            return
        log.debug(f'dst directory {dst} will be used for test {self.name}')

        dir_content = [str(p) for p in Path(dst).iterdir()]
        expected_missing_files = [
            file for file in self.params.files if file not in dir_content
        ]
        additional_files = [
            file for file in dir_content if file not in self.params.files
        ]
        if expected_missing_files:
            details = [f'expected missing files: {expected_missing_files}']
            if additional_files:
                details.append(f'additional files: {additional_files}')
            result = TestResult(
                status=TestFailed(),
                details=details
            )
            self.log_test_event(result)
            return

        result = TestResult(
            status=TestSuccess()
        )
        self.log_test_event(result)
        return


@attrs.define
class FileContentMatchesRegexParameter(Parameter):
    dst: str
    regex: str


@attrs.define
class FileContentMatchesRegex(BasicTest):
    testname: ClassVar[str] = 'file_content_matches_regex'
    testdescription: ClassVar[str] = 'tests if file content matches a given regex expression'

    name: str
    params: FileContentMatchesRegexParameter
    description: Optional[str] = ''

    def test(self):
        dst, status = self.resolve_globfilepath(self.params.dst)
        if not dst:
            result = TestResult(
                status=TestFailed(),
                details=[f'file with path {self.params.dst} can\'t be used, because no unambiguous file could be identified (because {status})']
            )
            self.log_test_event(result)
            return
        log.debug(f'dst file {dst} will be used for test {self.name}')
        try:
            with open(dst, 'r') as f:
                data = f.read()
        except FileNotFoundError:
            result = TestResult(
                status=TestFailed(),
                details=[f'file with path {self.params.dst} does not exist']
            )
            self.log_test_event(result)
            return
        if re.search(self.params.regex, data):
            result = TestResult(
                status=TestSuccess()
            )
        else:
            result = TestResult(
                status=TestFailed(),
                details=['file content does not match regex expression'],
            )
        self.log_test_event(result)
        return


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
    params: CsvContainsLineMatchingRegexParameter
    description: Optional[str] = ''

    def test(self):
        dst, status = self.resolve_globfilepath(self.params.dst)
        if not dst:
            result = TestResult(
                status=TestFailed(),
                details=[f'file with path {self.params.dst} can\'t be used, because no unambiguous file could be identified']
            )
            self.log_test_event(result)
            return

        log.debug(f'dst file {dst} will be used for test {self.name}')
        comparison_list = []
        for entry in self.params.entry:
            if entry is str:
                comparison_list.append(yml.YamlString(entry))
            else:
                comparison_list.append(entry)

        try:
            with open(dst, 'r') as f:
                reader = csv.reader(f)
                for row in reader:
                    if _row_match(row, comparison_list):
                        result = TestResult(
                            status=TestSuccess()
                        )
                        self.log_test_event(result)
                        return
            result = TestResult(
                status=TestFailed(),
                details=[f'entry {self.params.entry} does not exist in file']
            )
            self.log_test_event(result)
            return
        except FileNotFoundError:
            result = TestResult(
                status=TestFailed(),
                details=[f'file with path {self.params.dst} does not exist']
            )
            self.log_test_event(result)
            return
