from nicegui import ui
from pathlib import Path

from adare.gui.storage import Storage
from adare.gui.components.Header import Header
from adare.gui.colors import set_colors
from adare.gui import add_static_css_files
from adare.gui.components.LogDisplay import LogDisplay
import adare.database.database as database

import logging
log = logging.getLogger(__name__)

@ui.page('/log/{uuid}')
def page_log(uuid: str):
    add_static_css_files()
    set_colors()

    # set active tab in header to None
    Storage.active_tab = 'None'

    header = Header()
    header.create()

    with database.ExperimentApi() as experiment_api:
        logfile = experiment_api.get_logfile_by_uuid(uuid)
        logfile_path = Path(logfile.path)

    if not logfile_path.is_file():
        log.error(f'logfile with uuid {uuid} not found')
        ui.open('/')

    log_display = LogDisplay(logfile_path)
    log_display.create()

    log.debug('login page loaded')
