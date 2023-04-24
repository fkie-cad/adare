from adare.gui.login import LoginIface
from adare.gui.colors import TAILWIND_GRADIENTS
from adare.gui.extensions.icon import IconExtension
from adare.gui.styles import btn_remove_color_prop
from adare.gui.dialogs import create_login_dialogs, create_publish_experiment_dialogs

from nicegui import ui

# configure logging
import logging
log = logging.getLogger(__name__)

class LoginDrawer:
    drawer = None

    state = None

    view_logged_in = None
    view_login_interface = None


    def toggle_display(self):
        """ Toggle between login and user display window """
        if not self.state:
            return
        if self.state == 'login_window':
            self.state = 'userdisplay_window'
            self.view_login_interface.classes(remove='hidden')
            self.view_logged_in.classes(add='hidden')
        elif self.state == 'userdisplay_window':
            self.state = 'login_window'
            self.view_login_interface.classes(add='hidden')
            self.view_logged_in.classes(remove='hidden')
            self.drawer.toggle()
        self.drawer.update()

    def create(self):
        """ Create the login drawer """

        # create dialogs shown for successful/failed login or errors in the webserver connection
        create_login_dialogs()
        create_publish_experiment_dialogs()

        self.state = 'login_window' if LoginIface.user is None else 'userdisplay_window'

        LoginIface.add_login_trigger_function(self.toggle_display)
        LoginIface.add_logout_trigger_function(self.toggle_display)

        with ui.right_drawer(value=False).classes(f'bg-{TAILWIND_GRADIENTS.emerald_blue} self-end justify-center') as right_drawer:
            self.drawer = right_drawer
            with ui.column().classes('w-full items-center') as div_login_view:
                self.view_login_interface = div_login_view
                with ui.row().classes('w-full items-center justify-center'):
                    ui.icon('account_circle').classes('text-cyan-900 text-8xl')
                with ui.row().classes('w-full'):
                    username_input = ui.input(label='username').classes('w-full bg-white border-gray-400 rounded-lg px-6 py-2')
                with ui.row().classes('w-full'):
                    with ui.input(label='password').props('type=password').classes('w-full bg-white border-gray-400 rounded-lg px-6 py-2') as password_input:
                        with password_input.add_slot('append'):
                            icon = ui.icon('cursor-pointer').props('name=visibility_off').classes('text-gray-400')
                            IconExt = IconExtension(icon)
                            icon.on('click', lambda: IconExt.set_visibility(password_input))

                with ui.row().classes('w-full'):
                    with ui.button('Login', on_click=lambda _: LoginIface.login(username_input.value, password_input.value)) as btn:
                        btn_remove_color_prop(btn)
                        btn.classes('w-1/2 ml-auto text-blue-800 bg-slate-300')

            with ui.column().classes('w-full items-center') as div_logged_in:
                self.view_logged_in = div_logged_in

            self.toggle_display()
