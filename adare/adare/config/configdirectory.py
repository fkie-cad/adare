import logging
import os
import platform
from pathlib import Path

log = logging.getLogger(__name__)


# Overrides the whole state directory (tests point it at a temp dir).
ADARE_HOME_ENV_VAR = 'ADARE_HOME'

# Subdirectories ensure_directories() creates below the appdata directory.
_REQUIRED_SUBDIRS = (
    'state/vms',
    'state/environments',
    'state/testfunctions',
    'os-profiles',
    'vm-templates',
    'icons',
    'isos',
)


def _resolve_appdata_directory(program_name: str = 'adare') -> Path:
    """
    Resolve the tool's appdata directory without touching the filesystem.

    ``$ADARE_HOME`` wins; otherwise ``%APPDATA%\\adare`` on Windows and ``~/.adare`` elsewhere.
    """
    override = os.getenv(ADARE_HOME_ENV_VAR)
    if override:
        return Path(override).expanduser()
    if platform.system() == 'Windows':
        appdata = os.getenv('APPDATA')
        if appdata:
            return Path(appdata) / program_name.lower()
    return Path.home() / f'.{program_name.lower()}'


# Resolve paths at import time without creating directories (no side effects)
APPDATA_DIR: Path = _resolve_appdata_directory()
ADARE_DIR = APPDATA_DIR / 'adare'
ADAREVM_DIR = ADARE_DIR / 'adarevm'
ADARELIB_DIR = ADARE_DIR / 'adarelib'
WEBAPP_FILES: Path = APPDATA_DIR / 'webapp'
WEBAPP_STATIC_FILES: Path = WEBAPP_FILES / 'static'

EXAMPLES_DIR: Path = APPDATA_DIR / 'examples'
PROGRAMS_DIR: Path = APPDATA_DIR / 'programs'
PROG_PARSEANDTEST_DIR: Path = PROGRAMS_DIR / 'ParseAndTest'

TEMPLATES_DIR: Path = APPDATA_DIR / 'templates'
VAGRANTFILE_TEMPLATE: Path = APPDATA_DIR / 'VagrantfileTemplate' / 'VagrantfileMultiMachine'

# Global storage directories
STATE_DIR: Path = APPDATA_DIR / 'state'  # Global state directory
VMS_DIR: Path = STATE_DIR / 'vms'  # Global VM storage
ENVIRONMENTS_DIR: Path = STATE_DIR / 'environments'  # Global environment storage

# Managed QEMU disks, runtime sockets and per-VM configs. They live under ~/.adare on
# every OS (Windows included), unlike the rest of the appdata directory, unless
# $ADARE_HOME relocates everything.
QEMU_STATE_DIR: Path = (APPDATA_DIR if os.getenv(ADARE_HOME_ENV_VAR) else Path.home() / '.adare') / 'qemu'

# QEMU cache directory for ISOs and other large downloads
QEMU_CACHE_DIR: Path = APPDATA_DIR / 'qemu' / 'cache'

# Installer ISOs the user supplies themselves. Searched by name when a recipe
# environment declares `recipe.iso_name` (a consumer-supplied "BYO" ISO, used for
# Windows, whose installer media cannot lawfully be rehosted). Distinct from
# QEMU_CACHE_DIR, which holds *downloaded* ISOs keyed by URL hash and is prunable.
ISO_DIR: Path = APPDATA_DIR / 'isos'

# Cached recipe BASE disks: the OS install before build-time provisioning runs.
# Keyed by the base hash (recipe identity WITHOUT `provision`), so solr4 and solr8
# variants of the same Windows install share one two-hour build, and a failed
# provisioning step is retried with `--reprovision` in minutes instead of hours.
RECIPE_BASE_CACHE_DIR: Path = APPDATA_DIR / 'qemu' / 'cache' / 'recipe-bases'

# Per-build provisioning logs: one file per recipe hash recording every command,
# its exit code, wall time, stdout and stderr — the provenance record worth
# attaching to a published artifact, plus any log_files pulled from a failed step.
RECIPE_BUILD_LOG_DIR: Path = APPDATA_DIR / 'qemu' / 'build-logs'

# OS profiles directory for VM creation definitions
OS_PROFILES_DIR: Path = APPDATA_DIR / 'os-profiles'

# User-supplied Jinja2 templates for VM creation (autoinstall, autounattend)
VM_TEMPLATES_DIR: Path = APPDATA_DIR / 'vm-templates'

# Windows icon library: cached PNGs extracted from targets at runtime.
# Per-OS-profile subdirectories keep icons from different Windows builds
# separate, so an OS upgrade re-extracts rather than reusing stale bitmaps.
ICONS_DIR: Path = APPDATA_DIR / 'icons'

# Version-independent name -> resolver-spec map (shipped in appdata/).
ICON_LIBRARY_FILE: Path = APPDATA_DIR / 'icon-library.yml'


def ensure_directories() -> None:
    """
    Create all required application directories.

    Call this explicitly during application startup instead of relying on
    import-time side effects. This function is idempotent.
    """
    for sub in _REQUIRED_SUBDIRS:
        (APPDATA_DIR / sub).mkdir(parents=True, exist_ok=True)
