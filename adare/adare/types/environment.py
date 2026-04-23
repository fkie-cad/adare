# external imports
# configure logging
import logging
from pathlib import Path
from typing import Literal

import attrs
import cattrs

from adare.exceptions import DataStructuringError
from adarelib.helper.yaml import yaml_to_dict

log = logging.getLogger(__name__)


@attrs.define
class PostsetupInstallations:
    """
    Class to store information about installations that should be done after boot but before the experiment.
    """
    name: str
    command: str
    description: str | None = ''
    cwd: str | None = ''
    shell: bool = attrs.field(default=False)


@attrs.define
class OsInfo:
    """
    Operating system information for environments.
    """
    os: str
    platform: Literal['windows', 'linux']
    distribution: str
    version: str = ''
    language: str = ''
    architecture: str = ''
    details: str = ''


@attrs.define
class EnvironmentMetadata:
    """
    Consolidated class to store the configuration of an environment.

    Supports both modern VM-based environments (with OVA files) and legacy Vagrant-based environments.

    Hypervisor Configuration:
        The hypervisor_config field allows hypervisor-specific settings:

        QEMU hypervisor supports:
        - boot_mode: 'bios' or 'uefi' (default: auto-detected based on OS)
            - Windows VMs automatically use 'uefi'
            - Linux VMs automatically use 'bios'
            - Override with explicit boot_mode setting

        Example environment YAML:
            vm: windows-10
            os:
              platform: windows
              os: Windows 10
            hypervisor: qemu
            hypervisor_config:
              boot_mode: uefi  # Optional: override auto-detection
    """
    vm: str
    os: OsInfo

    name: str | None = None
    postsetupinstallations: list[PostsetupInstallations] = attrs.Factory(list)
    tags: list[str] = attrs.Factory(list)
    description: str = attrs.Factory(str)

    vm_type: Literal["auto", "path", "url"] = "auto"

    # Hypervisor configuration
    hypervisor: str = "virtualbox"  # Default hypervisor
    hypervisor_config: dict = attrs.Factory(dict)  # Hypervisor-specific configuration

    # Legacy Vagrant-based environment fields (for backward compatibility)
    vagrantbox: str | None = None

    def __attrs_post_init__(self):
        """Validate that either vm or vagrantbox is specified."""
        if not self.vm and not self.vagrantbox:
            raise ValueError("Either 'vm' or 'vagrantbox' must be specified")

    @property
    def is_vagrant_environment(self) -> bool:
        """Check if this is a legacy Vagrant-based environment."""
        return self.vagrantbox is not None

    @property
    def is_vm_environment(self) -> bool:
        """Check if this is a modern VM-based environment."""
        return self.vm is not None


def parse_environment_file(environment_file: Path) -> EnvironmentMetadata|None:
    environment_dict = yaml_to_dict(environment_file)
    try:
        environment = cattrs.structure(environment_dict, EnvironmentMetadata)
    except cattrs.BaseValidationError as e:
        error_msg = "\n".join(cattrs.transform_error(e))
        raise DataStructuringError(
            log,
            message=f'parsing errors while parsing environment file {environment_file}:{error_msg}',
            possible_solutions=[
                'fix the structure of the environment file',
            ]
        ) from e
    return environment
