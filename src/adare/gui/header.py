from adare.gui.colors import TAILWIND_GRADIENTS
from tabs import Tabs

from nicegui import ui


class Header:
    ui_self = None
    ui_user_avatar = None

    def create(self, right_drawer):

        with ui.header().classes('h-16', replace='row items-center justify-between') as header:
            self.ui_self = header
            # self.ui_tabs = Tabs()
            # self.ui_tabs.create()
            with ui.row():
                ui.label('Adare').classes('ml-2 text-2xl font-bold text-white')

            with ui.avatar('account_circle') as avatar:
                self.ui_user_avatar = avatar
                del avatar._props['color']
                avatar.props('font-size=48px')
                avatar.classes('mr-2 ml-auto bg-none text-white')
                avatar.on('click', lambda: right_drawer.toggle())


    def change_user_avatar(self, val):
        self.ui_user_avatar._props['icon'] = val
        self.ui_user_avatar.update()



