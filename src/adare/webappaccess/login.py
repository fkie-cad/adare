# external imports
import requests
import json
from datetime import datetime
from pathlib import Path

# internal imports
import adare.config.server as config_server
from adare.database.database import UserSessionApi
from adare.webappaccess.request_header import get_authenticated_request_header

# configure logging
import logging
log = logging.getLogger(__name__)

class WebappLogin:
    login_api_url = config_server.LOGIN_URL
    logout_api_url = config_server.LOGOUT_URL

    def __init__(self):
        self.__remove_expired_sessions()

    def __remove_expired_sessions(self):
        with UserSessionApi() as user_session_api:
            user_session_api.remove_expired_user_sessions()
    def __add_user_session(self, username, response_json):
        token_cookie = response_json['token']
        expiration_date = datetime.strptime(response_json['expiry'], '%Y-%m-%dT%H:%M:%S.%fZ')
        with UserSessionApi() as user_session_api:
            user_session_api.add_user_session(username=username, token=token_cookie, expiration_date=expiration_date)

    def __remove_user_session(self, username):
        with UserSessionApi() as user_session_api:
            user_session_api.remove_user_session(username=username)

    def get_user_session(self, username):
        self.__remove_expired_sessions()
        log.debug(f"Check if user '{username}' is logged in")
        with UserSessionApi() as user_session_api:
            if not username:
                # if no username is given check for the first user in database
                user_session = user_session_api.get_first_user_session()
            else:
                user_session = user_session_api.get_user_session(username=username)
            if not user_session:
                return None
            else:
                user_session_api._session.expunge(user_session)
                return user_session


    def login(self, username, password):
        log.debug(f"Login to webapp as user '{username}'")
        url = self.login_api_url
        payload = {'username': username, 'password': password}
        headers = {'Content-Type': 'application/json'}
        try:
            response = requests.post(url, data=json.dumps(payload), headers=headers)
        except requests.exceptions.ConnectionError as e:
            log.error(f"Login failed most likely the server is not running")
            log.debug(e, exc_info=True)
            return 'connection error'
        if response.status_code == 200:
            self.__add_user_session(username, response.json())
            log.debug("Login successful")
            return 'success'
        else:
            log.error("Login failed")
            return 'failed'

    def logout(self, username):
        log.debug("Logout from webapp")
        url = self.logout_api_url
        token = self.get_user_session(username).token
        if not token:
            log.error(f"user '{username}' is not logged in")
            return False
        header = get_authenticated_request_header(token, config_server.WEBSERVER_URL)
        response = requests.post(url, json={'username': username},headers=header)
        if response.status_code == 204:
            log.debug("Logout successful")
            self.__remove_user_session(username)
            return True
        else:
            log.error("Logout failed")
            return False