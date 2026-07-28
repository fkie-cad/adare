#!/bin/bash
# Make a finished genuine desktop disk ADARE-ready, OFFLINE (no boot, no reinstall).
#
#   provision_adare.sh <disk.qcow2> <ubuntu|kubuntu|fedora>
#
# Installs: qemu-guest-agent (ADARE command channel), cifs-utils + NOPASSWD sudo
# (host share mount), openssh-server, python3-pip, uv (editable path / agent
# fallback). Enables autologin using each distro's DEFAULT session (native
# Wayland where that is the default -- NO X11 forcing), disables auto-updates,
# and best-effort pre-installs adarevm (+adarelib) via pipx so agent-mode is
# ready without the slow first-run source build.
#
# GUI automation on QEMU is host-side (QMP screendump/input-send-event, see
# QEMUHostGUIExecutor), which is display-server agnostic -- so the guest keeps
# its genuine default session and we do NOT force Xorg.
set -eu
DISK="${1:?usage: provision_adare.sh <disk.qcow2> <ubuntu|kubuntu|fedora>}"
FAMILY="${2:?family required: ubuntu | kubuntu | fedora}"
export LIBGUESTFS_BACKEND=direct

# Repo root used to build adarevm/adarelib wheels for the pipx pre-install.
ADARE_REPO="${ADARE_REPO:-/home/miq/Documents/adare/adare}"

# pipx is NOT an apt package on older Ubuntu (18.04 has none); it is bootstrapped
# via pip in the best-effort pre-install step below, so it is not required here.
PKGS="qemu-guest-agent,cifs-utils,openssh-server,curl,python3-pip"
RELABEL=""
SELINUX_FIX=""   # set for fedora only (see case below)

# Disable idle screen-blank / screensaver lock so the desktop stays painted for
# the whole (possibly long) experiment -- a blanked or locked screen breaks both
# host/QMP screendump (uniform black frame) and any GUI automation. GNOME uses a
# dconf system default DB; KDE uses an /etc/xdg kscreenlocker default.
NOBLANK_GNOME='mkdir -p /etc/dconf/profile /etc/dconf/db/local.d && printf "user-db:user\nsystem-db:local\n" > /etc/dconf/profile/user && printf "[org/gnome/desktop/session]\nidle-delay=uint32 0\n\n[org/gnome/desktop/screensaver]\nlock-enabled=false\nidle-activation-enabled=false\n" > /etc/dconf/db/local.d/00-adare-noblank && dconf update'
NOBLANK_KDE='mkdir -p /etc/xdg && printf "[Daemon]\nAutolock=false\nLockOnResume=false\nTimeout=0\n" > /etc/xdg/kscreenlockerrc'

case "$FAMILY" in
  kubuntu)   # KDE Plasma -> SDDM autologin, genuine default session (Wayland on 22.04+)
    AUTOLOGIN='mkdir -p /etc/sddm.conf.d && printf "[Autologin]\nUser=adare\n" > /etc/sddm.conf.d/zz-adare-autologin.conf'
    NOBLANK="$NOBLANK_KDE" ;;
  fedora)    # GNOME on Fedora -> GDM at /etc/gdm (not gdm3); genuine Wayland; SELinux relabel
    AUTOLOGIN='mkdir -p /etc/gdm && printf "[daemon]\nAutomaticLoginEnable=True\nAutomaticLogin=adare\n" > /etc/gdm/custom.conf'
    NOBLANK="$NOBLANK_GNOME"
    # Fedora confines qemu-guest-agent to the SELinux domain virt_qemu_ga_t,
    # which -- even as root -- is denied mkdir /, mount, etc. That blocks the
    # virtio-fs share mount ADARE drives through the agent. Make ONLY that one
    # domain permissive (system stays enforcing everywhere else) so the agent
    # can set up shares. semanage ships in policycoreutils-python-utils.
    SELINUX_FIX='semanage permissive -a virt_qemu_ga_t'
    PKGS="$PKGS,policycoreutils-python-utils"
    RELABEL="--selinux-relabel" ;;
  ubuntu|*)  # GNOME on Ubuntu -> GDM3, genuine default session (Wayland where default).
    # Also drop any stale ubuntu-xorg AccountsService override left by the old
    # X11-forcing provisioner so the session reverts to the genuine default.
    AUTOLOGIN='mkdir -p /etc/gdm3 && printf "[daemon]\nAutomaticLoginEnable=true\nAutomaticLogin=adare\n" > /etc/gdm3/custom.conf; rm -f /var/lib/AccountsService/users/adare'
    NOBLANK="$NOBLANK_GNOME" ;;
