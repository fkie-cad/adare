# external imports
import sys
import argparse
from pathlib import Path

# internal imports
from parseandtest.tester import Tester
from parseandtest.inputparser import InputParser, YAMLInputParser
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
    InputParser: InputParser = None

    def __init__(self, inputparser, resultdisplay):
        self.Tester = Tester()
        self.InputParser = inputparser
        self.Resultdisplay = resultdisplay

    def parseandtest(self, logfolder: Path):
        self.InputParser.parse()
        self.Tester.set_input(self.InputParser.parsed_input)
        status = self.Tester.test()
        self.Resultdisplay.set_outcome(self.Tester.outcome)
        self.Resultdisplay.set_unsupported_types(self.Tester.unsupported_types)
        self.Resultdisplay.format_result()
        log.error((logfolder/'status.csv').as_posix())
        with open((logfolder/'status.csv').as_posix(), mode='a', encoding='ascii') as f:
            f.write(f'parseandtest,{status}\n')


def run():
    parser = argparse.ArgumentParser()
    parser.set_defaults(func=lambda args: parser.print_help())
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--logfile")

    args = parser.parse_args()

    setup_logging(args, sys.argv)

    path_inputdata = args.input
    path_outputdata = args.output

    if not Path(path_inputdata).is_file():
        log.error(path_inputdata + " is not a valid input file")
        exit(-1)

    if not Path(path_outputdata).parent.is_dir():
        log.error(f'path {Path(path_outputdata).parent} is not existing -> no result file can be placed there')
        exit(-1)

    inputparser = YAMLInputParser.YAMLInputParser(Path(path_inputdata).as_posix())
    resultdisplay = YamlResultFormatter.YamlResultFormatter(Path(path_outputdata).as_posix())

    parseandtest = ParseAndTest(inputparser, resultdisplay)
    parseandtest.parseandtest(Path(args.logfile).parent)
