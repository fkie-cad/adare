# NOT IN USE - saved in database

import json
from pathlib import Path
import requests
import requests.utils


def save_cookies(file: Path, cookie_jar):
    with open(file.as_posix(), 'w') as f:
        json.dump(requests.utils.dict_from_cookiejar(cookie_jar), f)


def load_cookies(file: Path, session: requests.Session):
    with open(file.as_posix(), 'r') as f:
        cookies = requests.utils.cookiejar_from_dict(json.load(f))
        session.cookies.update(cookies)
