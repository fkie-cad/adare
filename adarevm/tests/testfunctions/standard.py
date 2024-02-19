# external imports
from datetime import datetime, timedelta, timezone
import pandas as pd
import attrs
from pathlib import Path
import datefinder
import csv
import re
from typing import ClassVar, Optional

# internal imports
from adarevm.testset.basictest import BasicTest, Parameter
from adarevm.testset.teststatus import TestStatus, TestSuccess, TestError, TestFailed, TestMissingKey, TestSyntaxError
import adarelib.helperfunctions as helper
from adarevm.event import TestEnd
import adarelib.customyaml.customtags as yml
from adarevm import VARIABLES

# configure logging
import logging

log = logging.getLogger(__name__)


@attrs.define
class IsFileParameter(Parameter):
    dst: str


@attrs.define
class IsFile(BasicTest):
    testname: ClassVar[str] = 'is_file'
    testdescription: ClassVar[str] = 'tests if a file with path destination(dst)  is existing'

    name: str
    params: IsFileParameter
    description: Optional[str] = ''

    def test(self):
        if Path(self.params.dst).is_file():
            event = TestEnd(
                test_name=self.name,
                status=TestSuccess()
            )
        else:
            event = TestEnd(
                test_name=self.name,
                status=TestFailed(),
                details=[f'file with path {self.params.dst} does not exist']
            )
        self.eventsystem.log(event)


@attrs.define
class IsNotFileParameter(Parameter):
    dst: str


@attrs.define
class IsNotFile(BasicTest):
    testname: ClassVar[str] = 'is_not_file'
    testdescription: ClassVar[str] = 'tests if a file with path destination(dst) is NOT existing'

    name: str
    params: IsNotFileParameter
    description: Optional[str] = ''

    def test(self):
        if not Path(self.params.dst).is_file():
            event = TestEnd(
                test_name=self.name,
                status=TestSuccess()
            )
        else:
            event = TestEnd(
                test_name=self.name,
                status=TestFailed(),
                details=[f'file with path {self.params.dst} does exist']
            )
        return [event]


@attrs.define
class IsDirParameter(Parameter):
    dst: str


@attrs.define
class IsDir(BasicTest):
    testname: ClassVar[str] = 'is_dir'
    testdescription: ClassVar[str] = 'tests if a directory with path destination(dst) is existing'

    name: str
    params: IsDirParameter
    description: Optional[str] = ''

    def test(self):
        if Path(self.params.dst).is_dir():
            event = TestEnd(
                test_name=self.name,
                status=TestSuccess()
            )
        else:
            event = TestEnd(
                test_name=self.name,
                status=TestFailed(),
                details=[f'directory with path {self.params.dst} does not exist']
            )
        return [event]


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
            event = TestEnd(
                test_name=self.name,
                status=TestFailed(),
                details=[
                    f'directory with path {self.params.dst} can\'t be used, because no unambiguous directory could be identified (because {status})']
            )
            return [event]
        log.debug(f'dst directory {dst} will be used for test {self.name}')
        dir_content = [str(p) for p in Path(dst).iterdir()]
        if len(dir_content) != len(self.params.files):
            event = TestEnd(
                test_name=self.name,
                status=TestFailed(),
                details=[f'expected {len(self.params.files)} files/folders, but found {len(dir_content)}']
            )
            return [event]
        for file in self.params.files:
            if file not in dir_content:
                event = TestEnd(
                    test_name=self.name,
                    status=TestFailed(),
                    details=[f'file/folder {file} is missing']
                )
                return [event]
        event = TestEnd(
            test_name=self.name,
            status=TestSuccess()
        )
        return [event]


@attrs.define
class RegexMatchParameter(Parameter):
    dst: str
    regex: str


