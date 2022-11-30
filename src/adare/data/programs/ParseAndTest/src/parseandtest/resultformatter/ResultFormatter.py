from parseandtest.tester.testresult import TestOutcome


class ResultFormatter:
    outcome: TestOutcome = None
    unsupported_types: list = None

    def set_outcome(self, outcome):
        self.outcome = outcome

    def set_unsupported_types(self, unsupported_types):
        self.unsupported_types = unsupported_types

    def format_result(self):
        pass
