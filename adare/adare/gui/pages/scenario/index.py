from nicegui import ui

from adare.gui.components.Header import Header
from adare.gui.colors import set_colors
from adare.gui import add_static_css_files


@ui.page('/scenario/{uuid}')
def page_request(uuid: str):
    # add bootstrap icons
    ui.add_head_html(f'<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.3.0/font/bootstrap-icons.css">')

    # add custom css to page
    add_static_css_files()

    # set colors
    set_colors()

    # create header
    header = Header()
    header.create()

    
