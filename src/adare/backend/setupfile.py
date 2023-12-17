# external imports
from pathlib import Path
import cattrs

# internal imports
from adare.helperFunctions.yaml import yaml_to_dict
from adare.backend.attrs_classes import EnvironmentSetup, UsbDevice, ExperimentMetadata

# setup logging
import logging
log = logging.getLogger(__name__)


def load_setupfile(setup_file: Path) -> EnvironmentSetup or None:
    """
    loads the setup file for the environment
    :param setup_file: path to the setup file
    :return:
    """
    try:
        setup_dict = yaml_to_dict(setup_file)
    except FileNotFoundError:
        log.error(f'setup file {setup_file} for the environment not found')
        return None
    log.debug(f'read setup file ({setup_file}) to dictionary was successful')
    try:
        setup = cattrs.structure(setup_dict, EnvironmentSetup)
    except cattrs.BaseValidationError as e:
        log.error(f'parsing errors while parsing environment setup file {setup_file}:')
        exec_msgs = cattrs.transform_error(e)
        for msg in exec_msgs:
            log.error(msg)
        return None
    log.debug(f'environment setup file {setup_file} got successfully parsed')
    return setup


def load_experiment_metadata(metadata_file: Path) -> ExperimentMetadata or None:
    """
    loads the metadata file for the experiment
    :param metadata_file: path to the metadata file
    :return:
    """
    try:
        metadata_dict = yaml_to_dict(metadata_file)
    except FileNotFoundError:
        log.error(f'metadata file {metadata_file} for the experiment not found')
        return None
    log.debug(f'read metadata file ({metadata_file}) to dictionary was successful')
    try:
        metadata: ExperimentMetadata = cattrs.structure(metadata_dict, ExperimentMetadata)
    except cattrs.BaseValidationError as e:
        log.error(f'parsing errors while parsing experiment metadata file {metadata_file}:')
        exec_msgs = cattrs.transform_error(e)
        for msg in exec_msgs:
            log.error(msg)
        return None
    log.debug(f'experiment metadata file {metadata_file} got successfully parsed')
    if metadata:
        # used to ensure that the users of the smb shares are also users for smb
        metadata.fix_smb_users()
    return metadata



# def load_usb_setupfile(setup_file: Path) -> dict or None:
#     """
#     loads the setup file for the environment
#     :param setup_file: path to the setup file
#     :return:
#     """
#     devices = []
#     try:
#         data = yaml_to_dict(setup_file)
#     except FileNotFoundError:
#         log.error(f'setup file {setup_file} for the environment not found')
#         return None
#     log.debug(f'read setup file ({setup_file}) to dictionary was successful')
#     try:
#         if type(data) is list:
#             devices = cattrs.structure(data, list[UsbDevice])
#         else:
#             devices = [cattrs.structure(data, UsbDevice)]
#     except cattrs.BaseValidationError as e:
#         log.error(f'parsing errors while parsing environment setup file {setup_file}:')
#         exec_msgs = cattrs.transform_error(e)
#         for msg in exec_msgs:
#             log.error(msg)
#         return None
#     log.debug(f'environment setup file {setup_file} got successfully parsed')
#     return devices
#
#
# def __parse_networkdrive_entry(drive: dict):
#     smb, nfs = None, None
#     if not 'type' in drive.keys():
#         log.error(f'no type specified for network drive ({drive})')
#         return None, None
#     if drive['type'] == 'smb':
#         try:
#             smb = cattrs.structure(drive, SMBShare)
#         except cattrs.BaseValidationError as e:
#             log.error(f'could not parse network drive entry ({drive})')
#             exec_msgs = cattrs.transform_error(e)
#             for msg in exec_msgs:
#                 log.error(msg)
#     elif drive['type'] == 'nfs':
#         try:
#             nfs = cattrs.structure(drive, NFSShare)
#         except cattrs.BaseValidationError as e:
#             log.error(f'could not parse network drive entry ({drive})')
#             exec_msgs = cattrs.transform_error(e)
#             for msg in exec_msgs:
#                 log.error(msg)
#     else:
#         log.error(f'unknown network drive type ({drive["type"]})')
#     return smb, nfs
#
#
# def load_networkdrive_setupfile(setup_file: Path) -> (SMBConfiguration, NFSConfiguration) or None:
#     """
#     loads the setup file for the environment
#     :param setup_file: path to the setup file
#     :return:
#     """
#     smb_drive, nfs_drive = None, None
#     try:
#         data = yaml_to_dict(setup_file)
#     except FileNotFoundError:
#         log.error(f'setup file {setup_file} for the environment not found')
#         return None
#     log.debug(f'read setup file ({setup_file}) to dictionary was successful')
#     if type(data) is list:
#         for drive in data:
#             smb, nfs = __parse_networkdrive_entry(drive)
#             if smb:
#                 smb_shares.append(smb)
#             if nfs:
#                 nfs_shares.append(nfs)
#     else:
#         smb, nfs = __parse_networkdrive_entry(data)
#         if smb:
#             smb_shares.append(smb)
#         if nfs:
#             nfs_shares.append(nfs)
#     log.debug(f'environment setup file {setup_file} got successfully parsed')
#     return smb_drive, nfs_drive

