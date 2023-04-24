from nicegui import ui

from adare.gui.login import LoginIface
from adare.gui.publish import PublishExpIface



def create_login_dialogs():
    with ui.dialog() as connection_error_dialog, ui.card():
        ui.label('Could not connect to the server.')
        ui.button('Close', on_click=connection_error_dialog.close)

    failed_login_dialog = ui.dialog()
    with failed_login_dialog, ui.card():
        ui.label('Wrong password or username.')
        ui.button('Close', on_click=failed_login_dialog.close)

    LoginIface.add_login_trigger_function_connection_error(connection_error_dialog.open)
    LoginIface.add_login_trigger_function_failed_login(failed_login_dialog.open)


def create_publish_experiment_dialogs():
    with ui.dialog() as connection_error_dialog, ui.card():
        ui.label('Could not connect to the server.')
        ui.button('Close', on_click=connection_error_dialog.close)

    with ui.dialog() as missing_login_dialog, ui.card():
        ui.label('Logging is missing. Please login first.')
        ui.button('Close', on_click=missing_login_dialog.close)

    with ui.dialog() as publish_success_dialog, ui.card():
        ui.label('Experiment got uploaded successfully.')
        ui.button('Close', on_click=publish_success_dialog.close)

    with ui.dialog() as publish_failed_dialog, ui.card():
        ui.label('Experiment could not be uploaded.')
        ui.button('Close', on_click=publish_failed_dialog.close)

    with ui.dialog() as already_published_dialog, ui.card():
        ui.label('Experiment is already published.')
        ui.button('Close', on_click=already_published_dialog.close)

    PublishExpIface.add_publish_trigger_function_connection_error(connection_error_dialog.open)
    PublishExpIface.add_publish_trigger_function_missing_login(missing_login_dialog.open)
    PublishExpIface.add_publish_trigger_function(publish_success_dialog.open)
    PublishExpIface.add_publish_trigger_function_failed(publish_failed_dialog.open)
    PublishExpIface.add_publish_trigger_function_already_published(already_published_dialog.open)