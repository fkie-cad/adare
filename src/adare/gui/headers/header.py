from nicegui import ui

from adare.gui.styles import btn_remove_color_prop
from adare.gui.login import LoginIface

class Header:
    """ Header for most of the pages. """

    header = None

    logged_in = None

    login_label_logged_in = None
    login_label_login = None

    welcome_label = None

    def toggle_login_label(self):
        """
        Toggle between login and logged in the label of the header.
        """
        if self.logged_in:
            self.login_label_login.classes(add='hidden')
            self.login_label_logged_in.classes(remove='hidden')
        else:
            self.login_label_login.classes(remove='hidden')
            self.login_label_logged_in.classes(add='hidden')
        self.logged_in = not self.logged_in
        self.welcome_label.set_text(f'Welcome {LoginIface.user}')
        self.header.update()

    def create(self, right_drawer):
        """ Create the header. """
        self.logged_in = LoginIface.is_logged_in(None)

        with ui.header().classes('h-16', replace='row items-center justify-between') as header:
            self.header = header
            with ui.row():
                ui.label('Adare').classes('ml-2 text-2xl font-bold text-white')

            self.login_label_login = ui.button('Login').on('click', lambda: right_drawer.toggle()).classes('mr-2')
            btn_remove_color_prop(self.login_label_login)
            self.login_label_login.classes('bg-cyan-800')
            with ui.row() as login_label_logged_in:
                self.login_label_logged_in = login_label_logged_in
                self.welcome_label = ui.label(f'').classes('mr-2 text-xl self-center')
                btn = ui.button('Logout').on('click', lambda: LoginIface.logout()).classes('mr-2 bg-cyan-800')
                btn_remove_color_prop(btn)
                btn.classes('bg-cyan-800')

            LoginIface.add_logout_trigger_function(self.toggle_login_label)
            LoginIface.add_login_trigger_function(self.toggle_login_label)

            self.toggle_login_label()




