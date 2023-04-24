from nicegui import ui


class CardTable:
    """ card with a simple table inside """

    table = None
    data: list = None
    columns: list = None

    def set_table_data(self, columns: list, data: list):
        """ set table data """
        self.columns = columns
        self.data = data

    def update_table_data(self, data: list):
        """ update table data """
        self.data = data
        self.table.update()

    def create(self, label:str, dense=False):
        """ create table """
        with ui.card().classes('w-full no-padding').style('gap: 0'):
            ui.label(label).classes('w-full grid place-content-center h-10 text-center text-white text-bold bg-primary')
            with ui.row().classes('w-full'):
                props_str = 'hide-header table-style="font-size: 1rem;"'
                if dense:
                    props_str += ' dense'

                with ui.table(self.columns, rows=self.data).props(props_str).classes('w-full bordered table-striped').classes('table-text-large') as table:
                    self.table = table
                    for col in self.columns:
                        if 'display' not in col.keys():
                            continue
                        if col['display'] == 'btn_status':
                            table.add_slot(f'body-cell-{col["field"]}',"""
                                <q-td :props="props">
                                    <q-icon name="check_circle" color="green" v-if="props.value == 'success'" size="2rem"/>
                                    <q-icon name="error" color="warning" v-else-if="props.value == 'warning'" size="2rem"/>
                                    <q-icon name="cancel" color="red" v-else-if="props.value == 'error'" size="2rem"/>
                                    <q-icon name="pending" color="grey" v-else-if="props.value == 'pending'" size="2rem"/>
                                 </q-td> 
                            """)
                        if col['display'] == 'log_btn':
                            with table.add_slot(f'body-cell-{col["field"]}') as slot:
                                with table.cell().classes('text-right') as td:
                                    ico = ui.icon('open_in_new').props('size="1.5rem"').classes('opacity-180 hover:text-indigo-600')
                                    ico.on('click', lambda x: col['function'](td))
