"""
Host side of hypervisor port forwards (QEMU hostfwd, VirtualBox NAT rules).

A forward with an empty host address listens on every interface, which exposes
the unauthenticated guest agent to the whole network. Forwards therefore bind
to loopback unless ``$ADARE_FORWARD_BIND`` names another address (e.g. a LAN
IP when the host client runs on a different machine than the hypervisor).
"""

import os

FORWARD_BIND_ENV_VAR = 'ADARE_FORWARD_BIND'
DEFAULT_FORWARD_BIND = '127.0.0.1'

_WILDCARDS = frozenset({'0.0.0.0', '::', ''})


def forward_bind_host() -> str:
    """Host address port forwards listen on."""
    return os.getenv(FORWARD_BIND_ENV_VAR, '').strip() or DEFAULT_FORWARD_BIND


def forward_connect_host() -> str:
    """Address clients use to reach a forwarded port (loopback for wildcard binds)."""
    host = forward_bind_host()
    return DEFAULT_FORWARD_BIND if host in _WILDCARDS else host


def qemu_hostfwd(protocol: str, host_port: int, guest_port: int, host_ip: str = '', guest_ip: str = '') -> str:
    """QEMU ``hostfwd=`` value; a rule without a host address gets the bind host."""
    return f'{protocol}:{host_ip or forward_bind_host()}:{host_port}-{guest_ip}:{guest_port}'
