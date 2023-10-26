from nicegui import ui
from adare.gui.styles import btn_remove_color_prop
from adare.database import database

from adare.gui.interfaces.login import LoginIface
from adare.gui.extensions.advanced_table.advanced_table import AdvancedTable
from adare.gui.interfaces.publish import PublishExpIface


def toggle_table_fullscreen(table, btn) -> None:
    """ Toggle the fullscreen of the table. """
    table.toggle_fullscreen()
    btn.props('icon=fullscreen_exit' if table.is_fullscreen else 'icon=fullscreen')

class ExperimentTable(AdvancedTable):
    """ Table for showing experiments. """

    columns: list[dict] = [
        {'name': 'name', 'label': 'name', 'field': 'name', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'uuid', 'label': 'uuid', 'field': 'uuid', 'required': True, 'sortable': False, 'align': 'left', 'hide': False},
        {'name': 'os', 'label': 'os', 'field': 'os', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'os distribution', 'label': 'os distribution', 'field': 'os_distribution', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
        {'name': 'os version', 'label': 'os version', 'field': 'os_version', 'required': True, 'sortable': True,
         'align': 'left', 'hide': False},
    ]

    filters = {

    }

    publish_disabled: bool = None

    def __init__(self):
        super().__init__()
        self.publish_disabled = not LoginIface.logged_in

    def update_data(self):
        """ Retrieve data from database and update the table. """
        with database.ExperimentApi() as db:
            experiments = db.get_all_experiments()
            self.data = [
                {
                    'name': e.name,
                    'uuid': e.uuid,
                    'os': e.os_info.os,
                    'os_distribution': e.os_info.distribution,
                    'os_version': e.os_info.version,
                } for e in experiments
            ]

        if self.table:
            self.table.update()

    def _publish_experiment(self, table_data):
        """ Publish an experiment to a specified server. """
        experiment_uuid = table_data['args']['row']['uuid']
        PublishExpIface.publish(experiment_uuid)

    def update_publish_disabled(self):
        """
        Update the publish_disabled variable and update the table respectively.
        """
        LoginIface.update_login_status(None)
        self.publish_disabled = not LoginIface.logged_in
        # override slot
        self.table.add_slot('body-cell-publish', f"""
             <q-td :props="props">
                <q-btn flat round icon="publish" {'disable' if self.publish_disabled else ''} @click="$parent.$emit('action', props)" />
             </q-td>
        """)
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

                    ui.button(icon='fullscreen', on_click=lambda b: toggle_table_fullscreen(table, b.sender)).props('flat dense')

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

            # add buttons that links to the experiment page for each row
            table.add_slot('body-cell-btn', """
                 <q-td :props="props">
                    <q-btn flat round icon="add_circle" v-bind:href="'/experiment/'+ props.row['uuid']" class="text-slate-700" />
                 </q-td>
            """)
            table.add_slot('body-cell-publish', f"""
                 <q-td :props="props">
                    <q-btn flat round icon="publish" {'disable' if self.publish_disabled else ''} @click="$parent.$emit('action', props)" />
                 </q-td>
            """)
            table.add_slot('body-cell-status', """
                 <q-td :props="props" auto-width>
                    <q-icon name="check_circle" color="green" v-if="props.value == 'success'" size="2rem"/>
                    <q-icon name="error" color="warning" v-else-if="props.value == 'warning'" size="2rem"/>
                    <q-icon name="cancel" color="red" v-else-if="props.value == 'error'" size="2rem"/>
                    <q-icon name="pending" color="grey" v-else-if="props.value == 'pending'" size="2rem"/>
                    <p v-else>{{ props.value }} </p>
                 </q-td>
            """)
            table.on('action', lambda e: self._publish_experiment(e))



