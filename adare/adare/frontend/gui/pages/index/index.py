from nicegui import ui

from adare.frontend.gui.components.Header import Header
from adare.frontend.gui.colors import set_colors
from adare.frontend.gui import add_static_css_files

@ui.page('/')
def page_index():
    # redirect to /runs (experiment run overview)

    # add custom css to page
    add_static_css_files()
    set_colors()
    #
    # # create header with tabs
    header = Header()
    header.create()

    ui.open('/runs')

    #
    # # table containing all experiments
    # experiment_table = ExperimentTable()
    # experiment_table.create()

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