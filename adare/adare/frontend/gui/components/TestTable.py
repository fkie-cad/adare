from nicegui import ui
from adare.database.api.experiment import ExperimentApi
from adare.frontend.gui.components.AdvancedTable import AdvancedTable
from adare.config.gui import SLOT_STATUS_TABLE

import logging
log = logging.getLogger(__name__)


class TestTable(AdvancedTable):
    experimentrun_ulid: str = None

    columns: list[dict] = [
        {'name': 'result_status', 'label': 'result_status', 'field': 'result_status', 'required': True,
         'sortable': False, 'align': 'left', 'hide': False},
        {'name': 'result_details', 'label': 'result_details', 'field': 'result_details', 'required': True,
         'sortable': False, 'align': 'left', 'hide': False},
        {'name': 'name', 'label': 'name', 'field': 'name', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'ulid', 'label': 'ulid', 'field': 'ulid', 'required': True, 'sortable': False, 'align': 'left', 'hide': True},
        {'name': 'description', 'label': 'description', 'field': 'description', 'required': True, 'sortable': False, 'align': 'left', 'hide': True},
        {'name': 'testfunction', 'label': 'testfunction', 'field': 'testfunction', 'required': True, 'sortable': False, 'align': 'left', 'hide': False},
        {'name': 'parameters', 'label': 'parameters', 'field': 'parameters', 'required': True, 'sortable': False, 'align': 'left', 'hide': False},
        {'name': 'tool', 'label': 'tool', 'field': 'tool', 'required': True, 'sortable': False, 'align': 'left', 'hide': True},
        {'name': 'tool command', 'label': 'tool command', 'field': 'tool command', 'required': True, 'sortable': False, 'align': 'left', 'hide': True},
    ]

    columns_slot_map = {
        'result_status': 'status',
        'parameters': 'parameters',
    }

    def __init__(self, experimentrun_ulid: str):
        self.experimentrun_ulid = experimentrun_ulid
        super().__init__()

    def update_data(self):
        with ExperimentApi() as db:
            tests = db.get_experimentrun_by_ulid(self.experimentrun_ulid).tests

            self.data = [
                {
                    'name': t.abstracttest.name,
                    'ulid': t.abstracttest.ulid,
                    'description': t.abstracttest.description,
                    'testfunction': t.abstracttest.testfunction.name,
                    'testfunction_type': t.abstracttest.testfunction.type,
                    'testfunction_description': t.abstracttest.testfunction.description,
                    'parameters': {
                        'rows': [{'name': p.parameter.name, 'value': p.value} for p in t.abstracttest.parameters],
                        'columns': [
                            {'name': 'name', 'label': 'name', 'field': 'name', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
                            {'name': 'value', 'label': 'value', 'field': 'value', 'required': True, 'sortable': False, 'align': 'left', 'hide': False}
                        ]
                    },
                    'tool': t.abstracttest.tool.name if t.abstracttest.tool else None,
                    'tool command': t.abstracttest.tool.command if t.abstracttest.tool else None,
                    'result_status': t.result.status.name,
                    'result_details': t.result.details,
                } for t in tests
            ]

        if self.table:
            self.table.update()


    def create(self):
        """ Create the table gui object """
        data = self._get_shown_data()
        with ui.table(columns=self._get_shown_columns(), rows=data,
                      pagination=10).classes(
                'w-full') as table:
            self.table = table
            table.classes('table-striped')

            # add a search bar at the top-right of the table
            with table.add_slot('top'):
                with ui.row().classes('w-full flex justify-between items-center'):
                    ui.button(icon='fullscreen',
                              on_click=lambda b: self.toggle_table_fullscreen(table, b.sender)).props(
                        'flat dense')

                    with ui.input(placeholder='Search') as search_input:
                        search_input.props('type=search').bind_value(table, 'filter')
                        search_input.classes('w-1/4')
                        with search_input.add_slot('append'):
                            ui.icon('search')

                    with ui.row():
                        self.create_column_select_dropdown()

            for col_slot, slot_type in self.columns_slot_map.items():
                slot_name = f'body-cell-{col_slot}'
                if slot_type == 'status':
                    table.add_slot(slot_name, SLOT_STATUS_TABLE)
                elif slot_type == 'parameters':
                    table.add_slot(slot_name, """
                    <q-td key="name" :props="props">
                        <q-table
                            :rows="props.value.rows"
                            :columns="props.value.columns"
                            row-key="name"
                            hide-pagination
                            hide-header
                            dense
                        />
                    </q-td>
                    """)

