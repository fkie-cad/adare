# external imports
from pathlib import Path
from typing import Type

# internal imports
from guiautomation.yamlfeatures.basics import yaml_to_dict
from guiautomation.Scenario.Scenario import Scenario

# configure logging
import guiautomation.logger as logger
import logging as log


def setup_logging(logfile: Path = None):
    logger.setup_logger(logfile=logfile, console=False)


def run(scenario_class: Type[Scenario], config_file: Path or None, config_dict: dict = None):
    if not config_dict and not config_file:
        log.error(f'need to provide either config file or config dict')
    if config_file:
        if not config_file.is_file():
            log.error(f'provided config file does not exist')
            return
        gui_config = yaml_to_dict(config_file)
    else:
        gui_config = config_dict

    if 'img_folder' not in gui_config.keys():
        log.error(f'gui config file {config_file} does not contain img_folder attribute')
        return
    if 'tessdata_folder' not in gui_config.keys():
        log.error(f'gui config file {config_file} does not contain tessdata_folder attribute')
        return
    if 'logfile' not in gui_config.keys():
        log.error(f'gui config file {config_file} does not contain logfile attribute')
        return
    if 'statusfile' not in gui_config.keys():
        log.error(f'gui config file {config_file} does not contain statusfile attribute')
        return

    img_folder = Path(gui_config['img_folder'])
    tessdata_folder = Path(gui_config['tessdata_folder'])
    logfile = Path(gui_config['logfile'])
    statusfile = Path(gui_config['statusfile'])

    setup_logging(logfile)

    scenario_log_file = None
    if 'scenario_log_file' in gui_config.keys():
        scenario_log_file = gui_config['scenario_log_file']

    scenario_obj = scenario_class(
        img_folder=img_folder,
        tessdata_folder=tessdata_folder,
        scenario_log_file=scenario_log_file,
    )

    scenario_obj.prepare()
    log.debug(f'preperation of scenario {scenario_obj.__class__} done')
    status = scenario_obj.run()
    log.debug(f'scenario {scenario_obj.__class__} finished')

    with open(statusfile.as_posix(), mode='a', encoding='ascii') as f:
        f.write(f'gui,{status}\n')
