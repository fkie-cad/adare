# internal imports
from parseandtest.tester.testresult import TestOutcome

# configure logging
import logging
log = logging.getLogger(__name__)


class ResultFormatter:
    """
    Base class for result formatters
    """
    outcome: TestOutcome = None
    unsupported_types: list = None

    def set_outcome(self, outcome: TestOutcome):
        """
        setter function for outcome
        :param outcome:
        :return:
        """
        self.outcome = outcome

    def set_unsupported_types(self, unsupported_types):
        """
        setter function for unsupported_types
        :param unsupported_types:
        :return:
        """
        self.unsupported_types = unsupported_types

    def format_result(self):
        """
        format the result of an experiment run to a file
        :return:
        """
        pass