@attrs.define
class RegexMatch(BasicTest):
    testname: ClassVar[str] = 'regex_match'
    testdescription: ClassVar[str] = 'tests if file content matches a given regex expression'

    name: str
    params: RegexMatchParameter
    description: Optional[str] = ''

    def test(self):
        dst, status = self.resolve_globfilepath(self.params.dst)
        if not dst:
            event = TestEnd(
                test_name=self.name,
                status=TestFailed(),
                details=[
                    f'file with path {self.params.dst} can\'t be used, because no unambiguous file could be identified (because {status})']
            )
            return [event]
        log.debug(f'dst file {dst} will be used for test {self.name}')
        try:
            with open(dst, 'r') as f:
                data = f.read()
        except FileNotFoundError:
            event = TestEnd(
                test_name=self.name,
                status=TestFailed(),
                details=[f'file with path {self.params.dst} does not exist']
            )
            return [event]
        if re.search(self.params.regex, data):
            event = TestEnd(
                test_name=self.name,
                status=TestSuccess()
            )
        else:
            event = TestEnd(
                test_name=self.name,
                status=TestFailed(),
                details=[f'file content does not match regex {self.params.regex}']
            )
        return [event]


@attrs.define
class CheckTimestampParameter(Parameter):
    dst: str
    tolerance: int
    timestamp_name: str
    timestamp_format: Optional[str] = None


#
# @define
# class CheckTimestamp(BasicTest):
#     testname: ClassVar[str] = 'check_timestamp'
#     testdescription: ClassVar[str] = 'tests if a timestamp in a file can be found, which is identical to timestamp stored by the gui experiment'
#
#     name: str
#     params: CheckTimestampParameter
#     description: Optional[str] = ''
#     result: Optional[TestResult] = None
#
#     def test(self, variables: dict) -> TestResult:
#         details = dict()
#         try:
#             f = open(self.params.dst, mode="rb")
#             data = f.read().decode("utf-8")
#             f.close()
#         except FileNotFoundError:
#             testresult = TestFailed()
#             details['info'] = f'file with path {self.params.dst} is not existing'
#             return self.set_result(testresult, details=details)
#
#         timestamp_varname = f'TIMESTAMP.{self.params.timestamp_name}'
#         if timestamp_varname not in variables.keys():
#             testresult = TestFailed()
#             details['info'] = f'timestamp variable with name {timestamp_varname} could NOT be found in the saved variables'
#             return self.set_result(testresult, details=details)
#         if not self.params.timestamp_format:
#             saved_timestamp = datetime.strptime(variables[timestamp_varname],
#
#         LOCAL_TIMEZONE = datetime.now(timezone.utc).astimezone().tzinfo
#         found_dates = []
#         for date in datefinder.find_dates(data):
#             date = date.replace(tzinfo=LOCAL_TIMEZONE)
#             found_dates.append(date)
#
#         date_from_tmpfile = datetime.strptime(matching_dates[0], )
#         for date in found_dates:
#             if abs(date - date_from_tmpfile) < timedelta(seconds=self.params.tolerance):
#                 matching_date_found = True
#                 matching_dates.append(date.isoformat())
#
#         details['timestamp from gui event'] = date_from_tmpfile.isoformat()
#         details['found dates in file'] = ','.join([d.isoformat() for d in found_dates])
#         if matching_date_found:
#             testresult = TestSuccess()
#             details['matching timestamps'] = ','.join(matching_dates)
#         else:
#             testresult = TestFailed()
#         return self.set_result(testresult, details=details)


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
class CsvEntryExistsParameter(Parameter):
    dst: str
    entry: list


@attrs.define
class CsvEntryExists(BasicTest):
    testname: ClassVar[str] = 'csv_entry_exists'
    testdescription: ClassVar[str] = 'tests if row in a csv file exists that matches the given entry layout'

    name: str
    params: CsvEntryExistsParameter
    description: Optional[str] = ''

    def test(self):
        dst, status = self.resolve_globfilepath(self.params.dst)
        if not dst:
            event = TestEnd(
                test_name=self.name,
                status=TestFailed(),
                details=[
                    f'file with path {self.params.dst} can\'t be used, because no unambiguous file could be identified (because {status})']
            )
            return [event]
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
                        event = TestEnd(
                            test_name=self.name,
                            status=TestSuccess()
                        )
                        return [event]
            event = TestEnd(
                test_name=self.name,
                status=TestFailed(),
                details=[f'entry {self.params.entry} does not exist in file']
            )
            return [event]
        except FileNotFoundError:
            event = TestEnd(
                test_name=self.name,
                status=TestFailed(),
                details=[f'file with path {self.params.dst} does not exist']
            )
            return [event]
