"""Single chokepoint for QEMU acceleration (hvf/kvm/tcg) selection.

Guest architecture is a real per-VM field (OsDefinition.architecture,
QEMUVMConfig.architecture); acceleration must be derived from it plus the host
architecture, never assumed. This module replaces the various
`platform.system() == 'Darwin' and platform.machine() == 'arm64'` guards that
used to hardcode "only aarch64 guests work" -- normalizing arm64/aarch64
identically regardless of host OS also makes the check correct on Linux ARM64
hosts, which the old Darwin-only guards silently missed.
"""
import logging
import platform

from adare.hypervisor.exceptions import HypervisorException

log = logging.getLogger(__name__)


def normalize_arch(machine: str) -> str:
    """Normalize a `platform.machine()`-style string to 'x86_64' / 'aarch64'.

    Unrecognized values pass through unchanged.
    """
    m = machine.lower()
    if m in ('arm64', 'aarch64'):
        return 'aarch64'
    if m in ('x86_64', 'amd64'):
        return 'x86_64'
    return m


def host_arch() -> str:
    """Return the normalized host CPU architecture."""
    return normalize_arch(platform.machine())


def native_accel() -> str:
    """Return the hardware accelerator available on this host OS."""
    return 'hvf' if platform.system() == 'Darwin' else 'kvm'


def resolve_accel(guest_arch: str, allow_emulation: bool = False) -> str:
    """Resolve the QEMU accelerator for `guest_arch` on the current host.

    Single chokepoint used by both `adare vm create` and `adare experiment
    run`. Returns the native hardware accelerator when the guest architecture
    matches the host; otherwise requires `allow_emulation=True` and returns
    'tcg' (software emulation).

    Raises:
        HypervisorException: If the architectures mismatch and
            `allow_emulation` is False.
    """
    h = host_arch()
    if guest_arch == h:
        return native_accel()
    if not allow_emulation:
        raise HypervisorException(
            f"Host architecture ({h}) cannot hardware-accelerate {guest_arch} guests. "
            "Pass --allow-emulation to use QEMU TCG software emulation instead "
            "(expect a severe slowdown; consider raising experiment/action timeouts)."
        )
    log.warning(f"{guest_arch} guest on {h} host: using TCG (no hardware acceleration).")
    return 'tcg'


def cpu_mode_and_model(accel: str, guest_arch: str) -> tuple[str, str | None]:
    """Return (cpu_mode, cpu_model) for the libvirt <cpu> element.

    Under hardware acceleration, host-passthrough exposes the real host CPU.
    Under TCG there is no host CPU to pass through (especially cross-arch), so
    a generic model is used instead.
    """
    if accel != 'tcg':
        return 'host-passthrough', None
    return 'custom', ('qemu64' if guest_arch == 'x86_64' else 'cortex-a57')
