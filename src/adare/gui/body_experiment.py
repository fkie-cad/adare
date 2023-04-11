from card_table_tests import CardTableTests
from card_table import CardTable
from styles import style_text_muted_large
from nicegui import ui


class BodyExperimentPage:
    experiment_uuid = None
    data = None

    def __init__(self, uuid):
        self.experiment_uuid = uuid

    def load_data(self):
        pass

    def show(self):
        with ui.card().classes('w-full leading-4').style('gap: 0'):
            with ui.row().classes('w-full items-center justify-between'):
                ui.label(f'name').classes(style_text_muted_large)
                ui.label(f'uuid').classes(style_text_muted_large)
            with ui.row().classes('w-full items-center justify-between mb-6'):
                ui.label('deletefile').classes('text-h5')
                ui.label(self.experiment_uuid).classes('text-h5')
            ui.separator()
            with ui.row().classes('mt-6 w-full items-center justify-between'):
                with ui.column():
                    ui.label('Description')
                with ui.column():
                    table = CardTable()
                    columns = [
                        {'name': 'key', 'label': 'key', 'field': 'key', 'align': 'left', 'sortable': True},
                        {'name': 'value', 'label': 'value', 'field': 'value', 'align': 'left', 'sortable': True},
                    ]
                    data = []
                    table.set_table_data(columns, data)
                    table.show()
                with ui.column():
                    ui.label('Description')
                with ui.column():
                    ui.label('Description')

            with ui.row().classes('mt-12 w-full'):
                columns = [
                    {'name': 'key', 'label': 'key', 'field': 'key', 'align': 'left', 'sortable': True},
                    {'name': 'value', 'label': 'value', 'field': 'value', 'align': 'left', 'sortable': True},
                ]
                data = []
                table = CardTableTests()
                table.set_table_data(columns, data)
                table.show()