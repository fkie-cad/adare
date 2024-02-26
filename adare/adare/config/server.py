from .configdirectory import APPDATA_DIR
from .exceptions import ConfigDirectoryError


def get_cookie_file():
    if not APPDATA_DIR:
        raise ConfigDirectoryError('the config directory could not be set')

    return APPDATA_DIR / 'adare.cookies'


WEBSERVER_URL = 'https://adare.seclab-bonn.de/'
API_URL = f'{WEBSERVER_URL}api/'
LOGIN_URL = f'{WEBSERVER_URL}api/user/login/'
LOGOUT_URL = f'{WEBSERVER_URL}api/user/logout/'
CSRF_URL = f'{WEBSERVER_URL}api/csrf/'
ADD_EXPERIMENT_URL = f'{WEBSERVER_URL}api/experiment/add'
CHECK_EXPERIMENT_URL = f'{WEBSERVER_URL}api/experiment/check'
CHECK_REQUEST_URL = f'{WEBSERVER_URL}api/request/check'
ADD_EXPERIMENT_REQUEST_URL = f'{WEBSERVER_URL}api/request/experiment/create/'

TIMEOUT_SECONDS = 10

# PORTS FOR OAuth2 Redirects
PORT_OAUTH2_REDIRECT = [
    13331,
    13332,
    13333,
    13334,
    13335,
    14441,
    14442,
    14443,
    14444,
    14445
]
GITEA_CLIENT_ID = '9afe946b-d67f-46ac-8362-4ef479a8e11c'
GITEA_URL = 'https://adare.seclab-bonn.de/git/'
