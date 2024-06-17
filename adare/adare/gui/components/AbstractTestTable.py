from nicegui import ui
from adare.database.api.experiment import ExperimentApi
from adare.gui.components.AdvancedTable import AdvancedTable
from adare.config.gui import SLOT_STATUS_TABLE

import logging
log = logging.getLogger(__name__)


class AbstractTestTable(AdvancedTable):
    experiment_ulid: str = None

    columns: list[dict] = [
        {'name': 'name', 'label': 'name', 'field': 'name', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'ulid', 'label': 'ulid', 'field': 'ulid', 'required': True, 'sortable': False, 'align': 'left', 'hide': True},
        {'name': 'description', 'label': 'description', 'field': 'description', 'required': True, 'sortable': False, 'align': 'left', 'hide': False},
        {'name': 'testfunction', 'label': 'testfunction', 'field': 'testfunction', 'required': True, 'sortable': False, 'align': 'left', 'hide': False},
        {'name': 'parameters', 'label': 'parameters', 'field': 'parameters', 'required': True, 'sortable': False, 'align': 'left', 'hide': False},
        {'name': 'tool', 'label': 'tool', 'field': 'tool', 'required': True, 'sortable': False, 'align': 'left', 'hide': False},
        {'name': 'tool command', 'label': 'tool command', 'field': 'tool command', 'required': True, 'sortable': False, 'align': 'left', 'hide': False}
    ]

    def __init__(self, experiment_ulid: str):
        self.experiment_ulid = experiment_ulid
        super().__init__()

    def update_data(self):
        with ExperimentApi() as db:
            tests = db.get_experiment_by_ulid(self.experiment_ulid).abstract_tests

            self.data = [
                {
                    'name': t.name,
                    'ulid': t.ulid,
                    'description': t.description,
                    'testfunction': t.testfunction.name,
                    'testfunction_type': t.testfunction.type,
                    'testfunction_description': t.testfunction.description,
                    'parameters': {
                        'columns':[{'name': 'name', 'label': 'name', 'field': 'name', 'required': True, 'sortable': False, 'align': 'left'},
                                   {'name': 'value', 'label': 'value', 'field': 'value', 'required': True, 'sortable': False, 'align': 'right'}],
                        'rows': [{'name': p.parameter.name, 'value': p.value} for p in t.parameters]
                    },
                    'tool': t.tool.name if t.tool else None,
                    'tool command': t.tool.command if t.tool else None,
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

            table.add_slot('body-cell-status', SLOT_STATUS_TABLE)

            table.add_slot('body-cell-parameters', """
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


