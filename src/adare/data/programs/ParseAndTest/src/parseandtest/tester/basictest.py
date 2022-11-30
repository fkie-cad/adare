# external imports
import glob
from typing import Optional, ClassVar
from attrs import define, asdict
import re

# internal imports
from parseandtest.tester.teststatus import TestStatus
from parseandtest.tester.testresult import TestResult
from parseandtest.yamlfeatures.customtags import YamlCustomTag

# configure logging
import logging
log = logging.getLogger(__name__)


def replace_var_in_match_regex(regex_match, variables):
    key = regex_match.group(1)
    if key in variables.keys():
        return re.escape(variables[key])
    else:
        log.error(f'variable {key} can\'t be replaced because it\'s not present in the variable file')
        return ''


def replace_var_in_match_string(regex_match, variables):
    key = regex_match.group(1)
    if key in variables.keys():
        return variables[key]
    else:
        log.error(f'variable {key} can\'t be replaced because it\'s not present in the variable file')
        return ''


def replace_yamlobj_in_dict(d: dict):
    new_d = dict()
    for key, value in d.items():
        if isinstance(value, YamlCustomTag):
            new_d[key] = value.__repr__()
        elif isinstance(value, dict):
            new_value = replace_yamlobj_in_dict(value)
            new_d[key] = new_value
        elif isinstance(value, list):
            new_value = []
            for v in value:
                if isinstance(v, YamlCustomTag):
                    new_value.append(v.__repr__())
                else:
                    new_value.append(v)
            new_d[key] = new_value
        else:
            new_d[key] = value
    return new_d


@define
class Parameter:
    pass

@define
class BasicTest:
    testname: ClassVar[str] = ''
    testdescription: ClassVar[str] = ''

    name: str
    params: Parameter
    description: Optional[str]

    def set_result(self, testresult: TestStatus, details: list = None):
        if not details:
            details = []
        self.result = TestResult(
            name=self.name,
            function=self.testname,
            function_description=self.testdescription,
            function_options=replace_yamlobj_in_dict(asdict(self.params)),
            description=self.description,
            details=details,
            result=testresult
        )
        return self.result

    def resolve_globfilepath(self, globfilepath: str) -> (str, str):
        found_files = []
        for file in glob.glob(globfilepath):
            found_files.append(file)
        if len(found_files) == 0:
            return "", "no files match the given path (glob) expression"
        elif len(found_files) > 1:
            return "", f"{len(found_files)} files found that match given path (glob) expression"
        else:
            return found_files[0], ""

    def resolve_variable_in_string(self, string: str, variables: dict, regex=False):
        regex_expr = r"{{[ ]*(.*?)[ ]*}}"
        if regex:
            return re.sub(regex_expr, lambda match: replace_var_in_match_regex(match, variables), string)
        return re.sub(regex_expr, lambda match: replace_var_in_match_string(match, variables), string)

    def test(self, variables) -> TestResult:
        pass
