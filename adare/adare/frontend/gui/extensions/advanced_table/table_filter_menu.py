from nicegui import ui
from adare.frontend.gui.styles import btn_remove_color_prop
from adare.frontend.gui.extensions.advanced_table.filters import MultipleFilter

class TableFilterMenu:
    table = None
    filter_index_id_count = 0
    filter_menu_items = {}
    filter_menu_entry_container = None

    def set_table(self, table):
        self.table = table

    def __update_filter_column(self, e, filter_index):
        # Reset filter method and value
        self.filter_menu_items[filter_index]['ui_method_select'].set_value(None)
        self.filter_menu_items[filter_index]['ui_filter_value_input'].set_value(None)
        self.filter_menu_items[filter_index]['ui_filter_value_input'].props(add='disable')

        # get all filterable rows
        filterable_columns = self.table.get_filterable_columns()
        column = [c for c in filterable_columns if c['name'] == e.value][0]

        # list of names of all filter methods
        filter_method_options = [x.name for x in column['filter']]

        ui_filter_class_select = self.filter_menu_items[filter_index]['ui_method_select']
        ui_filter_class_select.options = filter_method_options
        ui_filter_class_select.props(remove='disable')
        ui_filter_class_select.update()
        self.filter_container.filter_data()

    def __update_filter_method(self, e, filter_index):

        ui_column_select = self.filter_menu_items[filter_index]['ui_column_select']
        ui_filter_value_column = self.filter_menu_items[filter_index]['ui_filter_value_column']
        ui_filter_value = self.filter_menu_items[filter_index]['ui_filter_value_input']

        column = [c for c in self.table.get_filterable_columns() if c['name'] == ui_column_select.value][0]
        filter_class = [f for f in column['filter'] if f.name == e.value][0]
        filter_obj = filter_class()
        filter_obj.set_column_name(column['field'])
        val = ui_filter_value.value
        ui_filter_value_column.remove(ui_filter_value)
        self.filter_menu_items[filter_index]['ui_filter_value_input'] = filter_obj.create_comparison_value_input(table=self,
                                                                                                           index=filter_index,
                                                                                                           filter_container=self.filter_container,
                                                                                                           container=ui_filter_value_column,
                                                                                                           default_value = val)
        ui_column_select.update()
        self.filter_container.filter_data()

    def __remove_filter(self, filter_index):
        ui_filter_menu_entry_container = self.filter_menu_items[filter_index]['ui_filter_menu_entry_container']
        ui_filter_entry_row = self.filter_menu_items[filter_index]['ui_filter_entry_row']

        ui_filter_menu_entry_container.remove(ui_filter_entry_row)
        self.filter_container.remove_filter(filter_index)
        self.filter_container.filter_data()

    def __create_filter_menu_entry(self):
        self.filter_index_id_count += 1
        filterable_columns = self.table.get_filterable_columns()
        filterable_columns_names = [c['name'] for c in filterable_columns]
        filter_index = self.filter_index_id_count

        with self.filter_menu_entry_container as container:
            with ui.row().classes('w-full') as row:
                ui_column_select = ui.select(filterable_columns_names,
                                             on_change=lambda e: self.__update_filter_column(e, filter_index))
                ui_method_select = ui.select([], on_change=lambda e: self.__update_filter_method(e, filter_index)).props(
                    'disable')
                with ui.column() as filter_value_column:
                    ui_filter_value_input = ui.input().props('disable')
                ui_btn = ui.button(on_click=lambda: self.__remove_filter(filter_index)).props('icon=delete').classes(
                    'ml-auto mr-2')
                btn_remove_color_prop(ui_btn)
                ui_btn.classes('bg-cyan-800 text-white')
        self.filter_menu_items[filter_index] = {
            'ui_filter_menu_entry_container': container,
            'ui_filter_entry_row': row,
            'ui_column_select': ui_column_select,
            'ui_method_select': ui_method_select,
            'ui_filter_value_input': ui_filter_value_input,
            'ui_filter_value_column': filter_value_column,
            'ui_remove_btn': ui_btn,
        }

    def create(self):
        self.filter_container = MultipleFilter()
        self.filter_container.set_table(self.table)

        with ui.button(on_click=lambda: menu_filter.open()).props('icon=filter_alt') as btn_filter:
            btn_remove_color_prop(btn_filter)
            btn_filter.classes('bg-cyan-800 text-white')

        with ui.menu() as menu_filter, ui.column().classes('p-2'):
            menu_filter.classes('w-1/2')
            self.filter_menu_entry_container = ui.column().classes('w-full')
            # self.__create_filter_menu_entry()

            with ui.row():
                btn = ui.button('add filter', on_click=self.__create_filter_menu_entry).props('icon=add')
                btn_remove_color_prop(btn)
                btn.classes('bg-cyan-800 text-white')