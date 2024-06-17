# from nicegui import ui
# import asyncio
#
# from adare.gui.components.AdvancedTable import AdvancedTable
# from adare.database.api.request import RequestSessionApi
# from adare.gui.storage import Storage
# from adare.config.gui import SLOT_STATUS_TABLE
# from adare.webappaccess.request import send_experiment_request
# from adare.gui.components.ErrorDialog import ErrorDialog
#
# import logging
# log = logging.getLogger(__name__)
#
#
# def _get_request_item_link(request, request_type: str):
#     if request_type == 'experiment':
#         return f'/experiment/{request.experiment.ulid}'
#     elif request_type == 'scenario':
#         return f'/scenario/{request.scenario.ulid}'
#     else:
#         log.error(f'unknown request type {request_type}')
#         return None
#
#
# class RequestPublishDialog:
#     msg: str
#     dialog: ui.dialog
#     close_button_visible: bool = False
#     loading_visible: bool = False
#
#     def __init__(self):
#         pass
#
#     def show(self):
#         self.dialog.open()
#
#     def hide(self):
#         self.dialog.close()
#         self.close_button_visible = False
#         self.loading_visible = False
#
#     def show_close_button(self):
#         self.close_button_visible = True
#
#     def set_msg(self, msg: str):
#         self.msg = msg
#
#     def show_loading(self):
#         self.loading_visible = True
#
#
#     def create(self):
#         with ui.dialog() as self.dialog:
#             with ui.card():
#                 with ui.card_section().classes('q-pa-sm'):
#                     ui.label('Publish').classes('text-h6')
#                 ui.separator()
#                 with ui.card_section().classes('q-pa-sm'):
#                     ui.label().bind_text(self, 'msg')
#                 with ui.card_section().classes('q-pa-sm'):
#                     ui.spinner('dots').bind_visibility(self, 'loading_visible')
#
#
# class RequestTable(AdvancedTable):
#     columns : list[dict] = [
#         {'name': 'status', 'label': 'status', 'field': 'status', 'required': True, 'sortable': False, 'align': 'left', 'hide': False},
#         {'name': 'title', 'label': 'title', 'field': 'title', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
#         {'name': 'ulid', 'label': 'ulid', 'field': 'ulid', 'required': True, 'sortable': True, 'align': 'left', 'hide': True},
#         {'name': 'description', 'label': 'description', 'field': 'description', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
#         {'name': 'type', 'label': 'type', 'field': 'type', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
#         {'name': 'upload', 'label': 'upload', 'field': 'upload', 'required': True, 'sortable': True, 'align': 'left', 'hide': False},
#     ]
#
#     columns_slot_map = {
#         'status': 'status',
#         'upload': 'upload'
#     }
#
#
#     def __init__(self):
#         super().__init__()
#
#     async def _publish(self, ulid: str):
#         log.info(f'publishing request with ulid {ulid}')
#         # send experiment request await it and get the result
#         self.request_publish_dialog.set_msg('Publishing request...')
#         self.request_publish_dialog.show_loading()
#         self.request_publish_dialog.show()
#         success, error_msg = await send_experiment_request(ulid)
#         print(success, error_msg)
#         if success:
#             self.request_publish_dialog.set_msg('Request published successfully')
#             self.request_publish_dialog.show_close_button()
#         self.request_publish_dialog.hide()
#
#         if not success:
#             self.error_dialog.set_error_msg(error_msg)
#             self.error_dialog.show()
#
#
#
#
#     def update_data(self):
#         with RequestSessionApi() as session:
#             self.data = [{
#                 'status': req.status.name if req.status else '',
#                 'title': req.title,
#                 'description': req.description,
#                 'ulid': req.ulid,
#                 'type': req.type,
#                 'link': _get_request_item_link(req, req.type),
#                 'upload': req.ulid,
#             } for req in session.get_all_requests()]
#         log.info(f'updated request table with {len(self.data)} entries')
#
#     def create(self):
#         self.error_dialog = ErrorDialog()
#         self.error_dialog.create()
#         self.request_publish_dialog = RequestPublishDialog()
#         self.request_publish_dialog.create()
#         data = self._get_shown_data()
#         with ui.table(columns=self._get_shown_columns(), rows=data, pagination=10).classes('w-full') as table:
#             self.table = table
#             table.bind_visibility(Storage, 'request_table_visible')
#             with table.add_slot('top'):
#                 with ui.row().classes('w-full flex justify-between items-center'):
#                     ui.button(icon='fullscreen', on_click=lambda b: self.toggle_table_fullscreen(table, b.sender)).props(
#                         'flat dense')
#
#                     with ui.input(placeholder='Search') as search_input:
#                         search_input.props('type=search').bind_value(table, 'filter')
#                         search_input.classes('w-1/4')
#                         with search_input.add_slot('append'):
#                             ui.icon('search')
#
#                     with ui.row():
#                         self.create_column_select_dropdown()
#
#             for col_slot, slot_type in self.columns_slot_map.items():
#                 slot_name = f'body-cell-{col_slot}'
#                 if slot_type == 'status':
#                     table.add_slot(slot_name, SLOT_STATUS_TABLE)
#                 elif slot_type == 'upload':
#                     table.add_slot(slot_name, """
#                         <q-td :props="props" auto-width>
#                             <q-btn flat dense round icon="upload" @click="$parent.$emit('publish', props.value)" />
#                         </q-td>
#                     """)
#
#             table.on('publish', lambda e: self._publish(e.args))