# external imports
from datetime import datetime
import aiohttp
import asyncio
import requests

# internal imports
import adare.config.server as config_server
from adare.database.api.usersession import UserSessionApi
from adare.webappaccess.webapp import check_webserver_availability
from adare.webappaccess.exceptions import NotLoggedInError

# configure logging
import logging

log = logging.getLogger(__name__)


class WebappLogin:

    def __init__(self):
        self.__remove_expired_sessions()

    async def __get_crsf_token(self, req_session: aiohttp.ClientSession):
        try:
            async with req_session.get(config_server.CSRF_URL, timeout=config_server.TIMEOUT_SECONDS) as response:
                csrf = response.cookies['csrftoken'].value
                req_session.headers.update({'X-CSRFToken': csrf})
                log.info(f'CSRF token {csrf} received')
                return csrf
        except asyncio.exceptions.TimeoutError as e:
            log.error("CSRF token request failed due to timeout")
            # close the session to prevent errors
            return None

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

    def get_user_session(self, username=None):
        self.__remove_expired_sessions()
        log.debug(f"Check if user {'' if not username else username} is logged in")
        with UserSessionApi() as user_session_api:
            if not username:
                # if no username is given check for the first user in database
                user_session = user_session_api.get_first_user_session()
            else:
                user_session = user_session_api.get_user_session(username=username)
            if not user_session:
                return None
            else:
                # expunge the user session from the sqlalchemy session to prevent errors
                user_session_api._session.expunge(user_session)
                return {
                    'django_token': user_session.django_token.token,
                    'gitea_token': user_session.gitea_token.token,
                }

    async def login(self, username, password):
        req_session = aiohttp.ClientSession()
        log.debug(f"Login to webapp as user '{username}'")
        if not await check_webserver_availability():
            log.error("Login failed due to webserver is not available")
            await req_session.close()
            return False, 'webserver is not available'

        url = config_server.LOGIN_URL
        if not await self.__get_crsf_token(req_session):
            log.error("Login failed due to CSRF token request failed")
            await req_session.close()
            return False, 'csrf token request failed due to timeout'

        data = {'username': username, 'password': password}
        try:
            async with req_session.post(url, json=data) as response:
                if response.status == 200:
                    self.__add_user_session(username, await response.json())
                    log.debug("Login successful")
                    await req_session.close()
                    return True, ''
                else:
                    log.error("Login failed")
                    await req_session.close()
                    return False, 'login failed due to wrong username or password'
        except aiohttp.ClientConnectionError as e:
            log.error(f"Login failed most likely the server is not running")
            log.debug(e, exc_info=True)
            await req_session.close()
            return False, 'server is not running'

    async def logout(self, username):
        log.debug("Logout from webapp")
        req_session = aiohttp.ClientSession()

        url = config_server.LOGOUT_URL
        user_session = self.get_user_session(username)
        if not user_session:
            log.error(f"user '{username}' is not logged in")
            await req_session.close()
            return False
        header = self.get_django_authenticated_request_header()
        async with req_session.post(url, json={'username': username}, headers=header) as response:
            if response.status == 204:
                log.debug("Logout successful")
                self.__remove_user_session(username)
                await req_session.close()
                return True
            else:
                log.error("Logout failed")
                await req_session.close()
                return False

    def get_django_authenticated_request_header(self):
        user_session = self.get_user_session()
        if not user_session:
            raise NotLoggedInError(log, message='user is not logged in')
        header = {
            'Referer': config_server.WEBSERVER_URL,
            'Authorization': f'Token {user_session["django_token"]}'
        }
        return header

    def get_gitea_authenticated_request_header(self):
        user_session = self.get_user_session()
        if not user_session:
            raise NotLoggedInError(log, message='user is not logged in')
        user_session_token = user_session['gitea_token']
        if not user_session_token:
            return None
        header = {
            'Referer': config_server.WEBSERVER_URL,
            'Authorization': f'token {user_session_token}'
        }
        return header

    def get_django_session(self):
        header = self.get_django_authenticated_request_header()
        session = requests.Session()
        session.headers.update(header)
        return session

    def get_gitea_session(self):
        header = self.get_gitea_authenticated_request_header()
        session = requests.Session()
        session.headers.update(header)
        return session
