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

# Optional open-vocabulary element-grounding backend for the GUI agent.
# When set, `adare dev agent` grounds each click to the true element bounding
# box (via the standalone LocateAnything sidecar, scripts/locate_anything_sidecar.py)
# and records the tight icon crop instead of the fixed box around the click.
# Empty (default) keeps the fixed ~220x90 crop. The sidecar is a separate
# process holding the heavy model — no VLM deps enter the adare package.
#   ADARE_LOCATE_URL=http://127.0.0.1:13111
LOCATE_URL = os.environ.get('ADARE_LOCATE_URL', '')
LOCATE_MODE = os.environ.get('ADARE_LOCATE_MODE', 'hybrid')
# The recorded crop expands the grounded element box by this margin (px per side)
# and is grown to at least this minimum size, keeping it centred on the element.
# A bare element box can be tiny or a generic glyph (e.g. a document icon) that
# collides with similar UI; a little context makes the crop robust for the CV
# replay matcher while staying far tighter than the fixed ~220x90 fallback.
LOCATE_CROP_MARGIN = int(os.environ.get('ADARE_LOCATE_CROP_MARGIN', '16'))
LOCATE_CROP_MIN = int(os.environ.get('ADARE_LOCATE_CROP_MIN', '72'))
# When on (and a grounding sidecar is configured), LocateAnything owns the click
# coordinate: the VLM says WHAT to click ("describe") and LA locates the element,
# then the agent clicks its centre — using the VLM's own point only as a
# disambiguating hint and as the fallback on a miss/error. Default off keeps
# today's behaviour (VLM point clicks; LA only tightens the recorded crop).
LOCATE_CLICK = os.environ.get('ADARE_LOCATE_CLICK', '0').lower() in ('1', 'true', 'yes', 'on')

# Bounded-autonomy budgets for the record run.
GUI_AGENT_MAX_STEPS = int(os.environ.get('ADARE_GUI_AGENT_MAX_STEPS', '80'))
GUI_AGENT_STALL_LIMIT = int(os.environ.get('ADARE_GUI_AGENT_STALL_LIMIT', '6'))
GUI_AGENT_WALL_CLOCK_SECONDS = int(os.environ.get('ADARE_GUI_AGENT_WALL_CLOCK_SECONDS', '3600'))

# Self-heal for a malformed / incomplete agent decision. A pure JSON-syntax
# slip is fixed by a cheap text-only repair call (no screenshot re-sent); a
# genuinely missing coordinate/choice costs a full vision re-ask. Recovery runs
# for at most GUI_AGENT_DECISION_RETRIES attempts after the first decision
# before the run fails honestly. If AGENT_REPAIR_MODEL is set, the cheap syntax
# repair uses that (typically smaller/cheaper) model on the same endpoint;
# empty (default) reuses the main VLLM model text-only.
AGENT_REPAIR_MODEL = os.environ.get('ADARE_AGENT_REPAIR_MODEL', '')
GUI_AGENT_DECISION_RETRIES = int(os.environ.get('ADARE_GUI_AGENT_DECISION_RETRIES', '2'))

# Port the `adare dev mcp` GUI-automation MCP server binds. An external harness
# (OpenCode / Claude Code / any MCP client) connects here to author playbooks.
# Distinct from the CV/OCR server's 13109 so both can run against one session.
GUI_MCP_PORT = int(os.environ.get('ADARE_GUI_MCP_PORT', '13110'))
GUI_MCP_HOST = os.environ.get('ADARE_GUI_MCP_HOST', '127.0.0.1')

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
