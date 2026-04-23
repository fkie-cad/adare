"""
Experiment metadata types for ADARE.

This module contains types for experiment configurations and metadata.
Moved from adare.types.backend to consolidate application-specific types.
"""


import attrs

from .backend import Disk, NFSConfiguration, SMBConfiguration, UsbDevice


@attrs.define
class ExperimentMetadata:
    """
    Class to store the metadata of an experiment.
    """
    environments: list[str] = attrs.Factory(list)
    tags: list[str] = attrs.Factory(list)
    smb: SMBConfiguration | None = None
    nfs: NFSConfiguration | None = None
    usb: list[UsbDevice] = attrs.Factory(list)
    disk: list[Disk] = attrs.Factory(list)
    description: str = attrs.Factory(str)

    def fix_smb_users(self):
        """
        Add all users of the SMB shares to the SMB users.
        """
        if self.smb:
            for share in self.smb.shares:
                if share.user not in self.smb.users:
                    self.smb.add_user(share.user)
