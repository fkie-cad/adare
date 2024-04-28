# external imports
from pathlib import Path
import vagrant
import prettytable

# configure logging
import logging
log = logging.getLogger(__name__)


def get_available_boxes():
    vg = vagrant.Vagrant()
    return vg.box_list()


def is_box(name: str):
    """
        checks whether a vagrant box exists
    """
    available_boxes = get_available_boxes()
    return any(box.name == name for box in available_boxes)


def print_available_boxes():
    """
        print all available boxes in a table
    """
    available_boxes = get_available_boxes()
    table = prettytable.PrettyTable()
    table.field_names = ['name', 'provider', 'version']
    for box in available_boxes:
        table.add_row([box.name, box.provider, box.version])
    print(table)


def box_add(name: str, path: Path):
    vg = vagrant.Vagrant()
    vg.box_add(name, path.as_posix())


def box_remove(name: str, provider: str):
    vg = vagrant.Vagrant()
    vg.box_remove(name, provider)


def box_is_alive(box_id: str):
    vg = vagrant.Vagrant()
    return vg.status(box_id)
