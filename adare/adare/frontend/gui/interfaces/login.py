from adare.webappaccess.login import WebappLogin
from nicegui import ui

# configure logging
import logging
log = logging.getLogger(__name__)

class LoginInterface:
    logged_in: bool = False
    login_interface = None
    user = None

    view_login_interface = None
    view_logged_in = None

    def __init__(self):
        self.login_interface = WebappLogin()
        session = self.login_interface.get_user_session(None)
        # self.user = session.username if session else None

    async def login(self, username, password):
        result, error_msg  = await self.login_interface.login(username, password)
        return result, error_msg

    def get_logged_in_user(self):
        return self.user

    async def logout(self):
        if not self.user:
            raise UserWarning('No user is logged in')
        await self.login_interface.logout(self.user)
        self.user = None
        ui.open('/login')


    def update_login_status(self, username):
        pass
        # user_session = self.login_interface.get_user_session(username)
        # if not user_session:
        #     self.logged_in = False
        #     return
        # if not self.user:
        #     self.user = user_session.username
        # self.logged_in = True

LoginIface = LoginInterface()