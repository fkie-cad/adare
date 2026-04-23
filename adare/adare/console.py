import logging

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from adare.helperfunctions.text import clean_rich_inline_str

console = Console()


def log_print(log: logging.Logger, msg: str, level: str = 'info'):
    if level == 'info':
        log.info(clean_rich_inline_str(msg))
        console.print(msg)


def console_print(msg: str):
    console.print(msg)


def print_success_message(title: str, location: str = '', next_steps: list[str] = None, tip: str = None):
    """Print a formatted success message with next steps using Rich."""
    console.print(f'✅ {title}', style='bold green')
    if location:
        console.print(f'📁 Location: {location}', style='dim')
        console.print()
    if next_steps:
        console.print('📝 Next steps:', style='bold')
        for i, step in enumerate(next_steps, 1):
            console.print(f'   {i}. {step}', style='dim')
        if tip:
            console.print()
            console.print(f'💡 Tip: {tip}', style='italic cyan')

def print_vm_config_panel(title: str, rows: list[tuple[str, str]]):
    """Render a bordered panel with key-value grid for VM configuration."""
    table = Table.grid(padding=(0, 2))
    table.add_column(style='cyan', justify='right')
    table.add_column(style='white')
    for key, value in rows:
        table.add_row(key, value)
    console.print()
    console.print(Panel(
        table,
        title=f'[b gold3]{title}[/b gold3]',
        border_style='blue',
        title_align='left',
        expand=False,
        padding=(0, 2),
    ))


def print_step(message: str):
    """Print a step marker with cyan prefix."""
    console.print(f'  [cyan]>[/cyan] {message}')


def print_section(title: str):
    """Print a phase separator with blue rule."""
    console.print()
    console.print(Rule(title, style='blue', align='left'))


def print_error_message(title: str, details: str = '', next_steps: list[str] = None):
    """Print a formatted error message with next steps using Rich."""
    console.print(f'❌ {title}', style='bold red')
    if details:
        console.print(f'Details: {details}', style='dim')
        console.print()
    if next_steps:
        console.print('📝 Next steps:', style='bold')
        for i, step in enumerate(next_steps, 1):
            console.print(f'   {i}. {step}', style='dim')