esac

# --- Best-effort: build adarevm + adarelib wheels on the host for pipx pre-install ---
# If the build fails or uv is missing, we simply skip the copy-in/pipx steps; the
# compat test's shared-source `uv run adarevm` fallback still exercises agent mode.
WHEEL_ARGS=()
WHEEL_STAGE=""
if command -v uv >/dev/null 2>&1 && [ -d "$ADARE_REPO/adarevm" ] && [ -d "$ADARE_REPO/adarelib" ]; then
  WHEEL_STAGE="$(mktemp -d /tmp/adare-wheels.XXXXXX)"
  if uv build --wheel --directory "$ADARE_REPO/adarelib" --out-dir "$WHEEL_STAGE" >/dev/null 2>&1 \
     && uv build --wheel --directory "$ADARE_REPO/adarevm" --out-dir "$WHEEL_STAGE" >/dev/null 2>&1 \
     && ls "$WHEEL_STAGE"/adarevm*.whl >/dev/null 2>&1 \
     && ls "$WHEEL_STAGE"/adarelib*.whl >/dev/null 2>&1; then
    # Copy the whole staging dir into the guest and pipx-install as user 'adare'
    # (idempotent via --force). pipx puts adarevm in ~/.local/pipx/venvs/adarevm
    # and manages PATH via ensurepath.
    WHEEL_ARGS+=( --copy-in "$WHEEL_STAGE:/opt" )
    WHEEL_ARGS+=( --run-command "rm -rf /opt/adare-wheels && mv /opt/$(basename "$WHEEL_STAGE") /opt/adare-wheels" )
    WHEEL_ARGS+=( --run-command 'su - adare -c "python3 -m pip install --user pipx >/dev/null 2>&1 || true; python3 -m pipx ensurepath >/dev/null 2>&1; python3 -m pipx install --force /opt/adare-wheels/adarevm-*.whl && python3 -m pipx inject --force adarevm /opt/adare-wheels/adarelib-*.whl" || echo "CLAUDE: pipx pre-install skipped (fallback to uv run)"' )
    echo "CLAUDE: staged adarevm/adarelib wheels for pipx pre-install ($WHEEL_STAGE)"
  else
    echo "CLAUDE: wheel build failed; skipping pipx pre-install (uv-run fallback stays)"
  fi
else
  echo "CLAUDE: uv/repo unavailable; skipping pipx pre-install (uv-run fallback stays)"
fi

SELINUX_ARGS=()
[ -n "$SELINUX_FIX" ] && SELINUX_ARGS+=( --run-command "$SELINUX_FIX" )

virt-customize -a "$DISK" $RELABEL \
  --install "$PKGS" \
  --run-command 'systemctl enable qemu-guest-agent 2>/dev/null || true' \
  --run-command 'systemctl enable ssh 2>/dev/null || systemctl enable sshd 2>/dev/null || true' \
  --run-command 'echo "adare ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/adare && chmod 440 /etc/sudoers.d/adare' \
  --run-command 'command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh' \
  --run-command "$AUTOLOGIN" \
  --run-command "$NOBLANK" \
  "${SELINUX_ARGS[@]}" \
  "${WHEEL_ARGS[@]}" \
  --run-command 'systemctl disable unattended-upgrades apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true' \
  --run-command 'mkdir -p /home/adare/.config && echo yes > /home/adare/.config/gnome-initial-setup-done && chown -R adare:adare /home/adare/.config' \
  --run-command 'echo adare-ready > /etc/adare-ready'

[ -n "$WHEEL_STAGE" ] && rm -rf "$WHEEL_STAGE"
echo "PROVISION_OK: $DISK ($FAMILY)"
