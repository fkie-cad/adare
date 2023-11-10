# external imports
import pandas as pd
from attr import define
from pathlib import Path
import re
from typing import ClassVar, Optional

# internal imports
from parseandtest.tester.basictest import BasicTest, Parameter
from parseandtest.tester.testresult import TestResult
from parseandtest.tester.teststatus import TestStatus, TestSuccess, TestError, TestFailed, TestMissingkey, TestInputError
from parseandtest.tester.testdetail import TestDetail, TestDetailList, TestDetailText
import parseandtest.customyaml.customtags as yaml_custom_tags

# configure logging
import logging
log = logging.getLogger(__name__)


@define
class IsFileParameter(Parameter):
    dst: str


@define
class IsFile(BasicTest):
    testname: ClassVar[str] = 'is_file'
    testdescription: ClassVar[str] = 'tests if a file with path destination(dst) is existing'

    name: str
    params: IsFileParameter
    description: Optional[str] = ''
    result: Optional[TestResult] = None

    def test(self, variables) -> TestResult:
        if Path(self.params.dst).is_file():
            result = TestSuccess()
        else:
            result = TestFailed()
        self.result = TestResult(
            name=self.name,
            function=self.testname,
            function_description=self.testdescription,
            result=result,
        )
        return self.result


@define
class IsNotFileParameter(Parameter):
    dst: str


@define
class IsNotFile(BasicTest):
    testname: ClassVar[str] = 'is_not_file'
    testdescription: ClassVar[str] = 'tests if a file with path destination(dst) is NOT existing'

    name: str
    params: IsNotFileParameter
    description: Optional[str] = ''
    result: Optional[TestResult] = None

    def test(self, variables) -> TestResult:
        if not Path(self.params.dst).is_file():
            result = TestSuccess()
        else:
            result = TestFailed()
        return self.set_result(result)


@define
class IsDirParameter(Parameter):
    dst: str


@define
class IsDir(BasicTest):
    testname: ClassVar[str] = 'is_dir'
    testdescription: ClassVar[str] = 'tests if a directory with path destination(dst) is existing'

    name: str
    params: IsDirParameter
    description: Optional[str] = ''
    result: Optional[TestResult] = None

    def test(self, variables) -> TestResult:
        if Path(self.params.dst).is_dir():
            result = TestSuccess()
        else:
            result = TestFailed()
        return self.set_result(result)

@define
class IsNotDirParameter(Parameter):
    dst: str


@define
class IsNotDir(BasicTest):
    testname: ClassVar[str] = 'is_not_dir'
    testdescription: ClassVar[str] = 'tests if a directory with path destination(dst) is NOT existing'

    name: str
    params: IsNotDirParameter
    description: Optional[str] = ''
    result: Optional[TestResult] = None

    def test(self, variables) -> TestResult:
        if not Path(self.params.dst).is_dir():
            result = TestSuccess()
        else:
            result = TestFailed()
        return self.set_result(result)


@define
class DirContentParameter(Parameter):
    dst: str
    expected: list


@define
class DirContent(BasicTest):
    testname: ClassVar[str] = 'dir_content'
    testdescription: ClassVar[str] = 'tests if a directory has the expected files/folders'

    name: str
    params: DirContentParameter
    description: Optional[str] = ''
    result: Optional[TestResult] = None

    def test(self, variables) -> TestResult:
        details = []
        if not Path(self.params.dst).is_dir():
            details += TestDetailText(name='reason for failure', data=f'directory {self.params.dst} does not exist')
            testresult = TestFailed()
            return self.set_result(testresult, details=details)

        files_in_dst = [f.name for f in Path(self.params.dst).iterdir()]
        details.append(TestDetailList(name='expected files/directorys', data=self.params.files))
        details.append(TestDetailList(name='found files/directorys', data=files_in_dst))
        if files_in_dst == self.params.files:
            testresult = TestSuccess()
            return self.set_result(testresult, details=details)
        else:
            testresult = TestFailed()
            return self.set_result(testresult, details=details)


@define
class RegexMatchParameter(Parameter):
    dst: str
    regex: str


@define
class RegexMatch(BasicTest):
    testname: ClassVar[str] = 'regex_match'
    testdescription: ClassVar[str] = 'tests if file content matches a given regex expression'

    name: str
    params: RegexMatchParameter
    description: Optional[str] = ''
    result: Optional[TestResult] = None

    def test(self, variables) -> TestResult:
        details = []
        try:
            f = open(self.params.dst, mode="rb")
            data = f.read().decode("utf-8")
            f.close()
        except FileNotFoundError:
            testresult = TestFailed()
            details.append(TestDetailText(name='info', data=f'file with path {self.params.dst} is not existing'))
            return self.set_result(testresult, details=details)

        try:
            pattern = re.compile(self.params.regex)
        except re.error:
            testresult = TestInputError()
            details.append(TestDetailText(name='info', data=f'given regular expression could not be compiled ({self.params.regex})'))
            return self.set_result(testresult, details=details)

        match = pattern.match(data)
        if match and match.span()[1] == len(data):
            testresult = TestSuccess()
        else:
            testresult = TestFailed()
        return self.set_result(testresult, details=details)

@define
class CsvEntryExistsParameter(Parameter):
    dst: str
    entry: list


@define
class CsvEntryExists(BasicTest):
    testname: ClassVar[str] = 'csv_entry_exists'
    testdescription: ClassVar[str] = 'tests if row in a given csv file (dst) exists, which matches the given layout provided (entry)'

    name: str
    params: CsvEntryExistsParameter
    description: Optional[str] = ''
    result: Optional[TestResult] = None

    def test(self, variables: dict) -> TestResult:
        details = []
        dst, status = self.resolve_globfilepath(self.params.dst)
        if not dst:
            testresult = TestFailed()
            details.append(TestDetailText(name='info', data=f'file with path {self.params.dst} can\'t be used, because no unambiguous file could be identified (because {status})'))
            return self.set_result(testresult, details=details)
        log.debug(f'dst file {dst} will be used for test {self.name}')
        csv_content = pd.read_csv(dst)
        comparison_list = []
        for entry in self.params.entry:
            if type(entry) == str:
                comparison_list.append(yaml_custom_tags.YamlString(entry))
            else:
                comparison_list.append(entry)

        matching_rows = []
        for index, row in csv_content.iterrows():
            match_found = True
            for item_index, item in enumerate(row.items()):
                match = False
                comparison_element = comparison_list[item_index]
                if type(comparison_element) in yaml_custom_tags.YAML_CUSTOM_TAGS:
                    match = comparison_element.compare(item[1])
                else:
                    if comparison_element == item[1]:
                        match = True
                if not match:
                    match_found = False
                    break
            if match_found:
                matching_rows.append(list(row))
        if not matching_rows:
            testresult = TestFailed()
            return self.set_result(testresult, details=details)
        else:
            details.append(TestDetailList(name='matching rows', data=matching_rows))
            testresult = TestSuccess()
            return self.set_result(testresult, details=details)

