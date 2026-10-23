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

__all__ = ['AUTOLOGIN_CHECK_LINUX', 'DECLARATIVE_DISTRIBUTIONS', 'bootstrap_steps', 'provision_steps']

# Typed on the text console, so it stays one line and holds no single quote
# inside the sh -c script. It covers apt (with a retry loop for the first-boot
# lock and mirror hiccups), dnf, zypper and pacman. The agent is then started by
# udev, since the guest boots with its virtio-serial port; `systemctl start`
# covers distributions that do not wire that up.
AGENT_INSTALL_COMMAND = (
    f"echo {GUEST_PASSWORD} | sudo -S sh -c '"
    'if command -v apt-get >/dev/null; then '
    'for i in 1 2 3 4 5; do apt-get -o DPkg::Lock::Timeout=300 update && '
    'DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=300 install -y qemu-guest-agent '
    '&& break; sleep 15; done; '
    'elif command -v dnf >/dev/null; then dnf -y install qemu-guest-agent; '
    'elif command -v zypper >/dev/null; then zypper --non-interactive install qemu-guest-agent; '
    'elif command -v pacman >/dev/null; then pacman -Sy --noconfirm --needed qemu-guest-agent; fi; '
    "systemctl enable qemu-guest-agent; systemctl start qemu-guest-agent'"
)

# Distributions whose packages are declared, not installed: the console command
# above cannot work there, so the creator explains the change instead.
DECLARATIVE_DISTRIBUTIONS = {
    'nixos': (
        'NixOS installs nothing imperatively. Add to /etc/nixos/configuration.nix:\n'
        '      services.qemuGuest.enable = true;\n'
        '      services.displayManager.autoLogin = { enable = true; user = "adare"; };\n'
        '    then run `sudo nixos-rebuild switch`, shut down, and run `adare vm test`.'
    ),
}


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


# Prefixed to every step that installs packages.
_PKG = """pkg_install() {
  if command -v apt-get >/dev/null; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get -o DPkg::Lock::Timeout=300 -q update && apt-get -o DPkg::Lock::Timeout=300 -q install -y "$@"
  elif command -v dnf >/dev/null; then dnf -y install "$@"
  elif command -v zypper >/dev/null; then zypper --non-interactive install "$@"
  elif command -v pacman >/dev/null; then pacman -Sy --noconfirm --needed "$@"
  else echo 'no supported package manager (apt, dnf, zypper, pacman)' >&2; return 1
  fi
}
"""

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
    command=_PKG
    + """set -e
if command -v apt-get >/dev/null || command -v dnf >/dev/null; then ssh=openssh-server; else ssh=openssh; fi
pkg_install cifs-utils "$ssh" curl""",
)

# Configures the display manager that is actually enabled. The session type is
# left as the distribution ships it; only the greeter is skipped.
_AUTOLOGIN = ProvisionCommand(
    name='automatic login',
    shell='bash',
    timeout_minutes=5,
    command=f"""set -e
dm=$(basename "$(readlink -f /etc/systemd/system/display-manager.service 2>/dev/null)" .service)
case "$dm" in
  gdm|gdm3)
    conf=/etc/gdm3/custom.conf
    [ -d /etc/gdm3 ] || conf=/etc/gdm/custom.conf
    cat > "$conf" <<'EOF'
[daemon]
AutomaticLoginEnable=true
AutomaticLogin={GUEST_USER}
EOF
    ;;
  sddm)
    mkdir -p /etc/sddm.conf.d
    cat > /etc/sddm.conf.d/adare-autologin.conf <<'EOF'
[Autologin]
User={GUEST_USER}
Session=plasma.desktop
Relogin=false
EOF
    ;;
  lightdm)
    mkdir -p /etc/lightdm/lightdm.conf.d
    cat > /etc/lightdm/lightdm.conf.d/50-adare-autologin.conf <<'EOF'
[Seat:*]
autologin-user={GUEST_USER}
autologin-user-timeout=0
EOF
    groupadd -f autologin
    usermod -aG autologin {GUEST_USER}
    ;;
  *)
    echo "unsupported display manager '${{dm:-none}}' (supported: GDM, SDDM, LightDM)" >&2
    exit 1
    ;;
esac""",
)

# Background package runs hold the package lock and change the system
# mid-experiment, and their update prompts pop up over the desktop.
_NO_AUTO_UPDATES = ProvisionCommand(
    name='no automatic updates',
    shell='bash',
    timeout_minutes=5,
    command="""set -e
for unit in apt-daily.timer apt-daily-upgrade.timer unattended-upgrades.service dnf-makecache.timer; do
  if [ -n "$(systemctl list-unit-files --no-legend "$unit")" ]; then
    systemctl disable --now "$unit"
  fi
done""",
)

_PYTHON = ProvisionCommand(
    name='python3-pip',
    shell='bash',
    timeout_minutes=20,
    command=_PKG + 'if command -v pacman >/dev/null; then pkg_install python-pip; else pkg_install python3-pip; fi',
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
