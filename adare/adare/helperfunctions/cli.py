# external imports
# setup logging
import logging

import pandas as pd
from rich.console import Console
from rich.table import Table

log = logging.getLogger(__name__)


def print_df(df: pd.DataFrame, title: str):
    """
    prints a dataframe to the console (rich table)
    (if an entry contains a newline, the entry is split into multiple lines)

    :param df: dataframe to print
    :param title: title of the table
    """
    console = Console()
    table = Table(title=title)
    for column in df.columns:
        table.add_column(column)
    for row in df.itertuples():
        table.add_row(*row[1:])
    console.print(table)


def print_dict(dictionary: dict, title: str, header: list = None):
    """
    prints a dictionary to the console (rich table)
    (if an entry contains a newline, the entry is split into multiple lines)

    :param dictionary: dictionary to print
    :param title: title of the table
    :param header: optional list containing the header of the table (column names)
    """
    console = Console()
    table = Table(title=title)
    if not header or len(header) < 2:
        table.add_column('key')
        table.add_column('value')
    else:
        table.add_column(header[0])
        table.add_column(header[1])

    for key, value in dictionary.items():
        if isinstance(value, str):
            table.add_row(key, value)
        else:
            table.add_row(key, str(value))
    console.print(table)

def get_status_icon(status: str, include_text: bool = True):
    """
    returns the icon for a given status

    :param status: status to get the icon for (unknown, published, in request, not published, success, in progress, failed, warning, not reached)
    :param include_text: if true, the status text is included in the return value
    :return: icon for the status to be printed by rich
    """
    icon = ''
    if status == 'unknown':
        icon = ':thinking_face:'
    elif status == 'published':
        icon = ':white_check_mark:'
    elif status == 'in request':
        icon = ':pending:'
    elif status == 'not published':
        icon = ':pencil:'
    elif status == 'success':
        icon = ':white_check_mark:'
    elif status == 'in progress':
        icon = ':soon:'
    elif status == 'failed':
        icon = ':x:'
    elif status == 'warning':
        icon = ':exclamation:'
    elif status == 'not reached':
        icon = ':white_exclamation_mark:'
    else:
        log.error(f'unknown status {status}')

    if include_text:
        return f'{icon} {status}'
    return icon

