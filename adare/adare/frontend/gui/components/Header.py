from nicegui import ui

from adare.frontend.gui.interfaces.login import LoginIface
from adare.frontend.gui.storage import Storage

class Header:
    """ Header for most of the pages. """

    def create(self):
        LoginIface.update_login_status(None)

        with ui.header().classes('bg-primary text-white', replace='row items-center justify-between').props('elevated') :
            with ui.element('q-toolbar').classes('q-pr-none'):
                with ui.element('q-toolbar-title'):
                    ui.html('Adare')

                tabs_props = [
                    'inline-label',
                    'active-bg-color="brand"'
                ]
                with ui.tabs().props(' '.join(tabs_props)).classes('q-pr-md').bind_value(Storage, 'active_tab'):
                    ui.tab('Runs', icon='play_circle').on('click', lambda x: ui.open('/'))
                    ui.tab('Experiment', icon='science').on('click', lambda x: ui.open('/experiment'))
                    ui.tab('Request', icon='hive').on('click', lambda x: ui.open('/request'))

                # create login button
                with ui.link(target='/login').bind_visibility_from(LoginIface, 'logged_in', value=False).classes(remove='nicegui-link'):
                    ui.button('Login', color='white', icon='login').props('dense').classes('text-primary q-ma-xs')


                btn_dropdown_props = [
                    'color="white"',
                    'dense',
                    'text-color="primary"',
                    'dropdown-icon="more_vert"',
                    'icon="person"',
                    'size="md"',
                ]
                with ui.element('q-btn-dropdown').props(' '.join(btn_dropdown_props)).bind_visibility_from(LoginIface, 'logged_in', value=True).classes('q-ma-xs') as btn_dropdown:
                    with btn_dropdown.add_slot('label'):
                        ui.label(LoginIface.user).style('font-size: 14px; font-weight: bold')

                    logout_btn_props = [
                        'size="md"',
                        'v-close-popup',
                        'push',
                    ]
                    ui.button('logout', color='primary', icon='logout', on_click=LoginIface.logout).props(' '.join(logout_btn_props)).classes('q-ma-sm')




