from nicegui import ui


class CardTableTests:
    data: list = None
    columns: list = None

    def set_table_data(self, columns: list, data: list):
        self.columns = columns
        self.data = data

    def show(self):
        with ui.card().classes('w-full no-padding'):
            ui.label('tests').classes(
                'w-full grid place-content-center h-10 text-center text-white text-bold bg-primary')
            with ui.row().classes('p-4 w-full'):
                ui.table(self.columns, rows=self.data).props('bordered').classes('w-full table-striped')
