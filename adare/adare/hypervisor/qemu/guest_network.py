"""
Bring a Linux guest's NIC up when its baked network config does not match the
PCI address ADARE gives the NIC at run time.

Why this is needed
------------------
The VM *creators* build a raw QEMU command line with a plain, auto-assigned NIC
(``-device virtio-net-pci,netdev=net0``), which lands on ``pcie.0`` slot ``0x01``,
so the guest sees ``enp0s1`` and the installer bakes that name into
``/etc/netplan/*.yaml``.

Experiment *runs* go through ``libvirt_xml_builder._add_network_commandline()``,
which pins ``virtio-net-pci,netdev=net0,bus=pcie.0,addr=0x1f``. ``0x1f`` is 31, so
the same NIC now enumerates as ``enp0s31``. netplan matches nothing, the link is
never configured, and the guest ends up with only ``lo``:

* ``systemd-networkd-wait-online`` burns its full 120s timeout on every boot,
* nothing can reach the SLIRP SMB server at ``10.0.2.4``, so file transfer falls
  back to the much slower QGA path,
* the port-forwarded adarevm websocket has no guest-side stack to bind against.

Guests whose networking is NetworkManager-managed (Fedora) or NetworkManager-rescued
(Ubuntu 24.04, after the 120s timeout) survive this; netplan/systemd-networkd
guests (Kubuntu, Ubuntu 22.04/20.04) do not.

The creators are being aligned so future images bake a matching name, but images
already built carry the old name, and ADARE should not depend on a baked guest
config agreeing with a topology ADARE itself chooses. So this module repairs the
link at run time.

No files are written inside the guest — only in-memory kernel state — so guest
disk state stays clean for forensic purposes. The static fallback is safe because
QEMU SLIRP's addressing is fixed: the first (and here only) client always gets
``10.0.2.15/24`` with the gateway at ``10.0.2.2``.
"""
import asyncio
import logging

log = logging.getLogger(__name__)

# QEMU SLIRP user-mode networking addresses (fixed by QEMU, not negotiable)
SLIRP_GUEST_IP = '10.0.2.15'
SLIRP_PREFIX = 24
SLIRP_GATEWAY = '10.0.2.2'
SLIRP_DNS = '10.0.2.3'

# How long to let the guest's own DHCP client (networkd / NetworkManager) claim a
# link that was merely down, before assigning the address ourselves.
_DHCP_GRACE_SECONDS = 6


def _has_ipv4(output: str) -> bool:
    """True if `ip -4 -o addr show` output contains a non-loopback address."""
    for line in output.splitlines():
        if not line.strip():
            continue
        # `ip -4 -o addr` lines look like: "2: enp0s31    inet 10.0.2.15/24 ..."
        parts = line.split()
        if len(parts) >= 2 and parts[1] != 'lo':
            return True
    return False


async def _configure_dns(vm, iface: str, stop_event=None) -> None:
    """Point the guest's resolver at SLIRP's DNS forwarder.

    An address and a default route are not enough: the agent bootstrap pip-installs
    from PyPI, which fails with "Temporary failure in name resolution" if only the
    route was restored.

    Prefers ``resolvectl``, which sets the resolver in systemd-resolved's runtime
    state without writing to the guest filesystem. Only if that is unavailable
    (or resolution still fails) does it fall back to writing ``/etc/resolv.conf``.
    """
    probe_dns = 'getent hosts pypi.org >/dev/null 2>&1 && echo DNS_OK || echo DNS_FAIL'

    resolvectl = (
        f'command -v resolvectl >/dev/null 2>&1 && '
        f'resolvectl dns {iface} {SLIRP_DNS} && resolvectl domain {iface} "~." '
        f'&& echo RESOLVECTL_OK || echo RESOLVECTL_UNAVAILABLE'
    )
    await vm.run_command(resolvectl, admin=True, silent=True, stop_event=stop_event)

    check = await vm.run_command(probe_dns, silent=True, stop_event=stop_event)
    if 'DNS_OK' in check.stdout:
        log.info(f"Guest DNS configured via resolvectl on '{iface}' ({SLIRP_DNS})")
        return

    # Last resort: a real resolv.conf. This does write one guest file, but a guest
    # that cannot resolve names cannot install the agent at all.
    log.warning(
        f'resolvectl did not restore name resolution; writing /etc/resolv.conf '
        f'with nameserver {SLIRP_DNS}'
    )
    await vm.run_command(
        f'printf "nameserver {SLIRP_DNS}\\n" > /etc/resolv.conf',
        admin=True, silent=True, stop_event=stop_event,
    )

    check = await vm.run_command(probe_dns, silent=True, stop_event=stop_event)
    if 'DNS_OK' in check.stdout:
        log.info(f'Guest DNS configured via /etc/resolv.conf ({SLIRP_DNS})')
    else:
        log.error(
            'Guest still cannot resolve names. Anything that installs from a '
            'package index (e.g. the adarevm agent bootstrap) will fail.'
        )


