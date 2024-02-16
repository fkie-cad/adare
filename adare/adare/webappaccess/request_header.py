from adare.config.server import WEBSERVER_URL

# configure logging
import logging
log = logging.getLogger(__name__)

def get_authenticated_request_header(user_session_token: str):
    if not user_session_token:
        return None
    header = {
        'Referer': WEBSERVER_URL,
        'Authorization': f'Token {user_session_token}'
    }
    return header