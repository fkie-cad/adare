"""What a playbook-installed desktop needs before ADARE can drive it.

``install_mode: playbook`` replays a genuine GUI installer, so the disk it yields
is a stock desktop: no QEMU guest agent, a login screen on every boot, a screen
that locks and blanks when idle, and a first-login welcome wizard over the
desktop. ``adare vm test`` and every experiment then wait for a guest agent that
can never answer. For ``--setup base`` and up the creator therefore finishes the
job after ``verify_steps`` in two halves:

1. **Bootstrap** (:func:`bootstrap_steps`): the only part that has to be typed.
   Without an agent the host cannot run anything in the guest, so the engine
   switches to a text console, logs in and installs ``qemu-guest-agent`` with one
   command. A text console looks the same under GNOME and KDE, so no per-desktop
   terminal handling is needed. A profile may replace these steps with its own
   ``bootstrap_steps``.
2. **Provisioning** (:func:`provision_steps`): everything else, one ``guest-exec``
   per step, each with a real exit code, so a failing step fails ``vm create``
   instead of leaving a half-ready image behind. It is the in-repo form of the
   ``provision_adare.sh`` that readied the genuine desktop images by hand. The
   desktop steps (no lock, no welcome wizard) are shared with the readiness
   pass of the unattended creators, see guest_readiness.

The guest keeps its genuine default session (Wayland where the release defaults
to it): ADARE drives QEMU desktops from the host over QMP, which needs no X11.
"""

from __future__ import annotations

from adare.hypervisor.qemu.vm_creator.guest_readiness import (
    AUTOLOGIN_CHECK_LINUX,
    GUEST_PASSWORD,
    GUEST_USER,
    NO_LOCK,
    NO_WELCOME,
)
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition, SetupLevel
from adare.types.environment import ProvisionCommand

__all__ = ['AUTOLOGIN_CHECK_LINUX', 'bootstrap_steps', 'provision_steps']

# Typed on the text console, so it stays one line. The retry loop rides out the
# first-boot apt lock and a mirror hiccup; the guest agent itself is then started
# by udev because the creator boots the guest with its virtio-serial port.
AGENT_INSTALL_COMMAND = (
    f"echo {GUEST_PASSWORD} | sudo -S sh -c '"
    'for i in 1 2 3 4 5; do '
    'apt-get -o DPkg::Lock::Timeout=300 update && '
    'DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=300 install -y qemu-guest-agent '
    '&& break; sleep 15; done; '
    "systemctl start qemu-guest-agent'"
)


def bootstrap_steps(os_def: OsDefinition) -> list[dict]:
    """Engine steps that install the guest agent from a text console."""
    if os_def.bootstrap_steps:
        return list(os_def.bootstrap_steps)
    return [
        {'action': 'key', 'keys': ['ctrl', 'alt', 'f3'], 'note': 'switch to a text console'},
        {'action': 'wait_stable', 'settle': 3, 'timeout': 60},
        {'action': 'type', 'text': f'{GUEST_USER}\n', 'note': 'console login'},
        {'action': 'wait', 'seconds': 3},
        {'action': 'type', 'text': f'{GUEST_PASSWORD}\n'},
        {'action': 'wait', 'seconds': 5},
        {'action': 'type', 'text': f'{AGENT_INSTALL_COMMAND}\n', 'note': 'install qemu-guest-agent'},
    ]


_APT = 'DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=300 -q'

_SUDO = ProvisionCommand(
    name='passwordless sudo',
    shell='bash',
    timeout_minutes=5,
    command=f"printf '%s ALL=(ALL) NOPASSWD:ALL\\n' {GUEST_USER} > /etc/sudoers.d/adare && "
    'chmod 440 /etc/sudoers.d/adare && visudo -cf /etc/sudoers.d/adare',
)

# cifs-utils: the SMB share fallback mounts with mount.cifs.
_PACKAGES = ProvisionCommand(
    name='base packages',
    shell='bash',
    timeout_minutes=20,
    command=f'{_APT} update && {_APT} install -y cifs-utils openssh-server curl',
)

# The session type is left as the release ships it; only the greeter is skipped.
_AUTOLOGIN = ProvisionCommand(
    name='automatic login',
    shell='bash',
    timeout_minutes=5,
    command=f"""set -e
if [ -d /etc/gdm3 ]; then
  cat > /etc/gdm3/custom.conf <<'EOF'
[daemon]
AutomaticLoginEnable=true
AutomaticLogin={GUEST_USER}
EOF
elif command -v sddm >/dev/null; then
  mkdir -p /etc/sddm.conf.d
  cat > /etc/sddm.conf.d/adare-autologin.conf <<'EOF'
[Autologin]
User={GUEST_USER}
Session=plasma.desktop
Relogin=false
EOF
else
  echo 'neither GDM nor SDDM found' >&2
  exit 1
fi""",
)

# Background apt runs hold the dpkg lock and change the system mid-experiment,
# and their update prompts pop up over the desktop.
_NO_AUTO_UPDATES = ProvisionCommand(
    name='no automatic updates',
    shell='bash',
    timeout_minutes=5,
    command="""set -e
for unit in apt-daily.timer apt-daily-upgrade.timer unattended-upgrades.service; do
  if [ -n "$(systemctl list-unit-files --no-legend "$unit")" ]; then
    systemctl disable --now "$unit"
  fi
done""",
)

_PYTHON = ProvisionCommand(
    name='python3-pip', shell='bash', timeout_minutes=20, command=f'{_APT} install -y python3-pip'
)


def _uv_step(architecture: str) -> ProvisionCommand:
    """Standalone uv: the agent launcher builds its venv with it when the
    system Python is older than adarevm's 3.10 (Ubuntu 18.04 / 20.04)."""
    triple = f'{architecture}-unknown-linux-gnu'
    return ProvisionCommand(
        name='uv',
        shell='bash',
        timeout_minutes=10,
        command=f"""set -eo pipefail
cd /tmp
curl -LsSf https://github.com/astral-sh/uv/releases/latest/download/uv-{triple}.tar.gz | tar xz
install -o root -g root -m 755 uv-{triple}/uv uv-{triple}/uvx /usr/local/bin/
rm -rf uv-{triple}
/usr/local/bin/uv --version""",
    )


def provision_steps(setup_level: SetupLevel, architecture: str) -> list[ProvisionCommand]:
    """The guest-agent steps for ``setup_level``; empty for ``bare``."""
    if setup_level < SetupLevel.BASE:
        return []
    steps = [_SUDO, _PACKAGES, _AUTOLOGIN, NO_LOCK, NO_WELCOME, _NO_AUTO_UPDATES]
    if setup_level >= SetupLevel.FULL:
        steps += [_PYTHON, _uv_step(architecture)]
    return steps
