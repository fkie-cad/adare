# external imports
import argparse
from importlib import import_module
import sys
from pkgutil import iter_modules
from inspect import isclass
import pkg_resources

# internal imports
import guiautomation.config as config
from guiautomation.Scenario.Scenario import Scenario

# configure logging
import guiautomation.logger as logger
import logging as log


def setup_logging(arguments, commandline):
    if arguments.logfile:
        logger.setup_logger(logfile=arguments.logfile)
    else:
        logger.setup_logger(logfile=config.DEFAULTLOGFILE)
    log.info("COMMAND: " + " ".join(commandline))


def import_scenario(scenarioname):
    scenario_class = None
    package_dir = pkg_resources.resource_filename('guiautomation.Scenario', '')
    for (_, module_name, _) in iter_modules([package_dir]):
        module = import_module(f"guiautomation.Scenario.{module_name}")
        for attribute_name in dir(module):
            attribute = getattr(module, attribute_name)
            if isclass(attribute) and issubclass(attribute, Scenario):
                globals()[attribute_name] = attribute
                if attribute_name == scenarioname:
                    scenario_class = attribute
    return scenario_class


def run_scenario(arguments):
    log.info(f'scenario {arguments.scenarioname} will be run')
    scenarioclass = import_scenario(arguments.scenarioname)
    log.info(f'scenario class for scenario {arguments.scenarioname} was imported successfully')
    if not scenarioclass:
        log.error(f'no scenario class for scenario {arguments.scenarioname} found')
        return
    ScenarioObj = scenarioclass()
    ScenarioObj.prepare()
    ScenarioObj.run()
    log.info(f'scenario {arguments.scenarioname} is run successfully')


def run():
    parser = argparse.ArgumentParser(description="")
    parser.add_argument("--logfile")
    subparsers = parser.add_subparsers()

    subparser_run = subparsers.add_parser('run', help='run a chosen scenario')
    subparser_run.add_argument('scenarioname', type=str, help='name of the scenario \n to list all available scenarios run the list command')
    subparser_run.set_defaults(func=run_scenario)

    args = parser.parse_args()

    setup_logging(args, sys.argv)

    args.func(args)

