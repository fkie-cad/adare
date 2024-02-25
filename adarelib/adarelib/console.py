from rich.console import Console
import logging
from adarelib.helperfunctions.text import clean_rich_inline_str

console = Console()


def log_print(log: logging.Logger, msg: str, level: str = 'info'):
    if level == 'info':
        log.info(clean_rich_inline_str(msg))
        console.print(msg)


def console_print(msg: str):
    console.print(msg)
