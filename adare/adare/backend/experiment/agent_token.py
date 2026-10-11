"""
The per-run secret the guest agent requires on every WebSocket connection.

It travels to the guest inside the run's ``config.json`` (written by the file
transfer strategy or the agent command builder) and back to the host client
as an ``Authorization`` header. A run directory that already has a token in its
``config.json`` keeps it, so a restored dev session reconnects to an agent that
is still running.
"""

import json
import logging
import secrets

from adare.logger.redaction import register_secret

log = logging.getLogger(__name__)

CONFIG_KEY = 'agent_token'


def ensure_agent_token(context) -> str:
    """Return the run's agent token, loading it from the run's config.json or creating one."""
    token = getattr(context, 'agent_token', None)
    if not (isinstance(token, str) and token):
        token = _token_from_run_config(context) or secrets.token_urlsafe(32)
        context.agent_token = token
    register_secret(token)
    return token


def _token_from_run_config(context) -> str | None:
    run_directory = getattr(context, 'experiment_run_directory', None)
    if run_directory is None:
        return None
    config_path = run_directory.path / 'config.json'
    try:
        token = json.loads(config_path.read_text(encoding='utf-8')).get(CONFIG_KEY)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError, AttributeError) as e:
        log.debug(f"Could not read agent token from {config_path}: {e}")
        return None
    return token if isinstance(token, str) and token else None
