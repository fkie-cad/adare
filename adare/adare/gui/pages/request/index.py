from nicegui import ui

from adare.gui.components.Header import Header
from adare.gui.components.RequestTable import RequestTable
from adare.gui.components.RequestModifyPanel import RequestModifyPanel
from adare.gui.colors import set_colors
from adare.gui import add_static_css_files
from adare.gui.storage import Storage, toggle_request_table_modifypanel


@ui.page('/request/')
def page_request():
    # add bootstrap icons
    ui.add_head_html(f'<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.3.0/font/bootstrap-icons.css">')

    # add custom css to page
    add_static_css_files()

    # set colors
    set_colors()

    # load experiment from database

    # create header
    header = Header()
    header.create()

    req_table = RequestTable()
    req_modify_panel = RequestModifyPanel(request_table=req_table)

    # create button to add new request
    with ui.element('div').classes('flex justify-end q-pa-md w-full').bind_visibility_from(Storage, 'request_modify_panel_visible', value=False):
        ui.button('Add new request', on_click=toggle_request_table_modifypanel)

    req_modify_panel.create()
    req_table.create()





