from nicegui import ui
from adare.gui.styles import btn_remove_color_prop
from adare.database.api.experiment import ExperimentApi

from adare.gui.interfaces.login import LoginIface
from adare.gui.components.AdvancedTable import AdvancedTable
from adare.config.gui import SLOT_STATUS_TABLE
from adare.webappaccess.experiment import check_experiment_published


class ExperimentTable(AdvancedTable):
    """ Table for showing experiments. """

    columns: list[dict] = [
        {'name': 'publish_status', 'label': 'publish status', 'field': 'publish_status', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'name', 'label': 'name', 'field': 'name', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'ulid', 'label': 'ulid', 'field': 'ulid', 'required': True, 'sortable': False, 'align': 'left', 'hide': False},
        {'name': 'os', 'label': 'os', 'field': 'os', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'os distribution', 'label': 'os distribution', 'field': 'os_distribution', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'os version', 'label': 'os version', 'field': 'os_version', 'required': True, 'sortable': True,
         'align': 'left', 'hide': False},
        {'name': 'experiment_link', 'label': 'experiment link', 'field': 'experiment_link', 'required': True, 'sortable': False, 'align': 'left', 'hide': False},
    ]

    columns_slot_map = {
        'experiment_link': 'experiment_link',
        'publish_status': 'status',
    }

    def __init__(self):
        super().__init__()
        self.publish_disabled = not LoginIface.logged_in

    def update_data(self):
        """ Retrieve data from database and update the table. """
        with ExperimentApi() as db:
            experiments = db.get_all_experiments()
            self.data = [
                {
                    'publish_status': e.publish_status.name,
                    'name': e.name,
                    'ulid': e.ulid,
                    'os': e.os_info.os,
                    'os_distribution': e.os_info.distribution,
                    'os_version': e.os_info.version,
                    'experiment_link': e.ulid,
                } for e in experiments
            ]


        if self.table:
            self.table.update()

    def create(self):
        """ Create the table gui object """

        data = self._get_shown_data()

        with ui.table(columns=self._get_shown_columns(), rows=data, pagination=10).classes('w-full table-striped') as self.table:
            table = self.table

            # add a search bar at the top-right of the table
            with table.add_slot('top'):
                with ui.row().classes('w-full flex justify-between items-center'):

                    ui.button(icon='fullscreen', on_click=lambda b: self.toggle_table_fullscreen(table, b.sender)).props('flat dense')

                    with ui.input(placeholder='Search') as search_input:
                        search_input.props('type=search').bind_value(table, 'filter')
                        search_input.classes('w-1/4')
                        with search_input.add_slot('append'):
                            ui.icon('search')

                    with ui.row():
                        with ui.button(on_click=lambda: menu_columnselect.open()).props('icon=tune') as btn_columnselect:
                            btn_remove_color_prop(btn_columnselect)
                            btn_columnselect.classes('bg-cyan-800 text-white')

                            with ui.menu() as menu_columnselect, ui.column().classes('gap-0 p-2'):
                                self.checkbox_showhideall = ui.checkbox('Show all columns', value=False, on_change=lambda e: self._show_hide_all(e.value))
                                self.checkbox_showhideall.props('color=cyan-800')
                                self.checkbox_showhideall.set_value(False)
                                for index, column in enumerate(self._get_hideable_columns().values()):
                                    checkbox = ui.checkbox(column['label'], value=True,
                                                on_change=lambda e, c_name=column['field']: self._show_hide_column(e.value, c_name))
                                    checkbox.props('color=cyan-800')
                                    self.checkboxes_showhide_columns.append(checkbox)
                                    checkbox.set_value(not column['hide'])
                                # if self.__all_columns_hidden():
                                #     self.checkbox_showhideall.set_value(True)


            for col_slot, slot_type in self.columns_slot_map.items():
                slot_name = f'body-cell-{col_slot}'
                if slot_type == 'status':
                    table.add_slot(slot_name, SLOT_STATUS_TABLE)
                elif slot_type == 'experiment_link':
                    # add a slot with the name of the experiment followed by a button to open the experiment (on the right)
                    table.add_slot(slot_name, """
                        <q-td :props="props" auto-width>
                            <q-btn flat dense round icon="link" @click="$parent.$emit('open_experiment', props.value)" />
                        </q-td>
                    """)

            table.on('open_experiment', lambda e: ui.open(f'/experiment/{e.args}', new_tab=True))



