from adare.gui.colors import set_colors, TAILWIND_GRADIENTS
from logindrawer import LoginDrawer
from header import Header
from experimenttable import ExperimentTable
from pathlib import Path
from styles import style_text_muted_large
from body_experiment import BodyExperimentPage

from nicegui import ui

def parse_filter_string(filter_string):
    filter_dict = {}
    if filter_string:
        for filter_key_val in filter_string.split(','):
            key, value = filter_key_val.split('=')
            filter_dict[key] = value
    return filter_dict

@ui.page('/')
def main_page(filter_str=None):
    filter_dict = None
    if filter_str:
        filter_dict = parse_filter_string(filter_str)

    # add custom css to page
    ui.add_head_html(f"<style>{Path(r'./static/custom.css').read_text()}</style>")
    set_colors()

    # create right drawer for login
    right_drawer = LoginDrawer()
    right_drawer.create()

    # create header with tabs
    header = Header()
    header.create(right_drawer.ui_self)

    # table containing all experiments
    experiment_table = ExperimentTable()
    experiment_table.create()

    with ui.footer(value=False) as footer:
        footer.classes('bg-white')
        ui.label('Footer')

    def footer_toggle(x):
        footer.toggle()
        if x.sender._props['icon'] == 'expand_less':
            x.sender.props(remove='icon=expand_less', add='icon=expand_more')
        else:
            x.sender.props(remove='icon=expand_more', add='icon=expand_less')

    with ui.page_sticky(position='bottom', x_offset=0, y_offset=0).classes('w-full'):
        ui.button('', on_click=lambda x: footer_toggle(x)).props('icon=expand_less').classes('w-full bg-primary text-white')

@ui.page('/{filter_str}')
def main_page_wfilter(filter_str):
    main_page(filter_str)


@ui.page('/experiment/{uuid}')
def show_experiment(uuid: str):
    # add custom css to page
    ui.add_head_html(f"<style>{Path(r'./static/custom.css').read_text()}</style>")

    set_colors()

    # create right drawer for login
    right_drawer = LoginDrawer()
    right_drawer.create()

    # load experiment from database

    # create header
    header = Header()
    header.create(right_drawer.ui_self)

    # create experiment view
    body = BodyExperimentPage(uuid)
    body.show()


ui.run()