"""Agent-free, host-side backend (see docs/guide/hostside-backend.rst).

``agent`` is the default and unchanged behavior; ``hostside`` runs the same
playbooks with no process of ours inside the guest.
"""

from adare.backend.hostside.backend import BACKEND_AGENT, BACKEND_HOSTSIDE, BACKENDS, is_hostside, resolve_backend

__all__ = ['BACKENDS', 'BACKEND_AGENT', 'BACKEND_HOSTSIDE', 'is_hostside', 'resolve_backend']
