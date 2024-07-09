import aiohttp
from pathlib import Path
import requests
import adare.config.server as config_server
from adare.webappaccess.exceptions import NotLoggedInError
from adare.webappaccess.login import WebappLogin
from adarelib.helperfunctions.web.download import download_from_session
from adare.database.api.experiment import ExperimentApi

# configure logging
import logging
log = logging.getLogger(__name__)


def __download_json(session: requests.Session, download_url: str) -> dict:
    """
    Download a json file from the webapp
    :param session:
    :param download_url:
    :return: dict with the json content
    """
    with session.get(download_url) as response:
        if response.status_code == 200:
            return response.json()
        else:
            log.error(f"Error downloading {download_url} ({response.status_code}, {response.text})")
            return dict()


def download_experiment(experiment_ulid: str, location: Path) -> bool:
    webapp = WebappLogin()
    download_url = f"{config_server.DOWNLOAD_API_URL}experiment_{experiment_ulid}/"
    session = webapp.get_django_session()
    experiment = __download_json(session, download_url)
    if experiment:
        metadata_file = experiment.get('metadata_file')
        action_file = experiment.get('action_file')
        testset_file = experiment.get('testset_file')
        if not metadata_file:
            log.error(f"Experiment {experiment_ulid} has no metadata_file attribute")
            return False
        if not action_file:
            log.error(f"Experiment {experiment_ulid} has no action_file attribute")
            return False
        if not testset_file:
            log.error(f"Experiment {experiment_ulid} has no testset_file attribute")
            return False
        # download the files
        session = webapp.get_gitea_session()
        experiment_dir = location / experiment.get('name')
        for file in [metadata_file, action_file, testset_file]:
            path = experiment_dir / Path(file).name
            download_from_session(file, path, session)
        return True
    return False


def download_testfunction(testfunction_name: str, location: Path) -> bool:
    webapp = WebappLogin()
    download_url = f"{config_server.DOWNLOAD_API_URL}testfunction_{testfunction_name}/"

    session = webapp.get_django_session()
    testfunction = __download_json(session, download_url)
    print(testfunction)

    if testfunction:
        testfunction_file = testfunction.get('file')
        requirements_file = testfunction.get('requirements_file')
        if not testfunction_file:
            log.error(f"Testfunction {testfunction_name} has no file attribute")
            return False
        if not requirements_file:
            log.error(f"Testfunction {testfunction_name} has no requirements_file attribute")
            return False
        # download the files
        session = webapp.get_gitea_session()
        for file in [testfunction_file, requirements_file]:
            path = location / Path(file).name
            download_from_session(file, path, session)
        return True
    return False


def download_environment(environment_name: str, location: Path) -> bool:
    webapp = WebappLogin()
    download_url = f"{config_server.DOWNLOAD_API_URL}environment_{environment_name}/"
    session = webapp.get_django_session()
    environment = __download_json(session, download_url)
    if environment:
        download_path = environment.get('file')
        if not download_path:
            log.error(f"Environment {environment_name} has no file attribute")
            return False
        # download the file
        session = webapp.get_gitea_session()
        download_from_session(download_path, location, session)
        return True
    return False
