from nicegui import ui

from adare.frontend.gui.storage import Storage
from adare.frontend.gui.components.Header import Header
from adare.frontend.gui.colors import set_colors
from adare.frontend.gui import add_static_css_files
from adare.frontend.gui.components.RunTable import RunTable
from adare.frontend.gui.components.ExperimentRunOverview import ExperimentRunOverview
from fastapi.responses import RedirectResponse

import logging
log = logging.getLogger(__name__)

@ui.page('/runs')
def page_index():
    add_static_css_files()
    set_colors()

    # set active tab in header to None
    Storage.active_tab = 'Runs'

    header = Header()
    header.create()

    run_table = RunTable()
    run_table.create()

    log.debug('experiment run page loaded')


@ui.page('/')
def page_runs():
    log.debug('redirecting to /runs/ to index page')
    return RedirectResponse(url='/runs')


@ui.page('/run/{ulid}')
def page_runs_details(ulid):
    add_static_css_files()
    set_colors()

    # set active tab in header to None
    Storage.active_tab = 'Runs'

    header = Header()
    header.create()

    exprun_overview = ExperimentRunOverview(ulid)
    exprun_overview.create()

    log.debug(f'experiment run (ulid:{ulid}) page loaded')