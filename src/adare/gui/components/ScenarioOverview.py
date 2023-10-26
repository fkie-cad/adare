# external imports
from nicegui import ui
from nicegui.background_tasks import create as create_background_task

# internal imports
from adare.gui.styles import STYLE_TEXT_MUTED_LARGE, STYLE_TEXT_MUTED_SMALL
from adare.database import database
from adare.webappaccess.experiment import check_experiment_published

import logging
log = logging.getLogger(__name__)

@ui.refreshable
def _publish_status(status: str) -> None:
    if status == 'unknown':
        with ui.icon('help', size='3em').classes('text-gray-500'):
            ui.tooltip(status)
    elif status == 'not published':
        with ui.timeline(side='left').props('dense'):
            with ui.icon('unpublished', size='3em').classes('text-gray-500'):
                ui.tooltip(status)
    else:
        # todo: update with more precise information such as dates in subtitle
        if status == 'in request':
            with ui.timeline(side='right', color='grey'):
                ui.timeline_entry('experiment request', title='request', icon='hourglass_empty', color='yellow', subtitle='DATE')
        if status == 'published':
            with ui.timeline(side='right'):
                ui.timeline_entry('experiment request', title='request', icon='hourglass_empty', color='green', subtitle='DATE')
                ui.timeline_entry('experiment published', title='published', icon='check_box', color='green', subtitle='DATE')


class ScenarioOverview:
    scenario_uuid = None
    scenario_data = None

    def __init__(self, uuid: str):
        self.scenario_uuid = uuid

    def load_data(self):
        with database.ExperimentApi() as db:
            sce = db.get_scenario_by_uuid(self.scenario_uuid)

            self.scenario_data = {
                'uuid': sce.uuid,
                'name': sce.name,
                'description': sce.description,
                'experiments': [
                    {
                        'uuid': exp.uuid,
                        'name': exp.name,
                    } for exp in sce.experiments.all()
                ]
            }

            # update publish status of experiment in a background task and update the experiment data
            # create_background_task(check_experiment_published(self.experiment_uuid, force_check=True, component_func=_publish_status))

    def __check_if_experiment_is_not_published(self):
        return self.scenario_data['publish_status'] == 'not published'

    def create(self):
        self.load_data()

        with ui.element('div').classes('flex justify-center w-full'):
            with ui.element('div').classes('q-pa-sm w-full'):
                with ui.card():
                    # card section with experiment name and uuid
                    with ui.card_section().classes('w-full q-pa-none'):
                        with ui.element('div').classes('row text-gray-600'):
                            with ui.element('div').classes(STYLE_TEXT_MUTED_SMALL+' col'):
                                ui.html('name')
                            with ui.element('div').classes(STYLE_TEXT_MUTED_SMALL+ ' col text-right'):
                                ui.html('uuid')
                        with ui.element('div').classes('row text-3xl'):
                            with ui.element('div').classes('col'):
                                ui.html().bind_content(self.experiment_data, 'name')
                            with ui.element('div').classes('col text-right'):
                                ui.html().bind_content(self.experiment_data, 'uuid')
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
