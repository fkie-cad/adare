from nicegui import ui

from adare.gui.drawers.logindrawer import LoginDrawer
from adare.gui.headers.header import Header
from adare.gui.page_index.experimenttable import ExperimentTable
from adare.gui.colors import set_colors
from adare.gui import add_static_css_files

@ui.page('/')
def page_index():

    # add custom css to page
    add_static_css_files()
    set_colors()

    # create right drawer for login
    right_drawer = LoginDrawer()
    right_drawer.create()

    # create header with tabs
    header = Header()
    header.create(right_drawer.drawer)

    # table containing all experiments
    experiment_table = ExperimentTable()
    experiment_table.create()

    # with ui.footer(value=False) as footer:
    #     footer.classes('bg-white h-full')
    #     with ui.row().classes('p-5'):
    #         ui.label('Footer')

    # def footer_toggle(x):
    #     footer.toggle()
    #     if x.sender._props['icon'] == 'expand_less':
    #         x.sender.props(remove='icon=expand_less', add='icon=expand_more')
    #     else:
    #         x.sender.props(remove='icon=expand_more', add='icon=expand_less')

    # with ui.page_sticky(position='bottom', x_offset=0, y_offset=0).classes('w-full'):
    #     ui.button('', on_click=lambda x: footer_toggle(x)).props('icon=expand_less').classes('w-full bg-primary text-white')