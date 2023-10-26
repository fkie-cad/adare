from nicegui import ui
from pathlib import Path

import logging
log = logging.getLogger(__name__)


@ui.refreshable
def _log_view(log_lines: list[str]):
    with ui.card_section().classes('flex flex-col justify-start items-start h-full w-full'):
        with ui.element('div').classes('w-full shadow-2'):
            with ui.column().classes('w-full').style('row-gap: 0px;'):
                for i, line in enumerate(log_lines):
                    with ui.row().classes('w-full'):
                        with ui.column().classes('w-1/20'):
                            ui.html(f'<span class="text-gray-500">{i}</span>')
                        with ui.column().classes('w-17/20'):
                            ui.html(f'<span class="text-gray-500">{line}</span>')


class LogDisplay:
    log_path: Path
    log_content: list[str]
    log_content_shown: list[str]
    search_string: str

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.search_string = ''
        self.log_content = []
        self.log_content_shown = []

    def read_log(self):
        self.log_content = self.log_path.read_text().splitlines()

    # def search(self):
    #     self.log_content_shown = []
    #     for line in self.log_content:
    #         if self.search_string in line:
    #             self.log_content_shown += line + '\n'
    #     _log_view.refresh(self.log_content_shown)

    def create(self):
        self.read_log()
        self.log_content_shown = self.log_content

        # create card
        with ui.card().props('flat square').classes('w-full') as card:
            # create card header with search bar
            # with ui.card_section().classes('flex justify-between items-center'):
            #     # create input field for search
            #     with ui.input(on_change=self.search).bind_value(self, 'search_string').props('dense outlined'):
            #         ui.icon('search')

            # show the log file path
            with ui.card_section().classes('flex justify-between items-center'):
                ui.html(f'<span class="text-gray-500">{self.log_path}</span>')

            # display log data in card content with line numbers and scroll bar
            _log_view(self.log_content_shown)
