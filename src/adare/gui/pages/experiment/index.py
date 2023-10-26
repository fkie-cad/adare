from nicegui import ui

from adare.gui.components.Header import Header
from adare.gui.colors import set_colors
from adare.gui import add_static_css_files, add_bootstrap_icons
from adare.gui.components.ExperimentTable import ExperimentTable
from adare.gui.components.ExperimentOverview import ExperimentOverview
from adare.gui.storage import Storage

import logging
log = logging.getLogger(__name__)

@ui.page('/experiment/')
def page_experiment():
    # add bootstrap icons
    add_bootstrap_icons()

    # add custom css to page
    add_static_css_files()

    # set colors
    set_colors()

    # set active tab in header to None
    Storage.active_tab = 'Experiment'

    # show experiment table
    experiment_table = ExperimentTable()
    experiment_table.create()

    # create header
    header = Header()
    header.create()

    log.info('experiment page loaded')


@ui.page('/experiment/{uuid}')
def page_experiment_details(uuid: str):
    # add bootstrap icons
    add_bootstrap_icons()

    # add custom css to page
    add_static_css_files()

    # set colors
    set_colors()

    # set active tab in header to None
    Storage.active_tab = 'None'

    # create header
    header = Header()
    header.create()

    # create experiment view
    experiment_overview = ExperimentOverview(uuid)
    experiment_overview.create()

    log.info(f'experiment (uuid:{uuid}) page loaded')