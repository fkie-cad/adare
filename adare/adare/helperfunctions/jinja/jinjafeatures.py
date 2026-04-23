# external imports
# configure logging
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

log = logging.getLogger(__name__)


def init_jinja_environment(template_folder: Path):
    if not template_folder.is_dir() or not template_folder:
        return None
    try:
        return Environment(
            loader=FileSystemLoader(template_folder.as_posix()),
            autoescape=select_autoescape()
        )
    except FileNotFoundError or OSError as e:
        log.error(e)
        return None
