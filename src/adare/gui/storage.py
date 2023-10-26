from nicegui import ui

import logging
log = logging.getLogger(__name__)

class Storage:
    active_tab = 'Home'

    # RequestModifyPanel
    request_modify_panel_visible = False
    request_table_visible = True
    request_type = None
    request_experiment_uuid = None
    request_scenario_uuid = None

def show_request_modify_panel(uuid: str = None, req_type: str = None):
    Storage.request_type = req_type
    if req_type == 'experiment':
        Storage.request_experiment_uuid = uuid
    elif req_type == 'scenario':
        Storage.request_scenario_uuid = uuid
    Storage.request_modify_panel_visible = True
    Storage.request_table_visible = False
    ui.open('/request/')

def toggle_request_table_modifypanel():
    Storage.request_modify_panel_visible = not Storage.request_modify_panel_visible
    Storage.request_table_visible = not Storage.request_table_visible
