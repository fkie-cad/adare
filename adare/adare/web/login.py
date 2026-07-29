import base64
import datetime
import hashlib
import http.server
import logging
import os
import secrets
import urllib.parse
import webbrowser
from urllib.parse import parse_qs, urlparse

import requests

from adare.config.server import GITEA_CLIENT_ID, GITEA_URL, PORT_OAUTH2_REDIRECT, WEBSERVER_URL
from adare.console import console_print, log_print
from adare.database.api.usersession import UserSessionApi
from adare.helperfunctions.port import is_localhost_port_free
from adare.web.exceptions import AlreadyLoggedIn, LoginFailedError, NoUserLoggedIn

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
        self.server.gitea_access_token_expiry = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=resp['expires_in'])
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
        self.gitea_access_token_expiry = datetime.datetime.now(datetime.UTC)
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

    # access django api to retrieve django knox token
    django_username, django_token, django_expiry = exchange_gitea_for_django(gitea_access_token)

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


def refresh_gitea_token(refresh_token):
    """Exchange a Gitea refresh token for a fresh access token.

    Mirrors ``exchange_code_for_token``: the OAuth2 client is a public/PKCE client, so
    the ``authorization_code`` grant works without a ``client_secret`` and the
    ``refresh_token`` grant behaves the same way. If a future Gitea configuration requires
    a secret for this grant, source it from ``adare.config.server`` alongside
    ``GITEA_CLIENT_ID`` and add it to the payload.

    Returns the parsed JSON response, which contains a new ``access_token``, ``expires_in``
    and a (rotated) ``refresh_token``.
    """
    token_url = f"{GITEA_URL}login/oauth/access_token"
    headers = {'Accept': 'application/json'}
    payload = {
        'client_id': GITEA_CLIENT_ID,
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
    }
    response = requests.post(token_url, headers=headers, data=payload)
    return response.json()


def exchange_gitea_for_django(gitea_access_token):
    """Exchange a Gitea access token for a Django Knox token.

    Returns a ``(username, token, expiry)`` tuple. Shared by the initial login and the
    token-refresh path so both mint the Knox token the same way.
    """
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
    return django_username, django_token, django_expiry


def refresh_session_if_needed(username: str = None, skew_seconds: int = 60):
    """Renew a session's tokens using the stored Gitea refresh token, before pruning.

    Loads the session without pruning it. If the Gitea access token is expired (or within
    ``skew_seconds`` of expiring) and a refresh token is present, exchanges the refresh
    token for a fresh Gitea access token, re-exchanges that for a new Django Knox token,
    and persists both with advanced expirations so the subsequent time-based pruning does
    not delete the session.

    On any refresh failure it does nothing and returns, letting the normal pruning run
    (i.e. a genuine logout). All HTTP work happens here in the auth layer, never in the DB
    layer.
    """
    with UserSessionApi() as db:
        user_session = db.get_session_for_refresh(username)
        if not user_session or not user_session.gitea_token:
            return
        refresh_token_obj = user_session.gitea_refresh_token
        if not refresh_token_obj or not refresh_token_obj.token:
            # No refresh token stored -> cannot renew, let pruning handle it.
            return
        expiration = user_session.gitea_token.expiration.replace(tzinfo=datetime.UTC)
        if expiration > datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=skew_seconds):
            # Access token still valid -> nothing to do.
            return
        session_username = user_session.username
        refresh_token = refresh_token_obj.token

    try:
        gitea_response = refresh_gitea_token(refresh_token)
        new_access_token = gitea_response['access_token']
        new_expiry = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=gitea_response['expires_in'])
        new_refresh_token = gitea_response.get('refresh_token', refresh_token)
    except (requests.exceptions.RequestException, ValueError, KeyError) as e:
        log.warning(f"Failed to refresh Gitea token for user {session_username}: {e}")
        return

    try:
        _, django_token, django_expiry = exchange_gitea_for_django(new_access_token)
    except LoginFailedError as e:
        log.warning(f"Failed to re-exchange Django token for user {session_username}: {e}")
        return

    with UserSessionApi() as db:
        db.update_session_tokens(
            username=session_username,
            gitea_token=new_access_token,
            gitea_token_expiration=new_expiry,
            gitea_refresh_token=new_refresh_token,
            django_token=django_token,
            django_token_expiration=django_expiry,
        )
    log.info(f"refreshed session tokens for user {session_username}")


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
    refresh_session_if_needed(username)
    with UserSessionApi() as db:
        db.remove_expired_user_sessions()
        if not username and (user_session := db.get_first_user_session()):
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
        if not username and (user_session := db.get_first_user_session()):
            username = user_session.username
        if not username:
            raise NoUserLoggedIn(log, "No user is currently logged in")
        db.remove_user_session(username)
    log_print(log, f'Logged out user [b]{username}[/b]')
