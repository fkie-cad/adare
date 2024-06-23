# external imports
from nicegui import ui
from nicegui.background_tasks import create as create_background_task
import asyncio

# internal imports
from adare.frontend.gui.styles import STYLE_TEXT_MUTED_LARGE, STYLE_TEXT_MUTED_SMALL
from adare.database.api.experiment import ExperimentApi
from adare.frontend.gui.components.AbstractTestTable import AbstractTestTable
from adare.frontend.gui.components.RunTable import RunTable
from adare.webappaccess.experiment import check_experiment_published
from adare.frontend.gui.storage import Storage, show_request_modify_panel
from adare.config.gui import STATUS_ICON_MAPPING, STATUS_COLOR_MAPPING

import logging
log = logging.getLogger(__name__)


@ui.refreshable
def _chip_list(tags) -> None:
    for tag in tags:
        ui.element('q-chip').props(f'label="{tag}"').classes('q-mr-sm')


@ui.refreshable
def _publish_status(status: str) -> None:
    if status in STATUS_ICON_MAPPING.keys():
        with ui.icon(STATUS_ICON_MAPPING[status], size='3em', color=STATUS_COLOR_MAPPING[status]):
            ui.tooltip(status)

class ExperimentOverview:
    experiment_ulid = None
    experiment_data = None
    data = None

    def __init__(self, ulid: str):
        self.experiment_ulid = ulid

    def __open_experiment_request(self):
        show_request_modify_panel(ulid=self.experiment_ulid, req_type='experiment')

    def load_data(self):
        with ExperimentApi() as db:
            exp = db.get_experiment_by_ulid(self.experiment_ulid)
            run_counts = db.get_experiment_run_counts_by_status(self.experiment_ulid)

            self.experiment_data = {
                'ulid': exp.ulid,
                'name': exp.name,
                'description': exp.description,
                'os': exp.os_info.os,
                'os_distribution': exp.os_info.distribution,
                'os_version': exp.os_info.version,
                'os_architecture': exp.os_info.architecture,
                'os_language': exp.os_info.language,
                'tags': [tag.name for tag in exp.tags],
                'publish_status': exp.publish_status.name,
                'num_failed_runs': str(run_counts['failed']),
                'num_successful_runs': str(run_counts['success']),
            }

            # update publish status of experiment in a background task and update the experiment data
            create_background_task(check_experiment_published(self.experiment_ulid, force_check=True, component_func=_publish_status))

    def __check_if_experiment_is_not_published(self):
        return self.experiment_data['publish_status'] == 'not published'

    def create(self):
        self.load_data()

        with ui.element('div').classes('flex justify-center w-full'):
            with ui.element('div').classes('q-pa-sm w-full'):
                with ui.card():
                    # card section with experiment name and ulid
                    with ui.card_section().classes('w-full q-pa-none'):
                        with ui.element('div').classes('row text-gray-600'):
                            with ui.element('div').classes(STYLE_TEXT_MUTED_SMALL+' col'):
                                ui.html('name')
                            with ui.element('div').classes(STYLE_TEXT_MUTED_SMALL+ ' col text-right'):
                                ui.html('ulid')
                        with ui.element('div').classes('row text-3xl'):
                            with ui.element('div').classes('col'):
                                ui.html().bind_content(self.experiment_data, 'name')
                            with ui.element('div').classes('col text-right'):
                                ui.html().bind_content(self.experiment_data, 'ulid')
                    ui.separator()

                    with ui.card_section().classes('row w-full justify-between'):
                        with ui.element('div').classes('col-8 q-pa-md'):
                            # Metadata Card
                            with ui.card().classes('q-pa-none').style('row-gap: 0'):
                                with ui.card_section().classes('w-full text-center text-2xl bg-primary text-white q-pa-sm'):
                                    ui.html('Metadata')
                                with ui.element('q-markup-table').props('dense').classes('w-full'):
                                    with ui.element('tbody'):
                                        with ui.element('tr'):
                                            with ui.element('td').classes('text-left'):
                                                ui.html('publish status')
                                            with ui.element('td').classes('text-right'):
                                                _publish_status(self.experiment_data['publish_status'])
                                        with ui.element('tr').bind_visibility(self, '__check_if_experiment_is_not_published'):
                                            with ui.element('td').classes('text-left'):
                                                ui.html('publish')
                                            with ui.element('td').classes('text-right'):
                                                ui.button('publish', on_click=self.__open_experiment_request, icon='publish')
                                        with ui.element('tr'):
                                            with ui.element('td').classes('text-left'):
                                                ui.html('description')
                                            with ui.element('td').classes('text-right'):
                                                ui.html().bind_content(self.experiment_data, 'description')
                                        with ui.element('tr'):
                                            with ui.element('td').classes('text-left'):
                                                ui.html('tags')
                                            with ui.element('td').classes('text-right'):
                                                _chip_list(self.experiment_data['tags'])
                                        with ui.element('tr'):
                                            with ui.element('td').classes('text-left'):
                                                ui.html('runs')
                                            with ui.element('td').classes('text-right'):
                                                with ui.element('div').classes('row text-center'):
                                                    with ui.element('div').classes('col'):
                                                        with ui.icon('check_circle', size='4em', color='green'):
                                                            ui.tooltip('successful runs')
                                                        ui.label().bind_text(self.experiment_data,
                                                                             'num_successful_runs').classes('text-center text-2xl')
                                                    with ui.element('div').classes('col'):
                                                        with ui.icon('cancel', size='4em', color='red'):
                                                            ui.tooltip('failed runs')
                                                        ui.label().bind_text(self.experiment_data, 'num_failed_runs').classes('text-center text-2xl')

                        with ui.element('div').classes('col-4 q-pa-md justify-end'):
                            with ui.card().classes('q-pa-none').style('row-gap: 0'):
                                with ui.card_section().classes('w-full text-center text-2xl bg-primary text-white q-pa-sm'):
                                    ui.html('Os Information')
                                with ui.element('q-markup-table').props('dense').classes('w-full'):
                                    with ui.element('tbody'):
                                        with ui.element('tr'):
                                            with ui.element('td').classes('text-left'):
                                                ui.html('os')
                                            with ui.element('td').classes('text-right'):
                                                ui.html().bind_content(self.experiment_data, 'os')
                                        with ui.element('tr'):
                                            with ui.element('td').classes('text-left'):
                                                ui.html('distribution')
                                            with ui.element('td').classes('text-right'):
                                                ui.html().bind_content(self.experiment_data, 'os_distribution')
                                        with ui.element('tr'):
                                            with ui.element('td').classes('text-left'):
                                                ui.html('version')
                                            with ui.element('td').classes('text-right'):
                                                ui.html().bind_content(self.experiment_data, 'os_version')
                                        with ui.element('tr'):
                                            with ui.element('td').classes('text-left'):
                                                ui.html('architecture')
                                            with ui.element('td').classes('text-right'):
                                                ui.html().bind_content(self.experiment_data, 'os_architecture')
                                        with ui.element('tr'):
                                            with ui.element('td').classes('text-left'):
                                                ui.html('language')
                                            with ui.element('td').classes('text-right'):
                                                ui.html().bind_content(self.experiment_data, 'os_language')

                    with ui.card_section().classes('row w-full justify-between'):
                        abstract_test_table = AbstractTestTable(self.experiment_ulid)
                        abstract_test_table.create()

                    with ui.card_section().classes('row w-full justify-between'):
                        run_table = RunTable(self.experiment_ulid, disabled_columns=['experiment_link'])
                        run_table.create()