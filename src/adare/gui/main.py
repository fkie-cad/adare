from adare.gui.colors import set_colors, TAILWIND_GRADIENTS
from logindrawer import LoginDrawer
from header import Header

from nicegui import ui


@ui.page('/')
def main_page():
    set_colors()

    # create right drawer for login
    right_drawer = LoginDrawer()
    right_drawer.create()

    # create header with tabs
    header = Header()
    header.create(right_drawer.ui_self)

    # the page content consists of multiple tab panels
    tabs = header.ui_tabs
    tabs.create_panel()


@ui.page('/experiment/{uuid}')
def show_experiment(uuid: str):
    # load experiment from database

    with ui.row():
        with ui.column():
            with ui.card().tight() as card:
                ui.image('https://picsum.photos/id/684/640/360')
                with ui.card_section():
                    ui.label('Lorem ipsum dolor sit amet, consectetur adipiscing elit, ...')
        with ui.column():
            with ui.card().tight() as card:
                ui.image('https://picsum.photos/id/684/640/360')
                with ui.card_section():
                    ui.label('Lorem ipsum dolor sit amet, consectetur adipiscing elit, ...')
        with ui.column():
            with ui.card().tight() as card:
                ui.image('https://picsum.photos/id/684/640/360')
                with ui.card_section():
                    ui.label('Lorem ipsum dolor sit amet, consectetur adipiscing elit, ...')

ui.run()