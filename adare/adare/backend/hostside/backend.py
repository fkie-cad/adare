"""Backend selection: ``agent`` (in-guest adarevm, the default) or ``hostside`` (no guest process)."""

from __future__ import annotations

import os

BACKEND_AGENT = 'agent'
BACKEND_HOSTSIDE = 'hostside'
BACKENDS = (BACKEND_AGENT, BACKEND_HOSTSIDE)
ENV_VAR = 'ADARE_BACKEND'


def resolve_backend(cli_value: str | None = None, playbook_settings=None) -> str:
    """Pick the backend: CLI ``--backend`` > ``ADARE_BACKEND`` > playbook ``settings.backend`` > ``agent``."""
    for candidate in (
        cli_value,
        os.environ.get(ENV_VAR),
        getattr(playbook_settings, 'backend', None) if playbook_settings is not None else None,
    ):
        if candidate and candidate != 'auto':
            if candidate not in BACKENDS:
                raise ValueError(f"Invalid backend {candidate!r}. Must be one of: {', '.join(BACKENDS)}")
            return candidate
    return BACKEND_AGENT


def is_hostside(context) -> bool:
    """True when this run (an ``ExperimentRunCtx``) uses the host-side backend."""
    return getattr(getattr(context, 'config', None), 'backend', BACKEND_AGENT) == BACKEND_HOSTSIDE
