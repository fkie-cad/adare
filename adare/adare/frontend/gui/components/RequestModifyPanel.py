# from nicegui import ui
#
# from adare.database.api.request import RequestSessionApi
# from adare.frontend.gui.components.ErrorDialog import ErrorDialog
# from adare.frontend.gui.storage import Storage, toggle_request_table_modifypanel
# from adare.frontend.gui.components.RequestTable import RequestTable
#
# import logging
# log = logging.getLogger(__name__)
#
#
# class RequestModifyPanel:
#
#     req_table: RequestTable
#
#     req_title: str
#     req_description: str
#
#     input_scenario_ulid_shown: bool
#     input_experiment_ulid_shown: bool
#
#     err_dialog: ErrorDialog = None
#
#     def __init__(self, request_table):
#         self.err_dialog = ErrorDialog()
#         self.req_table = request_table
#
#     def create_request(self):
#         with RequestSessionApi() as session:
#             req_ulid, error_msg = session.add_request(Storage.request_type, self.req_title, self.req_description,  Storage.request_experiment_ulid, Storage.request_scenario_ulid)
#         if not error_msg:
#             log.info(f'created request (type: {Storage.request_type}) with title {self.req_title}')
#             toggle_request_table_modifypanel()
#         else:
#             self.__show_error_dialog(error_msg)
#
#
#     def __show_error_dialog(self, error_msg):
#         self.err_dialog.set_error_msg(error_msg)
#         self.err_dialog.show()
#
#     def create(self):
#         self.err_dialog.create()
#         with ui.element('div').classes('flex q-pa-md w-full shadow-24').bind_visibility(Storage, 'request_modify_panel_visible'):
#             with ui.card().props('flat square').classes('flex flex-column justify-center items-center w-full'):
#
#                 with ui.card_section().classes('flex justify-between q-px-md'):
#                     ui.label('Add new request').classes('text-h4')
#
#                 ui.separator()
#
#                 with ui.card_section().classes('w-full'):
#                     # add tabs to select request type
#                     with ui.tabs().classes('q-mb-md w-full').props('dense active-color="secondary" indicator-color="secondary" align="justify" narrow-indicator') as tabs:
#                         ui.tab('experiment')
#                         ui.tab('scenario')
#                     ui.separator()
#
#                     with ui.tab_panels(tabs).props('default').classes('q-mb-md w-full').bind_value(Storage, 'request_type'):
#                         with ui.tab_panel('experiment'):
#                             # add input field for request title
#                             ui.input(label='title').classes('q-mb-md shadow-1').props('square clearable outlined dense').bind_value(self, 'req_title')
#
#                             # add input field for request description
#                             ui.textarea(label='description', placeholder='start typing').classes('q-mb-md shadow-1').props('square clearable outlined dense').bind_value(self, 'req_description')
#
#                             # add input field for request experiment ulid
#                             ui.input(label='experiment ulid').classes('q-mb-md shadow-1').props('square clearable outlined dense').bind_value(Storage, 'request_experiment_ulid')
#
#                         with ui.tab_panel('scenario'):
#                             # add input field for request title
#                             ui.input(label='title').classes('q-mb-md shadow-1').props(
#                                 'square clearable outlined dense').bind_value(self, 'req_title')
#
#                             # add input field for request description
#                             ui.textarea(label='description', placeholder='start typing').classes(
#                                 'q-mb-md shadow-1').props('square clearable outlined dense').bind_value(self, 'req_description')
#
#                             # add input field for request scenario ulid
#                             ui.input(label='scenario ulid').classes('q-mb-md shadow-1').props('square clearable outlined dense').bind_value(Storage, 'request_scenario_ulid')
#
#                 ui.separator()
#
#                 with ui.card_section().classes('w-full flex justify-between q-px-md'):
#                     ui.button('cancel', on_click=toggle_request_table_modifypanel)
#                     ui.button('request', on_click=self.create_request)