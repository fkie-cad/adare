# external imports
from nicegui import ui
from nicegui.background_tasks import create as create_background_task
import asyncio
from datetime import datetime

# internal imports
from adare.gui.styles import STYLE_TEXT_MUTED_LARGE, STYLE_TEXT_MUTED_SMALL
from adare.database.api.experiment import ExperimentApi
from adare.config.gui import TIMESTAMP_FORMAT_SECONDS, STATUS_COLOR_MAPPING, STATUS_SYMBOL_MAPPING
from adare.gui.components.TestTable import TestTable

import logging
log = logging.getLogger(__name__)

@ui.refreshable
def _status_timeline(status: str, status_vagrant: str, status_action: str, status_testset: str):
    with ui.timeline(side='left'):
        # create timeline item for status vagrant
        ui.timeline_entry(body='', icon=STATUS_SYMBOL_MAPPING[status_vagrant], title='Vagrant', subtitle=status_vagrant).props(f'color="{STATUS_COLOR_MAPPING[status_vagrant]}"')
            # with tm.add_slot('title'):
            #     # create title with button at upper right corner (using inline-block)
            #     with ui.element('div').classes('inline-block w-full'):
            #         ui.button(icon='attachment', color='secondary').props("round dense size='sm'").classes('q-mx-sm')
            #         ui.html('Vagrant').classes('inline-block')

        # create timeline item for status action
        ui.timeline_entry(icon=STATUS_SYMBOL_MAPPING[status_action], title='Action', subtitle=status_action).props(f'color="{STATUS_COLOR_MAPPING[status_action]}"')

        # create timeline item for status testset
        ui.timeline_entry(icon=STATUS_SYMBOL_MAPPING[status_testset], title='Testset', subtitle=status_testset).props(f'color="{STATUS_COLOR_MAPPING[status_testset]}"')

        # create timeline item for status
        ui.timeline_entry(icon=STATUS_SYMBOL_MAPPING[status], title='Status', subtitle=status).props(f'color="{STATUS_COLOR_MAPPING[status]}"')


def _calc_timedelta_string(start: datetime, end: datetime):
    timedelta = end - start
    seconds = timedelta.total_seconds()

    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)

    return f'{minutes}m {remaining_seconds}s'


