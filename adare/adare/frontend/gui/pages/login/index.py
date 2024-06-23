from nicegui import ui

from adare.frontend.gui.storage import Storage
from adare.frontend.gui.components.Header import Header
from adare.frontend.gui.colors import set_colors
from adare.frontend.gui import add_static_css_files
from adare.frontend.gui.components.LoginCard import LoginCard

import logging
log = logging.getLogger(__name__)

@ui.page('/login')
def page_login():
    add_static_css_files()
    set_colors()

    # set active tab in header to None
    Storage.active_tab = 'None'

    header = Header()
    header.create()

    with ui.element('div').classes('flex items-center justify-center w-full h-full'). style('position: absolute;top: 50%; left: 50%;transform: translate(-50%,-50%);'):
        with ui.element('div').classes('w-1/3 q-pa-xl shadow-24'):
            login_card = LoginCard()
            login_card.create()

    log.debug('login page loaded')
