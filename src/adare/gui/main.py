from adare.gui.colors import set_colors, TAILWIND_GRADIENTS
from logindrawer import LoginDrawer
from header import Header
from experimenttable import ExperimentTable

from nicegui import ui

# add custom css to use tailwind colors for quasar elements such as checkboxes since they can not be overwritten using the classes property of elements
#ui.add_head_html(f"<style>{r'X:/Arbeit/adare/src/adare/gui/static/tailwind_color_for_quasar.css'}</style>")


@ui.page('/')
def main_page():
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


@ui.page('/experiment/{uuid}')
def show_experiment(uuid: str):
    ui.add_head_html("""<style>
        .table-striped tbody tr:nth-of-type(even) {
          background-color: #f1f5f9;
        }
    </style>
    """)

    set_colors()

    # create right drawer for login
    right_drawer = LoginDrawer()
    right_drawer.create()

    # load experiment from database

    # create header
    header = Header()
    header.create(right_drawer.ui_self)

    # create experiment view
    with ui.card().classes('w-full leading-4').style('gap: 0'):
        with ui.row().classes('w-full items-center justify-between'):
            ui.label(f'name').classes('text-gray-400 font-medium text-lg')
            ui.label(f'uuid').classes('text-gray-400 font-medium text-lg')
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('deletefile').classes('text-h5 mb-4')
            ui.label('b8e1bfb1-81a9-4124-8d0d-6466dcf49220').classes('text-h4 mb-6')
        ui.separator()
        with ui.row().classes('mt-6 w-full items-center justify-between'):
            with ui.column():
                ui.label('Description')
            with ui.column():
                with ui.card().classes('w-full no-padding').style('gap: 0'):
                    ui.label('os information').classes('w-full grid place-content-center h-10 text-center text-white text-bold bg-primary')
                    columns = [
                        {'name': 'key', 'label': 'key', 'field': 'key', 'align': 'left', 'sortable': True},
                        {'name': 'value', 'label': 'value', 'field': 'value', 'align': 'left', 'sortable': True},
                    ]
                    data = [
                        {
                            'key': 'os',
                            'value': 'Windows 10',
                        },
                        {
                            'key': 'distribution',
                            'value': 'Home',
                        },
                    ]
                    ui.table(columns,rows=data).props('hide-header').classes('w-full table-striped')
            with ui.column():
                ui.label('Description')
            with ui.column():
                ui.label('Description')

        with ui.row().classes('mt-12 w-full items-center justify-between'):
            with ui.card().classes('w-full leading-4 no-padding'):
                ui.label('tests').classes('w-full grid place-content-center h-10 text-center text-white text-bold bg-primary')
                columns = [
                    {'name': 'key', 'label': 'key', 'field': 'key', 'align': 'left', 'sortable': True},
                    {'name': 'value', 'label': 'value', 'field': 'value', 'align': 'left', 'sortable': True},
                ]
                data = [
                    {
                        'key': 'os',
                        'value': 'Windows 10',
                    },
                    {
                        'key': 'distribution',
                        'value': 'Home',
                    },
                ]
                ui.table(columns,rows=data).props('bordered').classes('w-auto m-4 table-striped')


ui.run()