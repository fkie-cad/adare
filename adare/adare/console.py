from rich.console import Console
import logging
from adare.helperfunctions.text import clean_rich_inline_str

console = Console()


def log_print(log: logging.Logger, msg: str, level: str = 'info'):
    if level == 'info':
        log.info(clean_rich_inline_str(msg))
        console.print(msg)


def console_print(msg: str):
    console.print(msg)


def print_success_message(title: str, location: str, next_steps: list[str], tip: str = None):
    """Print a formatted success message with next steps using Rich."""
    console.print(f'✅ {title}', style='bold green')
    console.print(f'📁 Location: {location}', style='dim')
    console.print()
    console.print('📝 Next steps:', style='bold')
    for i, step in enumerate(next_steps, 1):
        console.print(f'   {i}. {step}', style='dim')
    if tip:
        console.print()
        console.print(f'💡 Tip: {tip}', style='italic cyan')
