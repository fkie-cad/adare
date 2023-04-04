from adare.gui.extensions.table import TableExtension
from nicegui import ui


class ExperimentTable:
    ui_self = None
    switch_button_all = None
    switch_button_columns = []

    columns = [
        {'name': 'name', 'label': 'name', 'field': 'name', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'uuid', 'label': 'uuid', 'field': 'uuid', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'os', 'label': 'os', 'field': 'os', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'os distribution', 'label': 'os distribution', 'field': 'os_distribution', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'os version', 'label': 'os version', 'field': 'os_version', 'required': True, 'sortable': True,
         'align': 'left', 'hide': False},
        {'name': 'time start', 'label': 'time start', 'field': 'time_start', 'required': True, 'sortable': True,
         'align': 'left', 'hide': False},
        {'name': 'time end', 'label': 'time end', 'field': 'time_end', 'required': True, 'sortable': True,
         'align': 'left', 'hide': True},
        {'name': 'btn', 'label': '', 'field': 'btn', 'required': False, 'sortable': False, 'align': 'right'},
    ]
    data = [
        {'id': 0, 'name': 'deletefile', 'uuid': '738d01fa-94f0-4977-90f8-2ac9d9fed464', 'os': 'Windows', 'os_distribution': 'Windows 10', 'os_version': '10.0.19042', 'time_start': '2022-07-01 14:05:33', 'time_end': '2022-07-01 14:08:21'},
        {'id': 1, 'name': 'deletefile', 'uuid': 'ae6753b1-bfbf-4655-b937-7b3426a0ab60', 'os': 'Windows',
         'os_distribution': 'Windows 10', 'os_version': '10.0.19042', 'time_start': '2022-11-07 11:05:33',
         'time_end': '2022-07-01 11:08:21'},
        {'id': 2, 'name': 'deletefile', 'uuid': 'db390940-a78e-4545-8cf3-bccac43ce9df', 'os': 'Windows',
         'os_distribution': 'Windows 10', 'os_version': '10.0.19042', 'time_start': '2022-07-01 14:05:33',
         'time_end': '2021-07-01 14:08:21'},
        {'id': 3, 'name': 'deletefileSMB', 'uuid': 'e9b5f78d-f6de-4ad0-b5b5-71ff3c01214d', 'os': 'Windows',
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

    def __get_hideable_columns(self):
        column_dict = {}
        for c in self.columns:
            if 'hide' in c.keys():
                column_dict[c['field']] = c
        return column_dict

    def __show_hide_column(self, value, column_field_name):
        columns_by_field_name = self.__get_hideable_columns()
        columns_by_field_name[column_field_name]['hide'] = not value['args']
        self.ui_self._props['columns'] = self.__get_shown_columns()
        switch_values = [c['hide'] for c in self.columns if 'hide' in c.keys()]
        if all(switch_values):
            self.switch_button_all.set_value(True)
        if False in switch_values:
            self.switch_button_all.set_value(False)
        self.ui_self.update()

    def __show_hide_all(self, value):
        new_columns = []
        for c in self.columns:
            c['hide'] = not value['args']
            new_columns.append(c)
        self.columns = new_columns
        if value['args']:
            self.ui_self._props['columns'] = self.columns
            for s in self.switch_button_columns:
                s.set_value(True)
        else:
            for s in self.switch_button_columns:
                s.set_value(False)
            self.ui_self._props['columns'] = []
        self.ui_self.update()

    def add_row(self, row):
        self.data.append(row)
        self.ui_self.update()

    def create(self):
        with ui.table(title='experiments', columns=self.__get_shown_columns(), rows=self.data,
                      pagination=10).classes(
                'w-100') as table:
            self.ui_self = table
            with table.add_slot('top-right'):
                with ui.input(placeholder='Search').props('type=search').bind_value(table, 'filter').add_slot('append'):
                    ui.icon('search')

            table.add_slot('body', """
                <q-tr :props="props">
                    <q-td v-for="col in props.cols" :key="col.name" :props="props">
                        <q-btn v-if="col.name == 'btn'" flat round icon="add_circle" v-bind:href="'/experiment/'+ props.cols[1].value" class="text-slate-700" />
                        <p v-else>{{ col.value }} </p>
                    </q-td>
                </q-tr>
            """)

            with table.add_slot('bottom-row'):
                self.switch_button_all = ui.switch('show all')
                self.switch_button_all.set_value(False)
                for c in self.columns:
                    column_label = c['field']
                    if column_label in self.__get_hideable_columns().keys():
                        switch = ui.switch(column_label)
                        switch.set_value(not self.__get_hideable_columns()[column_label]['hide'])
                        switch.on('update:model-value', lambda e, c_name=column_label: self.__show_hide_column(e, c_name))
                        self.switch_button_columns.append(switch)
                if all([not v['hide'] for v in self.__get_hideable_columns().values()]):
                    self.switch_button_all.set_value(True)
                self.switch_button_all.on('update:model-value', lambda e: self.__show_hide_all(e))


