# external imports
from pathlib import Path
import attr

# internal imports
from parseandtest.resultformatter.ResultFormatter import ResultFormatter
from parseandtest.yamlfeatures.basics import dict_to_yaml

# configure logging
import logging

log = logging.getLogger(__name__)


class YamlResultFormatter(ResultFormatter):
    outputpath: str = None

    def __init__(self, outputpath):
        P_outputpath = Path(outputpath)
        if P_outputpath.is_dir():
            if Path(P_outputpath.parent).exists():
                self.outputpath = (P_outputpath.parent / 'result.yml').as_posix()
        else:
            self.outputpath = outputpath

    def format_result(self):
        if self.outcome and self.outputpath:
            outcome_dict_list = []
            for result in self.outcome.TestResultList:
                outcome_dict_list.append(attr.asdict(result))
            dict_to_yaml(self.outputpath, outcome_dict_list)
