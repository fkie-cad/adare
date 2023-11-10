# external imports
import sys
import argparse
from pathlib import Path

# internal imports
from parseandtest.tester import Tester
from parseandtest.parser.TestsetFileParser import TestsetFileParser
from parseandtest.resultformatter import ResultFormatter, YamlResultFormatter
import parseandtest.config as config

# logging configuration
from parseandtest.logger import logger
import logging as log


def setup_logging(arguments, commandline):
    if arguments.logfile:
        logger.setup_logger(logfile=arguments.logfile)
    else:
        logger.setup_logger(logfile=config.DEFAULTLOGFILE)
    log.info(f'COMMAND: {" ".join(commandline)}')


class ParseAndTest:
    Tester: Tester = None
    Resultdisplay: ResultFormatter = None
    testsetfile_parser: TestsetFileParser = None

    def __init__(self, testsetfile_parser, resultdisplay):
        self.Tester = Tester()
        self.testsetfile_parser = testsetfile_parser
        self.Resultdisplay = resultdisplay

    def parseandtest(self, statusfile: Path):
        parsed_testset_data = self.testsetfile_parser.parse()
        self.Tester.set_input(parsed_testset_data)
        status = self.Tester.test()
        self.Resultdisplay.set_outcome(self.Tester.outcome)
        self.Resultdisplay.set_unsupported_types(self.Tester.unsupported_types)
        self.Resultdisplay.format_result()
        log.debug(f'status file: {statusfile}')
        with open(statusfile.as_posix(), mode='a', encoding='ascii') as f:
            f.write(f'parseandtest,{status}\n')


def run():
    parser = argparse.ArgumentParser()
    parser.set_defaults(func=lambda args: parser.print_help())
    parser.add_argument("testsetfile")
    parser.add_argument("output")
    parser.add_argument("statusfile")
    parser.add_argument("--logfile")

    args = parser.parse_args()

    setup_logging(args, sys.argv)

    testsetfile = Path(args.testsetfile)
    resultfile = Path(args.output)
    statusfile = Path(args.statusfile)

    if not testsetfile.is_file():
        log.error(f"{testsetfile} is not a valid input file")
        exit(-1)

    if not resultfile.parent.is_dir():
        log.error(f'path {resultfile.parent} is not existing -> no result file can be placed there')
        exit(-1)

    if not statusfile.parent.is_dir():
        log.error(f'path {statusfile.parent} is not existing -> no status file can be placed there')
        exit(-1)

    testset_file_parser = TestsetFileParser(testsetfile)
    resultdisplay = YamlResultFormatter.YamlResultFormatter(resultfile.as_posix())

    parseandtest = ParseAndTest(testset_file_parser, resultdisplay)
    parseandtest.parseandtest(statusfile)
