
class TableExtension:
    """
    provides helper functions for the table of nicegui:
        - allows to show/hide columns
        - allows to show/hide all columns
    """
    switch_button_all = None
    switch_button_columns = []
    table = None

    columns: list[dict]
    columns_shown: dict
    rows: list[dict]

    def __init__(self, columns, columns_shown, rows):
        self.columns = columns
        self.columns_shown = columns_shown
        self.rows = rows

    def set_columns(self, columns):
        self.columns = columns
        self.table.update()

    def set_columns_shown(self, columns_shown):
        self.columns_shown = columns_shown
        self.table.update()

    def add_row(self, row):
        self.rows.append(row)
        self.table.update()

    def add_rows(self, rows):
        self.rows.extend(rows)
        self.table.update()

    def add_table(self, table):
        self.table = table

    def add_switch_button_all(self, switch_button):
        self.switch_button_all = switch_button

    def add_switch_button_columns(self, switch_button):
        self.switch_button_columns.append(switch_button)

    def get_shown_columns(self):
        shown_columns = []
        for c in self.columns:
            if c['name'] not in self.columns_shown.keys():
                shown_columns.append(c)
            elif self.columns_shown[c['name']]:
                shown_columns.append(c)
        return shown_columns

    def show_hide_column(self, value, column_name):
        self.columns_shown[column_name] = value['args']
        self.table._props['columns'] = self.get_shown_columns()
        switch_values = [v for v in [switch.value for switch in self.switch_button_columns]]
        if all(switch_values):
            self.switch_button_all.set_value(True)
        if False in switch_values:
            self.switch_button_all.set_value(False)
        self.table.update()

    def show_hide_all(self, value):
        self.columns_shown = {c: value for c in self.columns_shown.keys()}
        if value['args']:
            self.table._props['columns'] = self.columns
            for s in self.switch_button_columns:
                s.set_value(True)
        else:
            for s in self.switch_button_columns:
                s.set_value(False)
            self.table._props['columns'] = []
        self.table.update()