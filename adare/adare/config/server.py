from .configdirectory import APPDATA_DIR
from .exceptions import ConfigDirectoryError

def get_cookie_file():
    if not APPDATA_DIR:
        raise ConfigDirectoryError(f'the config directory could not be set')

    return APPDATA_DIR / 'adare.cookies'


WEBSERVER_URL = 'http://localhost:8000'
API_URL = WEBSERVER_URL + '/api/'
LOGIN_URL = WEBSERVER_URL + '/api/user/login/'
LOGOUT_URL = WEBSERVER_URL + '/api/user/logout/'
CSRF_URL = WEBSERVER_URL + '/api/csrf/'
ADD_EXPERIMENT_URL = WEBSERVER_URL + '/api/experiment/add'
CHECK_EXPERIMENT_URL = WEBSERVER_URL + '/api/experiment/check'
CHECK_REQUEST_URL = WEBSERVER_URL + '/api/request/check'
ADD_EXPERIMENT_REQUEST_URL = WEBSERVER_URL + '/api/request/experiment/create/'

TIMEOUT_SECONDS = 10