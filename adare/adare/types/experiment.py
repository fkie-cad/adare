"""
Experiment metadata types for ADARE.

This module contains types for experiment configurations and metadata.
Moved from adare.types.backend to consolidate application-specific types.
"""

import attrs

from .backend import Disk, NFSConfiguration, SMBConfiguration, UsbDevice

# OCR engines/languages the cv-server offers (adare_cv_server.constants.OCRProfiles;
# duplicated because adare must not hard-depend on the cv-server package).
OCR_ENGINES = ('rapidocr', 'paddle')
OCR_LANGS = ('latin', 'en')


@attrs.define
class OcrSettings:
    """Per-experiment OCR pin (``ocr:`` in metadata.yml); unset fields use the global default.

    Pin ``engine: paddle`` to keep an existing experiment on the legacy OCR profile.
    """

    engine: str | None = attrs.field(
        default=None, validator=attrs.validators.optional(attrs.validators.in_(OCR_ENGINES))
    )
    lang: str | None = attrs.field(default=None, validator=attrs.validators.optional(attrs.validators.in_(OCR_LANGS)))


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
    ocr: OcrSettings | None = None

    def fix_smb_users(self):
        """
        Add all users of the SMB shares to the SMB users.
        """
        if self.smb:
            for share in self.smb.shares:
                if share.user not in self.smb.users:
                    self.smb.add_user(share.user)
