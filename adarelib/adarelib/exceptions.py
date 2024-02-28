from adarelib.console import console
from adarelib.helperfunctions.text import clean_rich_inline_str

# configure logging
import logging


class LoggedException(Exception):
    log: logging.Logger
    rich_message: str

    def __init__(self, log: logging.Logger, message: str, level: str = 'info'):
        self.log = log
        self.rich_message = message
        self.message = clean_rich_inline_str(message)
        if level == 'critical':
            self.log.critical(self.message)
        elif level == 'debug':
            self.log.debug(self.message)
        elif level == 'error':
            self.log.error(self.message)
        elif level == 'info':
            self.log.info(self.message)
        elif level == 'warning':
            self.log.warning(self.message)
        super().__init__(self.message)

    def print(self):
        console.print(self.rich_message, highlight=False)


class LoggedErrorException(LoggedException):
    error_name: str
    error_mitigation: list

    def __init__(self, log: logging.Logger, message: str, possible_solutions: list = None, critical=False):
        super().__init__(log, message, 'critical' if critical else 'error')
        self.error_name = self.__class__.__name__
        self.possible_solutions = possible_solutions

    def print(self):
        console.print()
        console.print(f'{self.error_name}:', highlight=False, style='underline bold')
        console.print(f'{self.message}', highlight=False)
        if self.possible_solutions:
            console.print('\nPossible Solutions:', highlight=False, style='')
            prefix_whitespace_count = 3
            for index, mitigation in enumerate(self.possible_solutions):
                print_string = ' '*prefix_whitespace_count + f'([b][cyan]{index+1}[/cyan][/b]) {mitigation}'
                console.print(print_string, highlight=False)
        console.print()



class DataStructuringError(LoggedErrorException):

    pass


class TestSetFormatError(LoggedErrorException):

    pass


class TemplateMissingError(LoggedErrorException):
    pass


class TestfunctionParameterClassMissingError(LoggedErrorException):
    pass


class TestfunctionSyntaxError(LoggedErrorException):
    pass


class NoProjectFoundError(LoggedErrorException):
    def __init__(self, log: logging.Logger):
        super().__init__(log, 'no project directory found')
