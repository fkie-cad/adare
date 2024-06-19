import requests
import ulid

import adare.config.server as config_server
from adare.webappaccess.request_header import get_authenticated_request_header
from adare.webappaccess.login import WebappLogin
from adare.database.api.experiment import ExperimentApi

# configure logging
import logging
log = logging.getLogger(__name__)



class WebappPublishExperiment:
    publish_experiment_api_url = config_server.ADD_EXPERIMENT_URL

    def publish(self, username: str, experiment_ulid: str) -> str:
        """
        Publish the experiment to the webapp
        :return: True if successful, False otherwise
        """
        # check is user is logged in
        webapp_login = WebappLogin()
        user_session = webapp_login.get_user_session(username)
        if not user_session:
            log.error(f'User {username} is not logged in. Can not publish experiment {experiment_ulid} to webapp')
            return 'login missing'

        with ExperimentApi() as experiment_api:
            exp = experiment_api.get_experiment_by_ulid(experiment_ulid)
            data = exp.to_dict()
            log.debug(f'Publishing experiment {experiment_ulid} to webapp with data: {data}')

        headers = get_authenticated_request_header(user_session.token, config_server.WEBSERVER_URL)
        try:
            response = requests.post(self.publish_experiment_api_url, json=data, headers=headers)
        except requests.exceptions.ConnectionError as e:
            log.error(f'Could not connect to webapp')
            return 'connection error'
        if response.status_code == 200:
            return 'success'
        else:
            if response.status_code == 400 and f'{experiment_ulid} does already exist' in response.text:
                log.error(f'Experiment {experiment_ulid} is already published to webapp')
                return 'already published'
            log.error(f'Could not publish experiment {experiment_ulid} to webapp. Response({response.status_code}): {response.text}')
            return 'failed'


# def send_experiment_request():
#     request = {
#         "ulid": ulid.ULID(),
#     }