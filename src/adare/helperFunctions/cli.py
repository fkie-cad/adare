# external imports
from rich.console import Console
from rich.table import Table
import pandas as pd

# setup logging
import logging
log = logging.getLogger(__name__)


def print_df(df: pd.DataFrame, title: str):
    """
    prints a dataframe to the console (rich table)
    (if an entry contains a newline, the entry is split into multiple lines)

    :param df: dataframe to print
    :param title: title of the table
    """
    print('\n')
    console = Console()
    table = Table(title=title)
    for column in df.columns:
        table.add_column(column)
    for row in df.itertuples():
        table.add_row(*row[1:])
    console.print(table)


def print_dict(dictionary: dict, title: str):
    """
    prints a dictionary to the console (rich table)
    (if an entry contains a newline, the entry is split into multiple lines)

    :param dictionary: dictionary to print
    :param title: title of the table
    """
    print('\n')
    console = Console()
    table = Table(title=title)
    table.add_column('key')
    table.add_column('value')
    for key, value in dictionary.items():
        if isinstance(value, str):
            table.add_row(key, value)
        else:
            table.add_row(key, str(value))
    console.print(table)