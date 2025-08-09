from adare.console import console
from adare.helperfunctions.text import clean_rich_inline_str

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
                print_string = ' ' * prefix_whitespace_count + f'([b][cyan]{index + 1}[/cyan][/b]) {mitigation}'
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
    def __init__(self, log: logging.Logger, message: str = None, specified_project: str = None, 
                 current_path: "Path" = None, possible_solutions: list = None):
        """
        Enhanced NoProjectFoundError with context-aware suggestions.
        
        Args:
            log: Logger instance
            message: Custom error message (auto-generated if None)
            specified_project: Project name that was specified
            current_path: Current working directory
            possible_solutions: Custom solutions (auto-generated if None)
        """
        if message is None or possible_solutions is None:
            from pathlib import Path
            from adare.helperfunctions.project_suggestions import generate_no_project_error_message
            
            if current_path is None:
                current_path = Path.cwd()
            
            auto_message, auto_solutions = generate_no_project_error_message(
                current_path=current_path,
                specified_project=specified_project
            )
            
            if message is None:
                message = auto_message
            if possible_solutions is None:
                possible_solutions = auto_solutions
        
        super().__init__(log, message, possible_solutions=possible_solutions)


class EnvironmentNotFoundError(LoggedErrorException):
    pass


class ProjectNotFoundError(LoggedErrorException):
    pass


class ExperimentNotFoundError(LoggedErrorException):
    pass


class ArgumentsError(LoggedErrorException):
    pass


class TestFunctionNotFoundError(LoggedErrorException):
    pass

class EnvironmentVMNotFoundError(LoggedErrorException):
    pass

class NotLoggedInError(LoggedErrorException):
    def __init__(self, log):
        super().__init__(log, 'User is not logged in', possible_solutions=[
            'Please login using the command `adare web login`'
        ])


class RunNotFoundError(LoggedErrorException):
    def __init__(self, log, run_ulid):
        super().__init__(log, f'Experiment run "{run_ulid}" not found', possible_solutions=[
            'Use `adare show runs` to list available experiment runs',
            'Check if the run ULID is correct',
            'Make sure the experiment run was completed successfully'
        ])
