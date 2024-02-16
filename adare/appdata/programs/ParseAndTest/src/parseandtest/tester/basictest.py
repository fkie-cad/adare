# external imports
import glob
from typing import Optional, ClassVar
from attrs import define, asdict
import re

# internal imports
from parseandtest.tester.teststatus import TestStatus
from parseandtest.tester.testresult import TestResult
from parseandtest.customyaml.customtags import YamlCustomTag

# configure logging
import logging
log = logging.getLogger(__name__)


def resolve_var_in_match_regex(regex_match, variables):
    """
    resolve the variable in a regex match (which is a regex expression)
    :param regex_match: regex match object
    :param variables: dict with variables
    :return:
    """
    key = regex_match.group(1)
    if key in variables.keys():
        return re.escape(variables[key])
    else:
        log.error(f'variable {key} can\'t be replaced because it\'s not present in the variable file')
        return ''


def resolve_var_in_match_string(regex_match, variables):
    """
    resolve the variable in a regex match (which is a simple string)
    :param regex_match: regex match object
    :param variables: dict with variables
    :return:
    """
    key = regex_match.group(1)
    if key in variables.keys():
        return variables[key]
    else:
        log.error(f'variable {key} can\'t be replaced because it\'s not present in the variable file')
        return ''


def resolve_yamlobj_in_dict(dictionary: dict):
    """
    resolve all YamlCustomTag objects in a dict with their __repr__ value
    :param dictionary: dict to replace YamlCustomTag objects in
    :return:
    """
    new_d = dict()
    for key, value in dictionary.items():
        if isinstance(value, YamlCustomTag):
            new_d[key] = value.__repr__()
        elif isinstance(value, dict):
            new_value = resolve_yamlobj_in_dict(value)
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
    """
    Parameter is the base class for all test parameters.
    """
    pass

@define
class BasicTest:
    """
    BasicTest is the base class for all tests. It provides basic functionality like setting the result of a test.
    """
    testname: ClassVar[str] = ''
    testdescription: ClassVar[str] = ''

    name: str
    params: Parameter
    description: Optional[str]

    def set_result(self, status: TestStatus, details: list = None):
        """
        Sets the result of the test and returns it.
        :param status: TestStatus
        :param details:
        :return:
        """
        if not details:
            details = []
        self.result = TestResult(
            name=self.name,
            function=self.testname,
            function_description=self.testdescription,
            function_options=resolve_yamlobj_in_dict(asdict(self.params)),
            description=self.description,
            details=details,
            result=status
        )
        return self.result

    def resolve_globfilepath(self, globfilepath: str) -> (str, str):
        """
        find a file that matches the given glob expression and return it. If no file is found or more than one file is
        found, return an error message.
        :param globfilepath: glob expression to find a file
        :return: (filepath, error message)
        """
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
        """
        replace a variable in a string (e.g. test{VARIABLE} with VARIABLE=value -> testvalue)
        :param string: string to replace variables in
        :param variables: dict with variables
        :param regex: boolean if string is a regex expression
        :return:
        """
        regex_expr = r"{{[ ]*(.*?)[ ]*}}"
        if regex:
            return re.sub(regex_expr, lambda match: resolve_var_in_match_regex(match, variables), string)
        return re.sub(regex_expr, lambda match: resolve_var_in_match_string(match, variables), string)

    def test(self, variables: dict) -> TestResult:
        """
        This method has to be implemented by all subclasses. It should return a TestResult object.
        :param variables: dict with variables
        :return:
        """
        pass
