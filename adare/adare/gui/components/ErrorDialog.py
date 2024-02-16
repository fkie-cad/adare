from nicegui import ui

import logging
log = logging.getLogger(__name__)


class ErrorDialog:
    error_msg: str
    dialog: ui.dialog

    def __init__(self):
        pass

    def show(self):
        self.dialog.open()

    def hide(self):
        self.dialog.close()

    def set_error_msg(self, error_msg):
        self.error_msg = error_msg

    def create(self):
        with ui.dialog() as self.dialog:
            with ui.card():
                with ui.card_section().classes('q-pa-sm'):
                    ui.label('Error').classes('text-h6')
                ui.separator()
                with ui.card_section().classes('q-pa-sm'):
                    ui.label().bind_text(self, 'error_msg')
                with ui.card_section().classes('flex justify-end w-full q-pa-sm'):
                    ui.button('Close', on_click=self.hide)