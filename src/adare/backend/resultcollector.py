# external imports
from pathlib import Path

# internal imports
from adare.database.django_db_api import DjangoDbApi
from adare.helperFunctions.yaml.basics import yaml_to_dict

# configure logging
import logging
log = logging.getLogger(__name__)


class ResultCollector:
    """
    class to collect results and additional information of an experiment and save it in the database
    """
    input_file: Path
    log_directory: Path
    result_file: Path
    environment_configuration: dict

    LOGFILE_MAPPING = {
        'logfile_vagrant': 'vagrant.log',
        'logfile_parse_and_test': 'parseandtest.log',
        'logfile_gui_automation': 'gui.log'
    }
    STATUS_CODE_NAME_MAPPING = {
        'default': 'failed',
        0: 'success'
    }

    def __init__(self, input_file: Path, log_directory: Path, result_file: Path, environment_configuration: dict):
        self.input_file = input_file
        self.log_directory = log_directory
        self.result_file = result_file

    def __get_status_by_status_code(self, code: int):
        if code in self.STATUS_CODE_NAME_MAPPING.keys():
            return self.STATUS_CODE_NAME_MAPPING[code]
        else:
            return self.STATUS_CODE_NAME_MAPPING['default']

    def collect(self, timestamps: dict, status_code_vagrant: int, ):
        db_api = DjangoDbApi()

        input_data = yaml_to_dict(self.input_file)
        result_data = yaml_to_dict(self.result_file)

        logfile_information = dict()
        for log_name, log_filename in self.LOGFILE_MAPPING.items():
            logfile_information[log_name] = (self.log_directory/log_filename).absolute().as_posix()

        status_information = {
            'status_vagrant': self.__get_status_by_status_code(status_code_vagrant)
        }

        db_api.add_experiment(inputdata=input_data, resultdata=result_data, logfiledata=logfile_information, timestamps=timestamps)

