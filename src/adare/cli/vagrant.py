# external imports
from pathlib import Path

# internal imports
from adare.vagrantapi import run_vagrant

# configure logging
import logging
log = logging.getLogger(__name__)


def vgbox_add(arguments):
    boxpath = arguments.target
    if not Path(boxpath).is_file():
        raise FileNotFoundError
    boxname = arguments.name
    run_vagrant(["box", "add", boxpath, boxname])


def vgbox_remove(arguments):
    boxname = arguments.name
    run_vagrant(["box", "remove", boxname])


def vgbox_list(arguments):
    command = ["box", "list"]
    ret = run_vagrant(command)
    print("List of locally available vagrant boxes:")
    print(ret['stdout'])
