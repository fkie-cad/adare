# external imports
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import datetime
import pkg_resources

# internal imports
from . import ResultFormatter
from parseandtest.tester.classes import TestOutcome

# configure logging
import logging
log = logging.getLogger(__name__)


class HtmlResultFormatter(ResultFormatter.ResultFormatter):
    outcome: TestOutcome = None
    outputpath: str = None

    def __init__(self, outputpath):
        P_outputpath = Path(outputpath)
        if P_outputpath.is_dir():
            if Path(P_outputpath.parent).exists():
                self.outputpath = (P_outputpath.parent/'result.html').as_posix()
        else:
            self.outputpath = outputpath

    def set_outcome(self, outcome):
        self.outcome = outcome

    def format_result(self) -> str:
        now = datetime.utcnow()
        dateandtime = now.strftime('%Y-%m-%d %H:%M:%S')
        directory = pkg_resources.resource_filename('parseandtest.resultformatter', 'templates')
        outcome = self.outcome
        env = Environment(
            loader=FileSystemLoader(directory),
            autoescape=select_autoescape()
        )
        template = env.get_template("template.html")
        with open(self.outputpath, 'w') as fh:
            fh.write(template.render(
                title="experiment results",
                date=dateandtime,
                outcome=outcome.TestResultList
            ))
        return self.outputpath
