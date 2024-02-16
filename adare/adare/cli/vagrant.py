# external imports
from pathlib import Path

# internal imports
from adare.vagrantapi.vagrantutils import print_available_boxes

# configure logging
import logging
log = logging.getLogger(__name__)


# def vgbox_add(arguments):
#     boxpath = arguments.target
#     if not Path(boxpath).is_file():
#         raise FileNotFoundError
#     boxname = arguments.name
#     run_vagrant(["box", "add", boxpath, boxname])
#
#
# def vgbox_remove(arguments):
#     boxname = arguments.name
#     run_vagrant(["box", "remove", boxname])


def vgbox_list(arguments):
    print_available_boxes()
