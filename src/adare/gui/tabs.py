from adare.gui.colors import TAILWIND_GRADIENTS
from experimenttable import ExperimentTable

from nicegui import ui

class Tabs:
    tab_names = ['experiments', 'scenario']
    tabs = None
    panels = None

    def __switch_tab(self, msg):
        name = msg['args']
        self.tabs.props(f'model-value={name}')
        self.panels.props(f'model-value={name}')

    def create(self):
        with ui.tabs().props().classes('h-16').on('update:model-value', self.__switch_tab) as tabs:
            self.tabs = tabs
            for name in self.tab_names:
                ui.tab(name)

    def create_panel(self):
        with ui.tab_panels(self.tabs, value='experiments').classes('w-full') as panels:
            self.panels = panels
            with ui.tab_panel('experiments').classes('w-full'):
                experiment_table = ExperimentTable()
                experiment_table.create()

            with ui.tab_panel('scenario').classes('w-full'):
                ui.label(f'Content of z')