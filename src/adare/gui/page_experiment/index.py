from nicegui import ui

from pathlib import Path
from adare.gui.headers.header import Header
from adare.gui.drawers.logindrawer import LoginDrawer
from adare.gui.page_experiment.body_experiment import BodyExperimentPage
from adare.gui.colors import set_colors
from adare.gui import add_static_css_files


@ui.page('/experiment/{uuid}')
def page_experiment(uuid: str):
    # add bootstrap icons
    ui.add_head_html(f'<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.3.0/font/bootstrap-icons.css">')

    # add custom css to page
    add_static_css_files()

    # set colors
    set_colors()

    # create right drawer for login
    right_drawer = LoginDrawer()
    right_drawer.create()

    # load experiment from database

    # create header
    header = Header()
    header.create(right_drawer.drawer)

    # create experiment view
    body = BodyExperimentPage(uuid)
    body.show()