# external imports
from typing import Literal, Optional
import attrs
from pathlib import Path
import cattrs
from adare.exceptions import DataStructuringError
from adarelib.helper.yaml import yaml_to_dict

# configure logging
import logging
log = logging.getLogger(__name__)


@attrs.define
class PostsetupInstallations:
    """
    Class to store information about installations that should be done after boot but before the experiment.
    """
    name: str
    command: str
    description: Optional[str] = ''
    cwd: Optional[str] = ''
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
    """
    vm: str

    name: Optional[str]
    os: OsInfo
    postsetupinstallations: list[PostsetupInstallations] = attrs.Factory(list)
    tags: list[str] = attrs.Factory(list)
    description: str = attrs.Factory(str)
    
    vm_type: Literal["path", "url", "ulid", "name"] = "path"
    
    # Legacy Vagrant-based environment fields (for backward compatibility)
    vagrantbox: Optional[str] = None
    
    def __post_init__(self):
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