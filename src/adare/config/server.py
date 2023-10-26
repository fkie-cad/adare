from .configdirectory import get_default_config_directory
from .exceptions import ConfigDirectoryError

def get_cookie_file():
    try:
        CONFIG_DIR = get_default_config_directory(create_if_missing=True)
    except (FileNotFoundError, FileExistsError, NotADirectoryError, IsADirectoryError) as e:
        CONFIG_DIR = None

    if not CONFIG_DIR:
        raise ConfigDirectoryError(f'the config directory could not be set')

    return CONFIG_DIR / 'adare.cookies'


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