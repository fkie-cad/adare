# external imports
from pathlib import Path
import json
import dataclasses

# internal imports
from parseandtest.resultformatter.ResultFormatter import ResultFormatter
from parseandtest.tester.classes import TestOutcome

# configure logging
import logging

log = logging.getLogger(__name__)


# todo: test if it works
class JsonResultFormatter(ResultFormatter):
    outcome: TestOutcome = None
    outputpath: str = None

    def __init__(self, outputpath):
        P_outputpath = Path(outputpath)
        if P_outputpath.is_dir():
            if Path(P_outputpath.parent).exists():
                self.outputpath = (P_outputpath.parent / 'result.json').as_posix()
        else:
            self.outputpath = outputpath

    def set_outcome(self, outcome):
        self.outcome = outcome

    def format_result(self) -> str:
        if self.outcome and self.outputpath:
            outcome_dict_list = []
            for result in self.outcome.TestResultList:
                outcome_dict_list.append(dataclasses.asdict(result))
            f = open(self.outputpath, mode="w")
            json.dump(outcome_dict_list, f)
            f.close()
        return self.outputpath
