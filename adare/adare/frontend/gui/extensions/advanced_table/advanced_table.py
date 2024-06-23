from adare.frontend.gui.extensions.advanced_table.table_filter_menu import TableFilterMenu
from adare.frontend.gui.styles import btn_remove_color_prop
from nicegui import ui

class AdvancedTable:
    """ A table with advanced features like filtering, sorting, hiding columns, etc."""

    table = None
    checkbox_showhideall = None
    checkboxes_showhide_columns = []

    # filter
    filter_index_id_count = 0
    filter_container = None
    ui_filter_menu_entry_container = None
    filter_menu_items = {}

    # must be set by subclass
    columns: list[dict] = None

    # contains the data to be displayed in the table
    data: list[dict] = None

    # contains the actual shown data in the table
    shown_rows: list[bool] = None

    def __init__(self):
        self.update_data()
        self.show_all_rows()

    def show_all_rows(self):
        """ Show all rows in the table """
        if self.data:
            self.shown_rows = [True] * len(self.data)

    def set_shown_rows(self, shown_rows):
        """ Set rows to be shown in the table """
        self.shown_rows = shown_rows

    def update_data(self):
        """ Update the table data """
        pass

    def _get_shown_columns(self):
        """ Get the columns that are shown """
        shown_columns = []
        for c in self.columns:
            if 'hide' not in c.keys():
                shown_columns.append(c)
            elif not c['hide']:
                shown_columns.append(c)
        return shown_columns

    def get_filterable_columns(self):
        """ Get the columns that can be filtered """
        return [c for c in self.columns if 'filter' in c.keys() and c['filter']]

    def _get_shown_data(self):
        """ Get the data that is shown in the table """
        shown_data = []
        for i, d in enumerate(self.data):
            if self.shown_rows[i]:
                shown_data.append(d)
        return shown_data

    def _get_hideable_columns(self):
        """ Get the columns that can be hidden """
        column_dict = {}
        for c in self.columns:
            if 'hide' in c.keys():
                column_dict[c['field']] = c
        return column_dict

    def _show_hide_column(self, value, column_field_name):
        """ Show or hide a specific column """
        columns_by_field_name = self._get_hideable_columns()
        columns_by_field_name[column_field_name]['hide'] = not value
        self.table._props['columns'] = self._get_shown_columns()
        self.table.update()

    def _show_hide_all(self, value):
        """ Show or hide all columns """
        new_columns = []
        for c in self.columns:
            if 'hide' in c.keys():
                c['hide'] = not value
                new_columns.append(c)
            else:
                new_columns.append(c)
        self.columns = new_columns
        if value:
            self.table._props['columns'] = self.columns
            for s in self.checkboxes_showhide_columns:
                s.set_value(True)
        else:
            self.table._props['columns'] = []
            for s in self.checkboxes_showhide_columns:
                s.set_value(False)
        self.table.update()

    def create_filter_menu(self):
        """ Create the filter menu to filter columns """
        table_filter_menu = TableFilterMenu()
        table_filter_menu.set_table(self)
        table_filter_menu.create()

    def create_column_select_dropdown(self):
        """ Create the column select dropdown to show/hide columns """
        with ui.button(on_click=lambda: menu_columnselect.open()).props('icon=tune') as btn_columnselect:
            btn_remove_color_prop(btn_columnselect)
            btn_columnselect.classes('bg-cyan-800 text-white')

            with ui.menu() as menu_columnselect, ui.column().classes('gap-0 p-2'):
                self.checkbox_showhideall = ui.checkbox('Show all columns', value=False,
                                                        on_change=lambda e: self._show_hide_all(e.value))
                self.checkbox_showhideall.props('color=cyan-800')
                self.checkbox_showhideall.set_value(False)
                for index, column in enumerate(self._get_hideable_columns().values()):
                    checkbox = ui.checkbox(column['label'], value=True,
                                           on_change=lambda e, c_name=column['field']: self._show_hide_column(e.value,
                                                                                                               c_name))
                    checkbox.props('color=cyan-800')
                    self.checkboxes_showhide_columns.append(checkbox)
                    checkbox.set_value(not column['hide'])

    def update(self):
        """ Update the table gui object """
        self.table._props['rows'] = self._get_shown_data()
        self.table.update()

    def create(self):
        """ Create the table gui object """
        pass



