import logging
import os

from .configdirectory import APPDATA_DIR
from .exceptions import ConfigDirectoryError

log = logging.getLogger(__name__)


def get_cookie_file():
    if not APPDATA_DIR:
        raise ConfigDirectoryError(log, 'the config directory could not be set')

    return APPDATA_DIR / 'adare.cookies'


WEBSERVER_URL = 'https://adare.seclab-bonn.de/'
# WEBSERVER_URL = 'http://localhost:8000/'
API_URL = f'{WEBSERVER_URL}api/'
DOWNLOAD_API_URL = f'{API_URL}download/'
HASH_API_URL = f'{API_URL}hash/'
LOGIN_URL = f'{WEBSERVER_URL}api/user/login/'
LOGOUT_URL = f'{WEBSERVER_URL}api/user/logout/'
CSRF_URL = f'{WEBSERVER_URL}api/csrf/'
ADD_EXPERIMENT_URL = f'{WEBSERVER_URL}api/experiment/add'
CHECK_EXPERIMENT_URL = f'{WEBSERVER_URL}api/experiment/check'
CHECK_REQUEST_URL = f'{WEBSERVER_URL}api/request/check'
ADD_EXPERIMENT_REQUEST_URL = f'{WEBSERVER_URL}api/request/experiment/create/'
PUBLISH_RUN_URL = f'{WEBSERVER_URL}api/run/publish/'

TIMEOUT_SECONDS = 10

# ── GUI-automation vision-LLM (vLLM) configuration ───────────────────────────
# A grounding-capable vision model served over an OpenAI-compatible endpoint
# (Qwen3-VL / Qwen2-VL / UI-TARS / Molmo-class). Used ONLY during a GUI-automation
# *record* run, the *agent* (`adare dev agent`), and *self-heal* on a replay miss —
# deterministic replay needs no LLM.
#
# Works with any OpenAI-compatible server, e.g. Ollama Cloud:
#   ADARE_VLLM_BASE_URL=https://ollama.com/v1
#   ADARE_VLLM_API_KEY=<key from ollama.com/settings/keys>
#   ADARE_VLLM_MODEL=qwen3-vl:235b-cloud        # GUI-grounding / computer-use
#   ADARE_VLLM_COORD_SPACE=normalized_1000       # Qwen3-VL returns 0..1000 coords
# Run `adare vm gui-doctor` to verify the endpoint and auto-detect the coord space.
VLLM_BASE_URL = os.environ.get('ADARE_VLLM_BASE_URL', 'http://localhost:8000/v1')
VLLM_MODEL = os.environ.get('ADARE_VLLM_MODEL', 'Qwen/Qwen2-VL-7B-Instruct')
VLLM_API_KEY = os.environ.get('ADARE_VLLM_API_KEY', 'EMPTY')

# Coordinate convention the model returns clicks in:
#   'absolute'        — raw pixel coordinates of the image it was shown (default)
#   'normalized_1000' — 0..1000 on both axes (rescaled to pixels by the client)
VLLM_COORD_SPACE = os.environ.get('ADARE_VLLM_COORD_SPACE', 'absolute')

# Bounded-autonomy budgets for the record run.
GUI_AGENT_MAX_STEPS = int(os.environ.get('ADARE_GUI_AGENT_MAX_STEPS', '80'))
GUI_AGENT_STALL_LIMIT = int(os.environ.get('ADARE_GUI_AGENT_STALL_LIMIT', '6'))
GUI_AGENT_WALL_CLOCK_SECONDS = int(os.environ.get('ADARE_GUI_AGENT_WALL_CLOCK_SECONDS', '3600'))

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
GITEA_API_URL = f'{GITEA_URL}api/v1/'
GITEA_EXPERIMENTS_REPO = 'adareTEST'
GITEA_EXPERIMENTS_REPO_OWNER = 'miq'
