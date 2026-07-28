# external imports
# configure logging
import logging
import os
import platform
from pathlib import Path

# internal imports

log = logging.getLogger(__name__)


def __get_default_appdata_directory(create_if_missing: bool = False, program_name: str = 'adare') -> Path | None:
    """
    get the default config directory for the tool

    :param create_if_missing: if True, the directory will be created if it does not exist
    :param program_name: the name of the program
    :return:
    """
    system = platform.system()
    if system == 'Windows':
        appdata_path = Path(os.getenv('APPDATA'))
        appdata_path = appdata_path / program_name.lower()
    elif system in ("Linux", "Darwin"):
        appdata_path = Path(f'~/.{program_name.lower()}/').expanduser()
        if not appdata_path.exists():
            appdata_path.mkdir(parents=False)
    else:
        print(f'the os {system} is not supported by the tool')
        return None
    if create_if_missing:
        appdata_path.mkdir(parents=False, exist_ok=True)
        # Create state directory structure
        state_dir = appdata_path / 'state'
        state_dir.mkdir(exist_ok=True, parents=True)
        (state_dir / 'vms').mkdir(exist_ok=True, parents=True)
        (state_dir / 'environments').mkdir(exist_ok=True, parents=True)
        (state_dir / 'testfunctions').mkdir(exist_ok=True, parents=True)
        (appdata_path / 'os-profiles').mkdir(exist_ok=True, parents=True)
        (appdata_path / 'vm-templates').mkdir(exist_ok=True, parents=True)
        (appdata_path / 'icons').mkdir(exist_ok=True, parents=True)
        (appdata_path / 'isos').mkdir(exist_ok=True, parents=True)
    if not appdata_path.is_dir():
        print(f'the appdata directory ({appdata_path}) of the tool is missing')
        return None
    return appdata_path


# Resolve paths at import time without creating directories (no side effects)
APPDATA_DIR: Path = __get_default_appdata_directory(create_if_missing=False)
ADARE_DIR = APPDATA_DIR/'adare'
ADAREVM_DIR = ADARE_DIR/'adarevm'
ADARELIB_DIR = ADARE_DIR/'adarelib'
WEBAPP_FILES: Path = APPDATA_DIR/'webapp'
WEBAPP_STATIC_FILES: Path = WEBAPP_FILES/'static'

EXAMPLES_DIR: Path = APPDATA_DIR/'examples'
PROGRAMS_DIR: Path = APPDATA_DIR/'programs'
PROG_PARSEANDTEST_DIR: Path = PROGRAMS_DIR/'ParseAndTest'

TEMPLATES_DIR: Path = APPDATA_DIR/'templates'
NETWORKDRIVE_TEMPLATES_DIR: Path = APPDATA_DIR/'networkdrive'/'templates'
VAGRANTFILE_TEMPLATE: Path = APPDATA_DIR/'VagrantfileTemplate'/'VagrantfileMultiMachine'

# Global storage directories
STATE_DIR: Path = APPDATA_DIR/'state'  # Global state directory
VMS_DIR: Path = STATE_DIR/'vms'  # Global VM storage
ENVIRONMENTS_DIR: Path = STATE_DIR/'environments'  # Global environment storage

# QEMU cache directory for ISOs and other large downloads
QEMU_CACHE_DIR: Path = APPDATA_DIR/'qemu'/'cache'

# Installer ISOs the user supplies themselves. Searched by name when a recipe
# environment declares `recipe.iso_name` (a consumer-supplied "BYO" ISO, used for
# Windows, whose installer media cannot lawfully be rehosted). Distinct from
# QEMU_CACHE_DIR, which holds *downloaded* ISOs keyed by URL hash and is prunable.
ISO_DIR: Path = APPDATA_DIR/'isos'

# Cached recipe BASE disks: the OS install before build-time provisioning runs.
# Keyed by the base hash (recipe identity WITHOUT `provision`), so solr4 and solr8
# variants of the same Windows install share one two-hour build, and a failed
# provisioning step is retried with `--reprovision` in minutes instead of hours.
RECIPE_BASE_CACHE_DIR: Path = APPDATA_DIR/'qemu'/'cache'/'recipe-bases'

# Per-build provisioning logs: one file per recipe hash recording every command,
# its exit code, wall time, stdout and stderr — the provenance record worth
# attaching to a published artifact, plus any log_files pulled from a failed step.
RECIPE_BUILD_LOG_DIR: Path = APPDATA_DIR/'qemu'/'build-logs'

# OS profiles directory for VM creation definitions
OS_PROFILES_DIR: Path = APPDATA_DIR/'os-profiles'

# User-supplied Jinja2 templates for VM creation (autoinstall, autounattend)
VM_TEMPLATES_DIR: Path = APPDATA_DIR/'vm-templates'

# Windows icon library: cached PNGs extracted from targets at runtime.
# Per-OS-profile subdirectories keep icons from different Windows builds
# separate, so an OS upgrade re-extracts rather than reusing stale bitmaps.
ICONS_DIR: Path = APPDATA_DIR/'icons'

# Version-independent name -> resolver-spec map (shipped in appdata/).
ICON_LIBRARY_FILE: Path = APPDATA_DIR/'icon-library.yml'


def ensure_directories() -> None:
    """
    Create all required application directories.

    Call this explicitly during application startup instead of relying on
    import-time side effects. This function is idempotent.
    """
    __get_default_appdata_directory(create_if_missing=True)


