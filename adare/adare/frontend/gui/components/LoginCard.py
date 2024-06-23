from nicegui import ui

from adare.frontend.gui.interfaces.login import LoginIface
from adare.frontend.gui.components.ErrorDialog import ErrorDialog

import logging
log = logging.getLogger(__name__)


class LoginCard:
    username = ''
    password = ''
    loading: bool
    not_loading: bool

    error_dialog: ErrorDialog

    def __init__(self):
        self.__set_loading(False)

    def __set_username(self, username: str):
        self.username = username

    def __set_password(self, password: str):
        self.password = password

    def __error(self, error_msg: str):
        self.error_dialog.set_error_msg(error_msg)
        self.error_dialog.show()

    def __set_loading(self, loading: bool):
        self.loading = loading
        self.not_loading = not loading

    async def __login(self):
        self.__set_loading(True)
        log.debug('log in process started')
        import asyncio
        success, error_msg = await LoginIface.login(self.username, self.password)
        if success:
            ui.open('/')
        else:
            self.__error(error_msg)
            log.error(f'log in process failed: {error_msg}')
        log.debug(f'log in process finished (success: {success})')
        self.__set_loading(False)

    def __reset(self):
        self.username = ''
        self.password = ''

    def create(self):
        self.error_dialog = ErrorDialog()
        self.error_dialog.create()

        with ui.card().props('flat square').classes('flex flex-column justify-center items-center w-full') as card:
            with ui.card_section():
                with ui.element('h3').classes('text-h3 q-ma-none q-mb-xl text-center'):
                    ui.label('Sign In')
                with ui.element('div').classes('flex justify-center'):
                    ui.icon('account_circle', size="10em")

            with ui.card_section().classes('w-full'):
                with ui.element('q-form').classes('q-px-sm q-pt-sm') as form:
                    form.on('submit', self.__login)
                    form.on('reset', self.__reset)
                    username_input_props = [
                        'square',
                        'clearable',
                        'type=username',
                        'label=username',
                    ]
                    with ui.input().classes('q-mb-sm').props(' '.join(username_input_props)) as input_username:
                        input_username.bind_value(self, 'username')
                        with input_username.add_slot('prepend'):
                            ui.icon('person')

                    password_input_props = [
                        'square',
                        'clearable',
                        'type=password',
                        'label=password',
                    ]

                    with ui.input().classes('q-mb-sm').props(' '.join(password_input_props)) as input_password:
                        input_password.bind_value(self, 'password')
                        with input_password.add_slot('prepend'):
                            ui.icon('lock')

            with ui.card_actions().classes('q-px-lg w-full'):
                with ui.button('', on_click=self.__login).classes('full-width').props('unelevated size="lg" color="blue-grey-9"'):
                    ui.label('Sign In').bind_visibility(self, 'not_loading')
                    ui.spinner('orbit', size="1em", color="white").bind_visibility(self, 'loading')