async def ensure_guest_network(vm, stop_event=None) -> bool:
    """Ensure a Linux guest has an IPv4 address on a non-loopback interface.

    Idempotent and best-effort: a guest that already has an address is left
    untouched, and any failure is logged rather than raised, because a guest
    without networking can still be driven over QGA.

    Args:
        vm: QEMUVM to repair
        stop_event: Optional cancellation event

    Returns:
        True if the guest has a non-loopback IPv4 address when this returns.
    """
    if 'windows' in vm.guest_os.lower():
        return True

    probe = await vm.run_command('ip -4 -o addr show', silent=True, stop_event=stop_event)
    if probe.returncode == 0 and _has_ipv4(probe.stdout):
        log.debug('Guest already has an IPv4 address; no network repair needed')
        return True

    log.warning(
        'Guest has no IPv4 address on any non-loopback interface. This happens when '
        'the interface name baked into the guest network config does not match the '
        "PCI address ADARE assigns the NIC at run time. Bringing the link up."
    )

    # Step 1: bring every non-loopback link up. On guests where the link was
    # merely down, the guest's own DHCP client takes over from here.
    # Prefer a real ethernet name (en*/eth*) over anything else a guest may carry
    # (docker0, virbr0, ...), which `ls` would otherwise sort ahead of it.
    up_script = (
        'for i in $(ls /sys/class/net | grep -v "^lo$"); do '
        'ip link set "$i" up 2>/dev/null; done; '
        'pick=$(ls /sys/class/net | grep -E "^(en|eth)" | head -1); '
        # Cannot test the pipeline's status here: `head` exits 0 even when grep
        # matched nothing, so fall back on the variable being empty instead.
        '[ -n "$pick" ] || pick=$(ls /sys/class/net | grep -v "^lo$" | head -1); '
        'echo "$pick"'
    )
    up = await vm.run_command(up_script, admin=True, silent=True, stop_event=stop_event)
    iface = up.stdout.strip().splitlines()[-1].strip() if up.stdout.strip() else ''
    if not iface:
        log.error('Guest network repair failed: no non-loopback interface found')
        return False

    log.info(f"Brought guest interface '{iface}' up; waiting for DHCP")
    await asyncio.sleep(_DHCP_GRACE_SECONDS)

    probe = await vm.run_command('ip -4 -o addr show', silent=True, stop_event=stop_event)
    if probe.returncode == 0 and _has_ipv4(probe.stdout):
        log.info(f"Guest interface '{iface}' obtained an address via DHCP")
        return True

    # Step 2: no DHCP client claimed the link. Assign SLIRP's fixed address
    # directly. In-memory only; nothing is written to the guest filesystem.
    log.warning(
        f"No DHCP client claimed '{iface}'; assigning SLIRP's fixed address "
        f'{SLIRP_GUEST_IP}/{SLIRP_PREFIX} via {SLIRP_GATEWAY}'
    )
    static_script = (
        f'ip addr add {SLIRP_GUEST_IP}/{SLIRP_PREFIX} dev {iface} 2>/dev/null; '
        f'ip link set {iface} up; '
        f'ip route replace default via {SLIRP_GATEWAY} dev {iface}'
    )
    await vm.run_command(static_script, admin=True, silent=True, stop_event=stop_event)
    await _configure_dns(vm, iface, stop_event)

    probe = await vm.run_command('ip -4 -o addr show', silent=True, stop_event=stop_event)
    if probe.returncode == 0 and _has_ipv4(probe.stdout):
        log.info(f"Guest interface '{iface}' configured statically")
        return True

    log.error(
        f"Guest network repair failed: '{iface}' still has no IPv4 address. "
        'File transfer will fall back to QGA and the guest agent websocket may '
        'be unreachable.'
    )
    return False
