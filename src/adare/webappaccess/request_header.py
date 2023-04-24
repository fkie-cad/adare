import requests
from adare.database.database import UserSessionApi

# configure logging
import logging
log = logging.getLogger(__name__)

def get_authenticated_request_header(user_session_token, webserver_url):
    if not user_session_token:
        return None
    with requests.session() as session:
        req_csrf = session.get(f'{webserver_url}/csrf/')
        csrftoken = req_csrf.cookies['csrftoken']
        header = {
            'X-CSRFToken': csrftoken,
            'Referer': f'{webserver_url}',
            'Authorization': f'Token {user_session_token}'
        }
        return header