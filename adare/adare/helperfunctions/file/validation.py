# configure logging
import logging
from pathlib import Path

from tqdm import tqdm

log = logging.getLogger(__name__)

def validate_tarfile_with_progress(
    file_path: Path,
    description: str | None = None,
    quiet: bool = False
) -> bool:
    """
    Validate if file is a valid tar file with progress indication.

    Args:
        file_path: Path to file
        description: Optional description for progress bar
        quiet: If True, suppress progress bar

    Returns:
        True if valid tar file, False otherwise
    """
    import tarfile

    if quiet:
        log.debug(f'Validating tar file {file_path} in silent mode')
        result = tarfile.is_tarfile(file_path)
        log.debug(f'Tar validation completed for {file_path}: {result}')
        return result

    # For tar validation, we'll show a spinner-style progress since we can't predict progress
    desc = description or f"Validating {file_path.name}"
    log.debug(f'Validating tar file {file_path} with progress indication')

    with tqdm(desc=desc, unit='', bar_format='{desc}: {elapsed}') as bar:
        try:
            result = tarfile.is_tarfile(file_path)
            bar.set_description(f"{desc} - {'Valid' if result else 'Invalid'}")
        except Exception as e:
            bar.set_description(f"{desc} - Error: {str(e)}")
            log.error(f'Error validating tar file {file_path}: {e}')
            return False

    log.debug(f'Tar validation completed for {file_path}: {result}')
    return result
