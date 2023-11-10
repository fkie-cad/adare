# external imports
from pathlib import Path
import attr

# internal imports
from parseandtest.resultformatter.ResultFormatter import ResultFormatter
from parseandtest.helperfunctions.yaml import dict_to_yaml

# configure logging
import logging
log = logging.getLogger(__name__)


class YamlResultFormatter(ResultFormatter):
    """
    format the result of an experiment run to a yaml file
    """
    result_path: Path = None

    def __init__(self, result_path: Path):
        if result_path.is_dir():
            if result_path.parent.exists():
                self.result_path = (result_path.parent / 'result.yml')
        else:
            self.result_path = result_path

    def format_result(self):
        """
        format the result of an experiment run to a yaml file
        :return:
        """
        if self.outcome and self.result_path:
            outcome_dict_list = []
            for result in self.outcome.TestResultList:
                outcome_dict_list.append(attr.asdict(result))
            dict_to_yaml(self.result_path, outcome_dict_list)
