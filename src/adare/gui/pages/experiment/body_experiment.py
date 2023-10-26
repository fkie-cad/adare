# external imports
from nicegui import ui

# internal imports
from adare.gui.extensions.card_table import CardTable
from adare.gui.styles import STYLE_TEXT_MUTED_LARGE, STYLE_TEXT_MUTED_SMALL
from adare.database import database
from adare.gui.pages.experiment.tests_table import TestsTable


class BodyExperimentPage:
    experiment_uuid = None
    experiment_data = None
    data = None

    def __init__(self, uuid):
        self.experiment_uuid = uuid

    def load_data(self):
        with database.ExperimentApi() as db:
            exp = db.get_experiment_by_uuid(self.experiment_uuid)
            tests = []
            for test in exp.abstract_tests:
                tests.append({
                    'name': test.name,
                    'description': test.description,
                    'testfunction_name': test.testfunction.name,
                    'parameters': [(p.parameter.name,p.value) for p in test.testparameterentry],
                })
            self.experiment_data = {
                'uuid': exp.uuid,
                'name': exp.name,
                'description': exp.description,
                'os': exp.os_info.os,
                'os_distribution': exp.os_info.distribution,
                'os_version': exp.os_info.version,
                'os_architecture': exp.os_info.architecture,
                'os_language': exp.os_info.language,
                'time_start': exp.timestamp_start,
                'time_end': exp.timestamp_end,
                'duration': str(exp.timestamp_end - exp.timestamp_start),
                'status': exp.status.name,
                'status_vagrant': exp.status_vagrant.name,
                'status_gui_automation': exp.status_gui_automation.name,
                'status_parse_and_test': exp.status_parse_and_test.name,
                'logfile_vagrant': exp.logfile_vagrant,
                'logfile_gui_automation': exp.logfile_gui_automation,
                'logfile_parse_and_test': exp.logfile_parse_and_test,
                'tests': tests,
            }

    def show(self):
        self.load_data()
        with ui.card().classes('w-full leading-4').style('gap: 0'):
            with ui.row().classes('w-full items-center justify-between'):
                ui.label(f'name').classes(STYLE_TEXT_MUTED_LARGE)
                ui.label(f'uuid').classes(STYLE_TEXT_MUTED_LARGE)
            with ui.row().classes('w-full items-center justify-between mb-6'):
                ui.label(self.experiment_data['name']).classes('text-h5')
                ui.label(self.experiment_uuid).classes('text-h5')
            ui.separator()
            with ui.element('div').classes('row mt-6 w-full'):
                with ui.element('div').classes('col mx-5'):
                    with ui.row():
                        with ui.card().classes('w-full mb-2 p-0'):
                            with ui.row().classes('w-full justify-between items-center'):
                                with ui.column():
                                    ui.icon('bi-calendar').classes('text-4xl text-blue-400 m-4')
                                with ui.column():
                                    ui.label(self.experiment_data['time_start']).classes('text-xl')
                                with ui.column().classes('self-start'):
                                    ui.label('start time').classes(STYLE_TEXT_MUTED_SMALL+' mr-2 mt-1')
                    with ui.row().classes('mt-4'):
                        with ui.card().classes('w-full mb-2 p-0'):
                            with ui.row().classes('w-full justify-between items-center'):
                                with ui.column():
                                    ui.icon('bi-stopwatch').classes('text-4xl text-blue-400 m-4')
                                with ui.column():
                                    ui.label(self.experiment_data['duration']).classes('text-xl')
                                with ui.column().classes('self-start'):
                                    ui.label('duration').classes(STYLE_TEXT_MUTED_SMALL+' mr-2 mt-1')

                with ui.element('div').classes('col mx-5'):
                    table = CardTable()
                    columns = [
                        {'name': 'key', 'label': 'key', 'field': 'key', 'align': 'left', 'sortable': True},
                        {'name': 'value', 'label': 'value', 'field': 'value', 'align': 'left', 'sortable': True},
                    ]
                    data = [
                        {'key': 'os', 'value': self.experiment_data['os']},
                        {'key': 'distribution', 'value': self.experiment_data['os_distribution']},
                        {'key': 'version', 'value': self.experiment_data['os_version']},
                        {'key': 'architecture', 'value': self.experiment_data['os_architecture']},
                        {'key': 'language', 'value': self.experiment_data['os_language']},
                    ]
                    table.set_table_data(columns, data)
                    table.create('os information', dense=False)
                with ui.element('div').classes('col mx-5'):
                    table = CardTable()
                    columns = [
                        {'name': 'key', 'label': 'key', 'field': 'key', 'align': 'left', 'sortable': True},
                        {'name': 'value', 'display':'btn_status', 'label': 'value', 'field': 'value', 'align': 'left', 'sortable': True},
                        {'name': 'log_btn', 'label': 'value', 'display':'log_btn', 'field': 'log_btn', 'align': 'left', 'sortable': True},
                    ]
                    data = [
                        {'key': 'total', 'value': self.experiment_data['status'], 'log_btn': None},
                        {'key': 'vagrant', 'value': self.experiment_data['status_vagrant'], 'log_btn': self.experiment_data['logfile_vagrant']},
                        {'key': 'gui automation', 'value': self.experiment_data['status_gui_automation'], 'log_btn': self.experiment_data['logfile_gui_automation']},
                        {'key': 'parse and test', 'value': self.experiment_data['status_parse_and_test'], 'log_btn': self.experiment_data['logfile_parse_and_test']},
                    ]
                    table.set_table_data(columns, data)
                    table.create('status information',dense=False)
                with ui.element('div').classes('col mx-5'):
                    table = CardTable()
                    columns = [
                        {'name': 'key', 'label': 'key', 'field': 'key', 'align': 'left', 'sortable': True},
                        {'name': 'value', 'label': 'value', 'field': 'value', 'align': 'left', 'sortable': True},
                    ]
                    data = [
                    ]
                    table.set_table_data(columns, data)
                    table.create('further logs', dense=False)

            with ui.row().classes('mt-12 w-full'):
                table = TestsTable(self.experiment_uuid)
                table.create()
