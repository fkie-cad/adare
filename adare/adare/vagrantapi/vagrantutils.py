# external imports
from pathlib import Path
import vagrant
import prettytable
import requests
import subprocess

# configure logging
import logging
log = logging.getLogger(__name__)


def get_available_boxes():
    vg = vagrant.Vagrant()
    return vg.box_list()


def remote_box_exists(owner: str, name: str):
    """
        checks whether a box exists on the vagrant cloud
    """
    url = f'https://vagrantcloud.com/api/v2/box/{owner}/{name}'
    response = requests.get(url)
    if response.status_code == 200:
        log.info(f'remote box {owner}/{name} found')
        return True
    else:
        log.warning(f'remote box {owner}/{name} not found')
        return False


def is_box(name: str):
    """
        checks whether a vagrant box exists
    """
    available_boxes = get_available_boxes()
    if any(box.name == name for box in available_boxes):
        log.info(f'local box {name} found')
        return True
    if '/' not in name:
        log.warning(f'local box {name} not found')
        return False
    owner, name = name.split('/', 1)
    if remote_box_exists(owner, name):
        return True
    return False


def is_box_download_required(name: str):
    available_boxes = get_available_boxes()
    if any(box.name == name for box in available_boxes):
        log.info(f'local box {name} found')
        return False
    if '/' not in name:
        log.warning(f'local box {name} not found')
        return False
    owner, name = name.split('/', 1)
    if remote_box_exists(owner, name):
        return True
    return False


def download_box(name: str, provider: str = 'virtualbox'):
    log.info(f'downloading box {name}')
    vg = vagrant.Vagrant()
    vg.box_add(name, None, provider=provider)
    log.info(f'box {name} downloaded')


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
