import json
from pathlib import Path
import requests
import adare.config.server as config_server
from adare.webappaccess.exceptions import NotLoggedInError, ExperimentPublishFailedError
from adare.webappaccess.login import WebappLogin, is_logged_in
from adarelib.helperfunctions.web.download import download_from_session
from adare.database.api.serialize import SerializeApi

# configure logging
import logging
log = logging.getLogger(__name__)


def files_to_request_files(files: dict) -> dict:
    request_files = {}
    for name, path in files.items():
        if not Path(path).exists():
            log.warning(f'File {path} does not exist.')
            continue
        file_bytes = Path(path).read_bytes()
        request_files[name] = (Path(path).name, file_bytes, 'text/plain')
    return request_files


def publish_experiment_run(run_ulid: str):
    if not is_logged_in():
        raise NotLoggedInError(log, 'You are not logged in. Please log in first.')
    with SerializeApi() as api:
        data, files = api.serialize_run_by_ulid(run_ulid)

    files = files_to_request_files(files)

    url = config_server.PUBLISH_RUN_URL
    header = WebappLogin().get_django_authenticated_request_header()

    response = requests.post(url, headers=header, data={'metadata': json.dumps(data)}, files=files)

    if response.status_code != 200:
        raise ExperimentPublishFailedError(log, f'Publishing experiment run failed with status code {response.status_code} and message {response.text}')

    log.info(f'experiment run ({run_ulid}) published successfully.')
    print(f'experiment run ({run_ulid}) published successfully!')