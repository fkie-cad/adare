"""Isolated inter-VM libvirt ``<network>`` management for multi-machine experiments.

Genuinely new territory for ADARE: it relies exclusively on QEMU's usermode/SLIRP
networking today (confirmed via a repo-wide grep -- no libvirt ``<network>``
object management existed anywhere before this module). A multi-machine
experiment (e.g. a Nextcloud client VM and server VM) needs its machines to
reach each other by LAN IP/hostname without exposing them to the host's outside
network, which is exactly what an isolated libvirt network (no ``<forward>``
element -- no NAT, no routing out) provides.

**Unverified.** This module has not been exercised against a live libvirt
daemon in this session -- there is no existing ADARE pattern for libvirt
``<network>`` objects to mirror or cross-check against. Per the plan's own
Phase 0, hand-build two QEMU VMs on a network created by this module and
confirm they can reach each other end-to-end before trusting it in a real
multi-machine experiment run.
"""

import logging

log = logging.getLogger(__name__)

# Linux bridge device names are capped at IFNAMSIZ - 1 = 15 characters.
_BRIDGE_NAME_MAX = 15


def _bridge_name(network_name: str) -> str:
    prefix = 'adare-'
    return (prefix + network_name)[:_BRIDGE_NAME_MAX]


def _network_xml(name: str, subnet: str) -> str:
    """Build ``<network>`` XML for an isolated, DHCP-enabled bridge.

    No ``<forward>`` element: libvirt treats this as an isolated network (no
    NAT, no routing to the outside world) -- machines on it can reach only each
    other and the host-side bridge.

    Args:
        name: Network name.
        subnet: Third-octet-style IPv4 base, e.g. ``'192.168.100'`` for a
            192.168.100.0/24 network (bridge at .1, DHCP hands out .2-.254).
    """
    bridge = _bridge_name(name)
    return (
        "<network>"
        f"<name>{name}</name>"
        f"<bridge name='{bridge}' stp='on' delay='0'/>"
        f"<ip address='{subnet}.1' netmask='255.255.255.0'>"
        f"<dhcp><range start='{subnet}.2' end='{subnet}.254'/></dhcp>"
        "</ip>"
        "</network>"
    )


def ensure_isolated_network(conn, name: str, subnet: str):
    """Define (if missing), start and autostart an isolated libvirt network.

    Idempotent: an existing network with this name is reused (and started if
    not already active) rather than redefined, so this is safe to call once per
    machine of a multi-machine run.

    Args:
        conn: An open libvirt connection (``libvirt.open('qemu:///session')``).
        name: Network name, unique per experiment run (e.g. ``f"adare-{run_ulid}"``).
        subnet: Third-octet-style IPv4 base, e.g. ``'192.168.100'``.

    Returns:
        The ``libvirt.virNetwork`` object.
    """
    import libvirt

    try:
        network = conn.networkLookupByName(name)
        log.debug(f"Reusing existing isolated network '{name}'")
    except libvirt.libvirtError:
        network = conn.networkDefineXML(_network_xml(name, subnet))
        log.info(f"Defined isolated network '{name}' ({subnet}.0/24)")

    if not network.isActive():
        network.create()
        log.info(f"Started isolated network '{name}'")

    try:
        network.setAutostart(True)
    except libvirt.libvirtError as e:
        # Best-effort: autostart only matters for surviving a libvirtd restart
        # mid-experiment, not for this run's correctness.
        log.warning(f"Could not set autostart on network '{name}': {e}")

    return network


def teardown_isolated_network(conn, name: str) -> None:
    """Stop and undefine the isolated network ``name``. Idempotent and best-effort.

    Called once per multi-machine run (not once per machine -- the network is
    shared across all of a run's machines), typically from the orchestrator's
    final cleanup step.
    """
    import libvirt

    try:
        network = conn.networkLookupByName(name)
    except libvirt.libvirtError:
        log.debug(f"Isolated network '{name}' already gone, nothing to tear down")
        return

    try:
        if network.isActive():
            network.destroy()
    except libvirt.libvirtError as e:
        log.warning(f"Could not stop isolated network '{name}': {e}")

    try:
        network.undefine()
    except libvirt.libvirtError as e:
        log.warning(f"Could not undefine isolated network '{name}': {e}")
