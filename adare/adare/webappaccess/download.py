import aiohttp
from pathlib import Path
import requests
import adare.config.server as config_server
from adare.webappaccess.exceptions import NotLoggedInError, ExperimentWithNameAlreadyExistsError, DownloadError, MissingDataError
from adare.webappaccess.login import WebappLogin
from adare.helperfunctions.web.download import download_from_session
from adare.database.api.experiment import ExperimentApi

# configure logging
import logging
log = logging.getLogger(__name__)


def __download_json(session: requests.Session, download_url: str, not_found_ignore: bool = False) -> dict:
    with session.get(download_url) as response:
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            if not_found_ignore:
                return dict()
    raise DownloadError(log, f"Error downloading {download_url} ({response.status_code}, {response.text})")


def download_experiment(experiment_ulid: str, location: Path):
    webapp = WebappLogin()
    download_url = f"{config_server.DOWNLOAD_API_URL}experiment_{experiment_ulid}/"
    session = webapp.get_django_session()
    experiment = __download_json(session, download_url)

    metadata_file = experiment.get('metadata_file')
    action_file = experiment.get('action_file')
    testset_file = experiment.get('testset_file')
    if not metadata_file:
        raise MissingDataError(log, f"Experiment {experiment_ulid} has no metadata_file attribute")
    if not action_file:
        raise MissingDataError(log, f"Experiment {experiment_ulid} has no action_file attribute")
    if not testset_file:
        raise MissingDataError(log, f"Experiment {experiment_ulid} has no testset_file attribute")
    # download the files
    session = webapp.get_gitea_session()
    name = experiment.get('name')
    experiment_dir = location / name
    # check if path already exists
    if experiment_dir.exists():
        log.error(f"Experiment {experiment_ulid} already exists in {location}")
        raise ExperimentWithNameAlreadyExistsError(log, f"Experiment {experiment_ulid} already exists in {location}")
    for file in [metadata_file, action_file, testset_file]:
        path = experiment_dir / Path(file).name
        download_from_session(file, path, session)
    return name


def download_testfunction(testfunction_name: str, location: Path):
    webapp = WebappLogin()
    download_url = f"{config_server.DOWNLOAD_API_URL}testfunction_{testfunction_name}/"

    session = webapp.get_django_session()
    testfunction = __download_json(session, download_url)

    testfunction_file = testfunction.get('file')
    requirements_file = testfunction.get('requirements_file')
    if not testfunction_file:
        raise MissingDataError(log, f"Testfunction {testfunction_name} has no file attribute")
    if not requirements_file:
        raise MissingDataError(log, f"Testfunction {testfunction_name} has no requirements_file attribute")
    # download the files
    session = webapp.get_gitea_session()
    for file in [testfunction_file, requirements_file]:
        path = location / Path(file).name
        download_from_session(file, path, session)


def download_environment(environment_name: str, location: Path):
    webapp = WebappLogin()
    download_url = f"{config_server.DOWNLOAD_API_URL}environment_{environment_name}/"
    session = webapp.get_django_session()
    environment = __download_json(session, download_url)
    download_path = environment.get('file')
    if not download_path:
        raise MissingDataError(log, f"Environment {environment_name} has no file attribute")
    # download the file
    session = webapp.get_gitea_session()
    download_from_session(download_path, location, session)


def sync(sha256: str, objective: str):
    webapp = WebappLogin()
    download_url = f"{config_server.HASH_API_URL}{objective}_{sha256}/"
    session = webapp.get_django_session()
    return __download_json(session, download_url, not_found_ignore=True)
