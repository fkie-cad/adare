# external imports
import shutil
from retry import retry
from pathlib import Path

# configure logging
import logging
log = logging.getLogger(__name__)


@retry(delay=1, tries=5)
def safe_rm_tree(path: str) -> int:
    if not Path(path).is_file() and not Path(path).is_dir():
        log.error(f'{path} is neither a directory and nor a file and can therefore not be deleted')
        return -1
    try:
        shutil.rmtree(path)
        return 0
    except PermissionError or OSError as e:
        log.warning(f'{path} could not be deleted caused by the following exception')
        log.warning(e, exc_info=True)
        raise
