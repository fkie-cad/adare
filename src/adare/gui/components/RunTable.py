# external
from nicegui import ui

# internal imports
import adare.database.database as database
from adare.gui.components.AdvancedTable import AdvancedTable
from adare.gui.styles import btn_remove_color_prop
from adare.config.gui import STATUS_ICON_MAPPING, STATUS_COLOR_MAPPING, SLOT_STATUS_TABLE

# logging
import logging
log = logging.getLogger(__name__)


class RunTable(AdvancedTable):
    experiment_uuid: str = None

    columns: list[dict] = [
        {'name': 'status', 'label': 'status', 'field': 'status', 'required': True, 'sortable': False, 'align': 'left', 'hide': False},
        {'name': 'experiment', 'label': 'experiment', 'field': 'experiment_name', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'experiment_link', 'label': 'experiment link', 'field': 'experiment_link', 'required': True, 'sortable': False, 'align': 'left', 'hide': False},
        {'name': 'experiment uuid', 'label': 'experiment uuid', 'field': 'experiment_uuid', 'required': True, 'sortable': True, 'align': 'left', 'hide': True},
        {'name': 'uuid', 'label': 'uuid', 'field': 'uuid', 'required': True, 'sortable': True, 'align': 'left',
         'hide': False},
        {'name': 'timestamp start', 'label': 'timestamp start', 'field': 'timestamp_start', 'required': True, 'sortable': True, 'align': 'left', 'hide': True},
        {'name': 'timestamp end', 'label': 'timestamp end', 'field': 'timestamp_end', 'required': True, 'sortable': True, 'align': 'left', 'hide': True},
        {'name': 'status_action', 'label': 'status action', 'field': 'status_action', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'logfile_action', 'label': 'logfile action', 'field': 'logfile_action', 'required': True,
         'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'status_testset', 'label': 'status testset', 'field': 'status_testset', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'logfile_testset', 'label': 'logfile testset', 'field': 'logfile_testset', 'required': True,
         'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'status_vagrant', 'label': 'status vagrant', 'field': 'status_vagrant', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'logfile_vagrant', 'label': 'logfile vagrant', 'field': 'logfile_vagrant', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'details', 'label': 'details', 'field': 'details', 'required': True, 'sortable': False, 'align': 'left', 'hide': False},
    ]

    columns_slot_map = {
        'status': 'status',
        'experiment_link': 'experiment_link',
        'details': 'experimentrun_link',
        'status_action': 'status',
        'status_testset': 'status',
        'status_vagrant': 'status',
        'logfile_action': 'logfile',
        'logfile_testset': 'logfile',
        'logfile_vagrant': 'logfile',
    }

    def __init__(self, experiment_uuid: str = None, disabled_columns: list = None):
        self.experiment_uuid = experiment_uuid

        if disabled_columns:
            # remove columns from the list of columns
            self.columns = [c for c in self.columns if c['name'] not in disabled_columns]

        super().__init__()


    def update_data(self):
        with database.ExperimentApi() as db:
            if self.experiment_uuid:
                experiment_runs = db.get_experiment_runs_by_experiment_uuid(self.experiment_uuid)
            else:
                experiment_runs = db.get_all_experiment_runs()

            self.data = [
                {
                    'status': e.status.name,
                    'uuid': e.uuid,
                    'experiment_name': e.experiment.name,
                    'experiment_link': e.experiment.name,
                    'experiment_uuid': e.experiment.uuid,
                    'timestamp_start': e.timestamp_start,
                    'timestamp_end': e.timestamp_end,
                    'status_action': e.status_gui_automation.name,
                    'status_testset': e.status_parse_and_test.name,
                    'status_vagrant': e.status_vagrant.name,
                    'details': e.uuid,
                    'logfile_action': e.logfile_gui_automation.uuid,
                    'logfile_testset': e.logfile_parse_and_test.uuid,
                    'logfile_vagrant': e.logfile_vagrant.uuid,
                }
                for e in experiment_runs
            ]
        log.info(f'updated experiment run data (num_entries: {len(self.data)})')


    def create(self):
        data = self._get_shown_data()
        with ui.table(columns=self._get_shown_columns(), rows=data, pagination=10).classes('w-full') as table:
            self.table = table
            with table.add_slot('top'):
                with ui.row().classes('w-full flex justify-between items-center'):
                    ui.button(icon='fullscreen', on_click=lambda b: self.toggle_table_fullscreen(table, b.sender)).props(
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

                elif slot_type == 'experiment_link':
                    # add a slot with the name of the experiment followed by a button to open the experiment (on the right)
                    table.add_slot(slot_name, """
                        <q-td :props="props" auto-width>
                            <q-btn flat dense round icon="link" @click="$parent.$emit('open_experiment', props)" />
                        </q-td>
                    """)
                elif slot_type == 'experimentrun_link':
                    table.add_slot(slot_name, """
                        <q-td :props="props" auto-width>
                            <q-btn flat dense round icon="link" @click="$parent.$emit('open_experimentrun', props)" />
                        </q-td>
                    """)
                elif slot_type == 'logfile':
                    table.add_slot(slot_name, """
                        <q-td :props="props" auto-width>
                            <q-btn flat dense round icon="description" @click="$parent.$emit('open_log', props.value)" />
                        </q-td>
                    """)
                else:
                    log.error(f'unknown slot type: {slot_type}')
            table.on('open_experiment', lambda e: ui.open(f'/experiment/{e.args["row"]["experiment_uuid"]}', new_tab=True))
            table.on('open_experimentrun', lambda e: ui.open(f'/run/{e.args["row"]["uuid"]}', new_tab=True))
            table.on('open_log', lambda e: ui.open(f'/log/{e.args}', new_tab=True))