class ExperimentRunOverview:
    experimentrun_uuid = None
    data = None

    def __init__(self, uuid: str):
        self.experimentrun_uuid = uuid


    def load_data(self):
        with ExperimentApi() as db:
            exprun = db.get_experimentrun_by_uuid(self.experimentrun_uuid)

            self.data = {
                'uuid': exprun.uuid,
                'experiment_uuid': exprun.experiment.uuid,
                'experiment_name': exprun.experiment.name,
                'timestamp_start': exprun.timestamp_start.strftime(TIMESTAMP_FORMAT_SECONDS),
                'timestamp_end': exprun.timestamp_end.strftime(TIMESTAMP_FORMAT_SECONDS),

                # status
                'status': exprun.status.name,
                'status_action': exprun.status_gui_automation.name,
                'status_testset': exprun.status_parse_and_test.name,
                'status_vagrant': exprun.status_vagrant.name,

                # logfiles
                'logfile_action': exprun.logfile_gui_automation.uuid,
                'logfile_testset': exprun.logfile_parse_and_test.uuid,
                'logfile_vagrant': exprun.logfile_vagrant.uuid,

                # calculated values
                'duration': _calc_timedelta_string(exprun.timestamp_start, exprun.timestamp_end)

            }


    def __open_experiment(self, experiment_uuid: str):
        ui.open(f'/experiment/{experiment_uuid}/', new_tab=True)


    def __open_logfile(self, logfile_uuid: str):
        ui.open(f'/log/{logfile_uuid}/', new_tab=True)


    def create(self):
        self.load_data()

        with ui.element('div').classes('flex justify-center w-full'):
            with ui.element('div').classes('q-pa-sm w-full'):
                with ui.card():
                    # card section with experimentrun uuid
                    with ui.card_section().classes('w-full q-pa-none'):
                        with ui.element('div').classes('row text-gray-600'):
                            with ui.element('div').classes(STYLE_TEXT_MUTED_SMALL+' col'):
                                ui.html('')
                            with ui.element('div').classes(STYLE_TEXT_MUTED_SMALL+ ' col text-right'):
                                ui.html('uuid')
                        with ui.element('div').classes('row text-3xl'):
                            with ui.element('div').classes('col'):
                                ui.html('Experiment Run')
                            with ui.element('div').classes('col text-right'):
                                ui.html().bind_content(self.data, 'uuid')
                    ui.separator()

                    with ui.card_section().classes('row w-full justify-between'):
                        with ui.element('div').classes('col-4 q-pa-md'):
                            # create a metadata table
                            with ui.card().classes('q-pa-none').style('row-gap: 0'):
                                with ui.card_section().classes('w-full text-center text-2xl bg-primary text-white q-pa-sm'):
                                    ui.html('Metadata')
                                with ui.element('q-markup-table').props('dense').classes('w-full'):
                                    with ui.element('tbody'):
                                        with ui.element('tr'):
                                            with ui.element('td').classes('text-left'):
                                                ui.html('experiment')
                                            with ui.element('td').classes('text-right'):
                                                with ui.element('div').classes('inline-block'):
                                                    ui.label().bind_text(self.data, 'experiment_name').classes('inline-block')
                                                    ui.button(icon='open_in_new', color='secondary', on_click=lambda x: self.__open_experiment(self.data['experiment_uuid'])).props("round dense size='sm'").classes('q-ml-sm')
                                        with ui.element('tr'):
                                            with ui.element('td').classes('text-left'):
                                                ui.html('experiment uuid')
                                            with ui.element('td').classes('text-right'):
                                                ui.label().bind_text(self.data, 'experiment_uuid')
                                        with ui.element('tr'):
                                            with ui.element('td').classes('text-left'):
                                                ui.html('start')
                                            with ui.element('td').classes('text-right'):
                                                ui.label().bind_text(self.data, 'timestamp_start')
                                        with ui.element('tr'):
                                            with ui.element('td').classes('text-left'):
                                                ui.html('end')
                                            with ui.element('td').classes('text-right'):
                                                ui.label().bind_text(self.data, 'timestamp_end')
                                        with ui.element('tr'):
                                            with ui.element('td').classes('text-left'):
                                                ui.html('duration')
                                            with ui.element('td').classes('text-right'):
                                                ui.label().bind_text(self.data, 'duration')

                            # create logfile table
                            with ui.card().classes('q-pa-none q-my-xl').style('row-gap: 0'):
                                with ui.card_section().classes('w-full text-center text-2xl bg-primary text-white q-pa-sm'):
                                    ui.html('Logfiles')
                                with ui.element('q-markup-table').props('dense').classes('w-full'):
                                    with ui.element('tbody'):
                                        with ui.element('tr'):
                                            with ui.element('td').classes('text-left'):
                                                ui.html('vagrant')
                                            with ui.element('td').classes('text-right'):
                                                ui.button(icon='open_in_new', color='secondary', on_click=lambda x: self.__open_logfile(self.data['logfile_vagrant'])).props("round dense size='sm'").classes('q-ml-sm')
                                        with ui.element('tr'):
                                            with ui.element('td').classes('text-left'):
                                                ui.html('action')
                                            with ui.element('td').classes('text-right'):
                                                ui.button(icon='open_in_new', color='secondary', on_click=lambda x: self.__open_logfile(self.data['logfile_action'])).props("round dense size='sm'").classes('q-ml-sm')
                                        with ui.element('tr'):
                                            with ui.element('td').classes('text-left'):
                                                ui.html('testset')
                                            with ui.element('td').classes('text-right'):
                                                ui.button(icon='open_in_new', color='secondary', on_click=lambda x: self.__open_logfile(self.data['logfile_testset'])).props("round dense size='sm'").classes('q-ml-sm')

                        with ui.element('div').classes('col-8 q-pa-md'):
                            _status_timeline(self.data['status'], self.data['status_vagrant'], self.data['status_action'], self.data['status_testset'])

                    # create a table with all tests and their results
                    with ui.card_section().classes('w-full q-pa-none'):
                        test_table = TestTable(self.experimentrun_uuid)
                        test_table.create()

