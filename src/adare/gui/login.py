from adare.webappaccess.login import WebappLogin

# configure logging
import logging
log = logging.getLogger(__name__)

class LoginInterface:
    login_interface = None
    user = None

    view_login_interface = None
    view_logged_in = None

    login_trigger_functions = []
    login_trigger_functions_failed_login = []
    login_trigger_functions_connection_error = []

    logout_trigger_functions = []

    def __init__(self):
        self.login_interface = WebappLogin()
        session = self.login_interface.get_user_session(None)
        self.user = session.username if session else None

    def login(self, username, password):
        result = self.login_interface.login(username, password)
        if result == 'success':
            self.user = username
            for func in self.login_trigger_functions:
                func()
        elif result == 'connection error':
            for func in self.login_trigger_functions_connection_error:
                func()
        elif result == 'failed':
            for func in self.login_trigger_functions_failed_login:
                func()

    def get_logged_in_user(self):
        return self.user

    def logout(self):
        if not self.user:
            raise UserWarning('No user is logged in')
        self.login_interface.logout(self.user)
        self.user = None
        for func in self.logout_trigger_functions:
            func()

    def add_login_trigger_function(self, func):
        self.login_trigger_functions.append(func)

    def add_logout_trigger_function(self, func):
        self.logout_trigger_functions.append(func)

    def add_login_trigger_function_failed_login(self, func):
        self.login_trigger_functions_failed_login.append(func)

    def add_login_trigger_function_connection_error(self, func):
        self.login_trigger_functions_connection_error.append(func)

    def is_logged_in(self, username):
        user_session = self.login_interface.get_user_session(username)
        if not user_session:
            return False
        if not self.user:
            self.user = user_session.username
        return True

LoginIface = LoginInterface()