from nicegui import ui


class CardTable:
    data: list = None
    columns: list = None

    def set_table_data(self, columns: list, data: list):
        self.columns = columns
        self.data = data

    def show(self):
        with ui.card().classes('w-full no-padding').style('gap: 0'):
            ui.label('os information').classes('w-full grid place-content-center h-10 text-center text-white text-bold bg-primary')
            with ui.row().classes('w-full'):
                ui.table(self.columns, rows=self.data).props('hide-header').classes('w-full bordered table-striped')
