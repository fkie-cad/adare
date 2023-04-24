from nicegui import ui
from adare.database import database
from adare.gui.extensions.advanced_table.filters import FilterEqual, FilterNotEqual, FilterContains
from adare.gui.extensions.advanced_table.advanced_table import AdvancedTable


class TestsTable(AdvancedTable):
    experiment_uuid: str = None
    table = None
    checkbox_showhideall = None
    checkboxes_showhide_columns = []
    database_path: str = None

    # filter
    filter_index_id_count = 0
    filter_container = None
    ui_filter_menu_entry_container = None
    filter_menu_items = {}

    columns: list[dict] = [
        {'name': 'status', 'label': 'status', 'field': 'status', 'required': True, 'sortable': False, 'align': 'left'},
        {'name': 'name', 'label': 'name', 'field': 'name', 'required': True, 'sortable': True, 'align': 'left', 'hide': False, 'filter': [FilterEqual, FilterNotEqual, FilterContains]},
        {'name': 'uuid', 'label': 'uuid', 'field': 'uuid', 'required': True, 'sortable': False, 'align': 'left', 'hide': False, 'filter': [FilterEqual, FilterNotEqual]},
        {'name': 'description', 'label': 'description', 'field': 'description', 'required': True, 'sortable': False, 'align': 'left', 'hide': False, 'filter': [FilterEqual, FilterNotEqual, FilterContains]},
        {'name': 'testfunction', 'label': 'testfunction', 'field': 'testfunction', 'required': True, 'sortable': False, 'align': 'left', 'hide': False, 'filter': [FilterEqual, FilterNotEqual, FilterContains]},
        {'name': 'parameters', 'label': 'parameters', 'field': 'parameters', 'required': True, 'sortable': False, 'align': 'left', 'hide': False},
        {'name': 'tool', 'label': 'tool', 'field': 'tool', 'required': True, 'sortable': False, 'align': 'left', 'hide': False, 'filter': [FilterEqual, FilterNotEqual, FilterContains]},
        {'name': 'tool command', 'label': 'tool command', 'field': 'tool command', 'required': True, 'sortable': False, 'align': 'left', 'hide': False, 'filter': [FilterEqual, FilterNotEqual, FilterContains]}
    ]

    data: list[dict] = None
    shown_rows: list[bool] = None

    def __init__(self, experiment_uuid: str):
        self.experiment_uuid = experiment_uuid
        super().__init__()

    def update_data(self):
        with database.ExperimentApi() as db:
            tests = db.get_experiment_by_uuid(self.experiment_uuid).tests
            self.data = [
                {
                    'status': t.result.status.name,
                    'name': t.name,
                    'uuid': t.uuid,
                    'description': t.description,
                    'testfunction': t.testfunction.name,
                    'parameters': {
                        'columns':[{'name': 'name', 'label': 'name', 'field': 'name', 'required': True, 'sortable': False, 'align': 'left'},
                                   {'name': 'value', 'label': 'value', 'field': 'value', 'required': True, 'sortable': False, 'align': 'right'}],
                        'rows': [{'name': p.parameter.name, 'value': p.value} for p in t.testparameterentry]
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
                    ui.label('').classes('text-xl font-bold')

                    with ui.input(placeholder='Search') as search_input:
                        search_input.props('type=search').bind_value(table, 'filter')
                        search_input.classes('w-1/4')
                        with search_input.add_slot('append'):
                            ui.icon('search')

                    with ui.row():
                        self.create_filter_menu()
                        self.create_column_select_dropdown()

            table.add_slot('body-cell-status', """
                 <q-td :props="props" auto-width>
                    <q-icon name="check_circle" color="green" v-if="props.value == 'success'" size="2rem"/>
                    <q-icon name="error" color="warning" v-else-if="props.value == 'warning'" size="2rem"/>
                    <q-icon name="cancel" color="red" v-else-if="props.value == 'failed'" size="2rem"/>
                    <q-icon name="pending" color="grey" v-else-if="props.value == 'no reached'" size="2rem"/>
                    <p v-else>{{ props.value }} </p>
                 </q-td>
            """)

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


