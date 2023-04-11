from adare.gui.extensions.table import TableExtension
from nicegui import ui


class Filter:

    @classmethod
    def create_comparison_value_input(cls):
        pass

    @classmethod
    def filter_row(cls, value, comparison_value) -> bool:
        pass

    @classmethod
    def filter_data(cls, data: list, column_name: str, comparison_value) -> list[bool]:
        bool_list_show = []
        for row in data:
            bool_list_show.append(cls.filter_row(row[column_name], comparison_value))
        return bool_list_show


class FilterEqual(Filter):
    name: str = '=='

    @classmethod
    def create_comparison_value_input(cls):
        ui.input()

    @classmethod
    def filter_row(cls, value, comparison_value) -> bool:
        return value == comparison_value


# todo: more clever data structure for table maybe pandas dataframe?
class ExperimentTable:
    ui_self = None
    checkbox_showhideall = None
    checkboxes_showhide_columns = []

    # filter
    filter_menu_entry_container = None

    columns: list[dict] = [
        {'name': 'status', 'label': 'status', 'field': 'status', 'required': True, 'sortable': False, 'align': 'left'},
        {'name': 'name', 'label': 'name', 'field': 'name', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'uuid', 'label': 'uuid', 'field': 'uuid', 'required': True, 'sortable': False, 'align': 'left', 'hide': False},
        {'name': 'os', 'label': 'os', 'field': 'os', 'required': True, 'sortable': True, 'align': 'left', 'hide': False, 'filter': [FilterEqual]},
        {'name': 'os distribution', 'label': 'os distribution', 'field': 'os_distribution', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'os version', 'label': 'os version', 'field': 'os_version', 'required': True, 'sortable': True,
         'align': 'left', 'hide': False},
        {'name': 'time start', 'label': 'time start', 'field': 'time_start', 'required': True, 'sortable': True,
         'align': 'left', 'hide': False},
        {'name': 'time end', 'label': 'time end', 'field': 'time_end', 'required': True, 'sortable': True,
         'align': 'left', 'hide': True},
        {'name': 'btn', 'label': '', 'field': 'btn', 'required': False, 'sortable': False, 'align': 'right'},
        {'name': 'publish', 'label': 'publish', 'field': 'publish', 'required': False, 'sortable': False, 'align': 'right'},
    ]
    data: list[dict] = [
        {'id': 0, 'status': 'success', 'name': 'deletefile', 'uuid': '738d01fa-94f0-4977-90f8-2ac9d9fed464', 'os': 'Windows', 'os_distribution': 'Windows 10', 'os_version': '10.0.19042', 'time_start': '2022-07-01 14:05:33', 'time_end': '2022-07-01 14:08:21'},
        {'id': 1, 'status': 'warning', 'name': 'deletefile', 'uuid': 'ae6753b1-bfbf-4655-b937-7b3426a0ab60', 'os': 'Windows',
         'os_distribution': 'Windows 10', 'os_version': '10.0.19042', 'time_start': '2022-11-07 11:05:33',
         'time_end': '2022-07-01 11:08:21'},
        {'id': 2, 'status': 'pending', 'name': 'deletefile', 'uuid': 'db390940-a78e-4545-8cf3-bccac43ce9df', 'os': 'Windows',
         'os_distribution': 'Windows 10', 'os_version': '10.0.19042', 'time_start': '2022-07-01 14:05:33',
         'time_end': '2021-07-01 14:08:21'},
        {'id': 3, 'status': 'error', 'name': 'deletefileSMB', 'uuid': 'e9b5f78d-f6de-4ad0-b5b5-71ff3c01214d', 'os': 'Windows',
         'os_distribution': 'Windows 10', 'os_version': '10.0.19042', 'time_start': '2021-07-01 14:05:33',
         'time_end': '2021-07-01 14:08:21'},
        {'id': 4, 'name': 'deletefile', 'uuid': '825ffcac-e271-4f29-b2b2-7b5afb5cb9d4', 'os': 'Windows',
         'os_distribution': 'Windows 10', 'os_version': '10.0.19042', 'time_start': '2021-07-01 14:05:33',
         'time_end': '2021-07-01 14:08:21'},
        {'id': 5, 'name': 'deletefileSMB', 'uuid': '613ddb57-b541-4c76-b0a0-014ae8202cc9', 'os': 'Windows',
         'os_distribution': 'Windows 10', 'os_version': '10.0.19042', 'time_start': '2021-07-01 14:05:33',
         'time_end': '2021-07-01 14:08:21'},
        {'id': 6, 'name': 'deletefile', 'uuid': 'eb6d2783-5786-49c6-b730-e819538a64b0', 'os': 'Windows',
         'os_distribution': 'Windows 7', 'os_version': 'SP1', 'time_start': '2021-07-01 14:05:33',
         'time_end': '2021-07-01 14:08:21'},
        {'id': 7, 'name': 'deletefileNFS', 'uuid': '5e3082bd-9a38-4227-a30d-6f4332bcfd97', 'os': 'Windows',
         'os_distribution': 'Windows 10', 'os_version': '10.0.19042', 'time_start': '2021-07-01 14:05:33',
         'time_end': '2021-07-01 14:08:21'},
        {'id': 8, 'name': 'deletefile', 'uuid': '32fdb22e-e21e-4557-942f-9178b8ddcf40', 'os': 'Windows',
         'os_distribution': 'Windows 8', 'os_version': '', 'time_start': '2021-07-01 14:05:33',
         'time_end': '2021-07-01 14:08:21'},
    ]

    def __get_shown_columns(self):
        shown_columns = []
        for c in self.columns:
            if 'hide' not in c.keys():
                shown_columns.append(c)
            elif not c['hide']:
                shown_columns.append(c)
        return shown_columns

    def __all_columns_hidden(self):
        switch_values = [not c['hide'] for c in self.columns if 'hide' in c.keys()]
        if all(switch_values):
            return True
        return False

    def __all_columns_shown(self):
        switch_values = [c['hide'] for c in self.columns if 'hide' in c.keys()]
        if all(switch_values):
            return True
        return False

    def get_filterable_columns(self):
        return [c for c in self.columns if 'filter' in c.keys() and c['filter']]



    def __get_hideable_columns(self):
        column_dict = {}
        for c in self.columns:
            if 'hide' in c.keys():
                column_dict[c['field']] = c
        return column_dict

    def __show_hide_column(self, value, column_field_name):
        columns_by_field_name = self.__get_hideable_columns()
        columns_by_field_name[column_field_name]['hide'] = not value
        self.ui_self._props['columns'] = self.__get_shown_columns()
        if self.__all_columns_hidden():
            self.checkbox_showhideall.set_value(True)
        elif not self.__all_columns_shown():
            self.checkbox_showhideall.set_value(False)
        self.ui_self.update()

    def __show_hide_all(self, value):
        new_columns = []
        for c in self.columns:
            if 'hide' in c.keys():
                c['hide'] = not value
                new_columns.append(c)
            else:
                new_columns.append(c)
        self.columns = new_columns
        if value:
            self.ui_self._props['columns'] = self.columns
            for s in self.checkboxes_showhide_columns:
                s.set_value(True)
        else:
            self.ui_self._props['columns'] = []
            for s in self.checkboxes_showhide_columns:
                s.set_value(False)
        self.ui_self.update()

    def add_row(self, row):
        """ Add a row to the table """
        self.data.append(row)
        self.ui_self.update()

    def set_table_data(self, columns, data):
        """ Set the table data and columns """
        self.columns = columns
        self.data = data
        self.ui_self.update()


    def __set_filter_class(self, e, filter_class_obj):
        filterable_columns = self.get_filterable_columns()
        column = [c for c in filterable_columns if c['name'] == e.value][0]
        print(e)
        filter_class_obj.options = [x.name for x in column['filter']]
        filter_class_obj.props(remove='disable')
        filter_class_obj.update()


    def __create_filter(self, e, row, val_col):
        column = [c for c in self.get_filterable_columns() if c['name'] == 'os'][0]
        filter_class = [f for f in column['filter'] if f.name == e.value][0]
        row.remove(val_col)
        f_val = filter_class().create_comparison_value_input(val_col)

    def create_filter_menu_entry(self):
        filterable_columns = self.get_filterable_columns()
        filterable_columns_names = [c['name'] for c in filterable_columns]

        with self.filter_menu_entry_container as container:
            with ui.row().classes('w-full') as row:
                column_select = ui.select(filterable_columns_names, on_change=lambda e: self.__set_filter_class(e, filter_class_select))
                filter_class_select = ui.select([], on_change=lambda e: self.__create_filter(e, row, val_col)).props('disable')
                with ui.column() as val_col:
                    filter_value = ui.input().props('disable')
                btn = ui.button(on_click=lambda: container.remove(row)).props('icon=delete').classes('ml-auto mr-2')
                del btn._props['color']
                btn.classes('bg-cyan-800 text-white')

    def create_filter_menu(self):
        with ui.button(on_click=lambda: menu_filter.open()).props('icon=filter_alt') as btn_filter:
            del btn_filter._props['color']
            btn_filter.classes('bg-cyan-800 text-white')

        with ui.menu() as menu_filter, ui.column().classes('p-2'):
            menu_filter.classes('w-1/2')
            self.filter_menu_entry_container = ui.column().classes('w-full')
            self.create_filter_menu_entry()

            with ui.row():
                ui.button('add filter', on_click=self.create_filter_menu_entry).props('icon=add')

    def create(self):
        """ Create the table gui object """
        with ui.table(columns=self.__get_shown_columns(), rows=self.data,
                      pagination=10).classes(
                'w-full') as table:
            self.ui_self = table
            table.classes('table-striped')

            # add a search bar at the top-right of the table
            with table.add_slot('top'):
                with ui.row().classes('w-full flex justify-between items-center'):
                    ui.label('experiments table').classes('text-xl font-bold')

                    with ui.input(placeholder='Search') as search_input:
                        search_input.props('type=search').bind_value(table, 'filter')
                        search_input.classes('w-1/4')
                        with search_input.add_slot('append'):
                            ui.icon('search')

                    with ui.row():
                        self.create_filter_menu()

                        with ui.button(on_click=lambda: menu_columnselect.open()).props('icon=tune') as btn_columnselect:
                            del btn_columnselect._props['color']
                            btn_columnselect.classes('bg-cyan-800 text-white')

                            with ui.menu() as menu_columnselect, ui.column().classes('gap-0 p-2'):
                                self.checkbox_showhideall = ui.checkbox('Show all columns', value=False, on_change=lambda e: self.__show_hide_all(e.value))
                                self.checkbox_showhideall.props('color=cyan-800')
                                self.checkbox_showhideall.set_value(False)
                                for index, column in enumerate(self.__get_hideable_columns().values()):
                                    checkbox = ui.checkbox(column['label'], value=True,
                                                on_change=lambda e, c_name=column['field']: self.__show_hide_column(e.value, c_name))
                                    checkbox.props('color=cyan-800')
                                    self.checkboxes_showhide_columns.append(checkbox)
                                    checkbox.set_value(not column['hide'])
                                if self.__all_columns_hidden():
                                    self.checkbox_showhideall.set_value(True)

            # add buttons that links to the experiment page for each row
            table.add_slot('body-cell-btn', """
                 <q-td :props="props">
                    <q-btn flat round icon="add_circle" v-bind:href="'/experiment/'+ props.row['uuid']" class="text-slate-700" />
                 </q-td>
            """)
            table.add_slot('body-cell-publish', """
                 <q-td :props="props">
                    <q-btn flat round icon="publish" v-bind:href="" />
                 </q-td>
            """)
            table.add_slot('body-cell-status', """
                 <q-td :props="props" auto-width>
                    <q-icon name="check_circle" color="green" v-if="props.value == 'success'" size="2rem"/>
                    <q-icon name="error" color="warning" v-else-if="props.value == 'warning'" size="2rem"/>
                    <q-icon name="cancel" color="red" v-else-if="props.value == 'error'" size="2rem"/>
                    <q-icon name="pending" color="grey" v-else-if="props.value == 'pending'" size="2rem"/>
                    <p v-else>{{ props.value }} </p>
                 </q-td>
            """)



