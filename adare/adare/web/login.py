import base64
import hashlib
import os
import requests
import http.server
import urllib.parse
from urllib.parse import parse_qs, urlparse
import secrets
import datetime
import webbrowser

from adare.helperfunctions.port import is_localhost_port_free
from adare.config.server import GITEA_URL, GITEA_CLIENT_ID, PORT_OAUTH2_REDIRECT, WEBSERVER_URL
from adare.web.exceptions import LoginFailedError, AlreadyLoggedIn, NoUserLoggedIn
from adare.database.api.usersession import UserSessionApi
from adare.console import console_print, log_print

import logging

log = logging.getLogger(__name__)


class RedirectHandler(http.server.SimpleHTTPRequestHandler):
    code_verifier = None
    state = None
    redirect_uri = None

    def do_GET(self):
        if not self.path.startswith('/oauth/callback'):
            return
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Authorization successful. You can close this window.")
        # Extract the authorization code from the query string, and use it in your application
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)
        state = query_params.get('state', [None])[0]
        if state != self.state:
            self.send_error(400, "State mismatch")
            raise LoginFailedError(log, "State mismatch")
        authorization_code = query_params.get('code', [None])[0]
        log.info("Received authorization code")
        # Here you would normally signal your application to continue with the code exchange process

        # Shut down the HTTP server
        resp = exchange_code_for_token(GITEA_CLIENT_ID, authorization_code, self.code_verifier, self.redirect_uri)
        self.server.gitea_access_token = resp['access_token']
        self.server.gitea_access_token_expiry = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=resp['expires_in'])
        self.server.gitea_refresh_token = resp.get('refresh_token', None)
        log.info("Received access token")

    def log_message(self, format, *args):
        log.info(f'[{self.log_date_time_string()}] {format % args}')


class LoginHTTPServer(http.server.HTTPServer):
    gitea_access_token: str
    gitea_access_token_expiry: datetime.datetime
    gitea_refresh_token: str

    def __init__(self, server_address, RequestHandlerClass):
        super().__init__(server_address, RequestHandlerClass)
        self.server_activate()
        self.gitea_access_token = ''
        self.gitea_access_token_expiry = datetime.datetime.now(datetime.timezone.utc)
        self.gitea_refresh_token = ''


def generate_state():
    return secrets.token_urlsafe(16)


def base64_url_encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')


def generate_code_verifier():
    return base64_url_encode(os.urandom(40))


def generate_code_challenge(code_verifier):
    digest = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    return base64_url_encode(digest)


def start_oauth_flow(redirect_uri, port):
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)
    state = generate_state()

    with LoginHTTPServer(('localhost', port), RedirectHandler) as httpd:
        RedirectHandler.code_verifier = code_verifier
        RedirectHandler.state = state
        RedirectHandler.redirect_uri = redirect_uri
        log.info(f"Started HTTP server on port {port}")

        # Step 1: Redirect user to the authorization endpoint
        auth_url = f"{GITEA_URL}login/oauth/authorize?response_type=code&client_id={GITEA_CLIENT_ID}&redirect_uri={urllib.parse.quote_plus(redirect_uri)}&state={state}&code_challenge={code_challenge}&code_challenge_method=S256"
        webbrowser.open(auth_url, new=0, autoraise=True)
        console_print("A browser window has been opened. Please log in and authorize the application.")
        console_print(f'\nIf the browser does not open, please visit the following URL manually: [i blue]{auth_url}[/i blue]')

        # Wait for a single request and get self.path from the handler
        try:
            httpd.handle_request()
        except KeyboardInterrupt as e:
            console_print("Received keyboard interrupt, shutting down HTTP server")
            raise LoginFailedError(log, "Login cancelled by user") from e
        finally:
            httpd.server_close()

        gitea_access_token = httpd.gitea_access_token
        gitea_access_token_expiry = httpd.gitea_access_token_expiry
        gitea_refresh_token = httpd.gitea_refresh_token

        # gitea_access_token_expiry has the wrong timezone since its data is timezone aware for Berlin and we want it to be UTC


    # access django api to retrieve django knox token
    try:
        response = requests.post(f'{WEBSERVER_URL}api/auth/gitea/', data={'access_token': gitea_access_token})
        if response.status_code != 200:
            raise LoginFailedError(log,
                                   f"Failed to retrieve Django token ({response.status_code}): {response.text}")
    except requests.exceptions.RequestException as e:
        raise LoginFailedError(
            log, "Failed to retrieve Django token"
        ) from e

    log.info("Received Django token")

    django_username = response.json()['user']
    django_token = response.json()['token']
    django_expiry = datetime.datetime.strptime(response.json()['expiry'], '%Y-%m-%dT%H:%M:%S.%fZ')


    # Save the tokens to the database
    with UserSessionApi() as db:
        db.add_user_session(
            username=django_username,
            gitea_token=gitea_access_token,
            gitea_token_expiration=gitea_access_token_expiry,
            gitea_refresh_token=gitea_refresh_token,
            django_token=django_token,
            django_token_expiration=django_expiry,
        )
    log.info("Saved tokens to database")
    log_print(log, f"\nLogged in as user [b]{django_username}[/b]")


def exchange_code_for_token(client_id, code, code_verifier, redirect_uri):
    token_url = f"{GITEA_URL}login/oauth/access_token"
    headers = {'Accept': 'application/json'}
    payload = {
        'client_id': client_id,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': redirect_uri,
        'code_verifier': code_verifier
    }
    response = requests.post(token_url, headers=headers, data=payload)
    return response.json()


def login():
    with UserSessionApi() as db:
        if user_session := db.get_first_user_session():
            log.info(f"User {user_session.username} is already logged in")
            raise AlreadyLoggedIn(
                log,
                f"User {user_session.username} is already logged in",
                [
                    'if you want to login as a different user, please logout first via [i]adare logout[/i]'
                ],
            )

    redirect_handler_port = next(
        (
            port
            for port in PORT_OAUTH2_REDIRECT
            if is_localhost_port_free(port)
        ),
        -1,
    )
    if redirect_handler_port == -1:
        raise LoginFailedError(
            log,
            f"No free port found for OAuth2 redirect handler. Please close some applications and try again. (Ports tried: {PORT_OAUTH2_REDIRECT})"
        )
    redirect_uri = f"http://localhost:{redirect_handler_port}/oauth/callback"
    log.info(f"Using redirect URI: {redirect_uri}")

    # Start the OAuth flow
    start_oauth_flow(redirect_uri, redirect_handler_port)


def is_logged_in(username: str = None, silent:bool = False):
    with UserSessionApi() as db:
        db.remove_expired_user_sessions()
        if not username:
            if user_session := db.get_first_user_session():
                username = user_session.username
        if not username:
            if not silent:
                log_print(log, "No user is currently logged in")
            return False
        if not silent:
            log_print(log, f"User [b]{username}[/b] is currently logged in")
        return True



def logout(username: str = None):
    with UserSessionApi() as db:
        if not username:
            if user_session := db.get_first_user_session():
                username = user_session.username
        if not username:
            raise NoUserLoggedIn(log, "No user is currently logged in")
        db.remove_user_session(username)
    log_print(log, f'Logged out user [b]{username}[/b]')
