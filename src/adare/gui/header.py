from adare.gui.colors import TAILWIND_GRADIENTS
from tabs import Tabs

from nicegui import ui


class Header:
    ui_self = None
    ui_tabs = None

    def create(self, right_drawer):
        with ui.header().classes('h-16', replace='row items-center justify-between') as header:
            self.ui_self = header
            self.ui_tabs = Tabs()
            self.ui_tabs.create()

            btn = ui.button('Login', on_click=lambda: right_drawer.toggle())
            del btn._props['color']
            btn.classes(f'bg-{TAILWIND_GRADIENTS.shiny_button} text-white mr-2')
