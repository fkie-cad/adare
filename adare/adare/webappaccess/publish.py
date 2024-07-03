import requests

import adare.config.server as config_server
from adare.webappaccess.request_header import get_authenticated_request_header
from adare.webappaccess.login import WebappLogin
from adare.database.api.experiment import ExperimentApi

# configure logging
import logging
log = logging.getLogger(__name__)


def publish_experiment(experiment_ulid: str) -> bool:
    """
    Publish the experiment to the webapp
    :param experiment_ulid:
    :return:
    """


def publish_run(run_ulid: str) -> bool:
    """
    Publish the experiment to the webapp
    :return: True if successful, False otherwise
    """
    pass


def download_experiment(experiment_ulid: str) -> bool:
    """
    Download the experiment from the webapp
    :param experiment_ulid:
    :return: True if successful, False otherwise
    """
    pass


def download_testfunction(testfunction_ulid: str) -> bool:
    """
    Download the testfunction from the webapp
    :param testfunction_ulid:
    :return: True if successful, False otherwise
    """
    pass


def download_environment(environment_ulid: str) -> bool:
    """
    Download the environment from the webapp
    :param environment_ulid:
    :return: True if successful, False otherwise
    """
    pass





