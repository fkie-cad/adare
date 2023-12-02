from adare.webappaccess.publish_experiment import WebappPublishExperiment
from adare.gui.interfaces.login import LoginInterface

# configure logging
import logging
log = logging.getLogger(__name__)

class PublishExperimentInterface:
    webapp_interface = None
    user = None

    view_webapp_interface = None
    view_logged_in = None

    publish_trigger_functions = []
    publish_trigger_functions_missing_login = []
    publish_trigger_functions_failed = []
    publish_trigger_functions_connection_error = []
    publish_trigger_functions_already_published = []


    def __init__(self):
        self.webapp_interface = WebappPublishExperiment()

    def publish(self, experiment_uuid):
        result = self.webapp_interface.publish(LoginInterface.user, experiment_uuid)
        if result == 'success':
            for func in self.publish_trigger_functions:
                func()
        elif result == 'login missing':
            for func in self.publish_trigger_functions_missing_login:
                func()
        elif result == 'connection error':
            for func in self.publish_trigger_functions_connection_error:
                func()
        elif result == 'already published':
            for func in self.publish_trigger_functions_already_published:
                func()
        elif result == 'failed':
            for func in self.publish_trigger_functions_failed:
                func()

    def add_publish_trigger_function(self, func):
        self.publish_trigger_functions.append(func)

    def add_publish_trigger_function_missing_login(self, func):
        self.publish_trigger_functions_missing_login.append(func)

    def add_publish_trigger_function_failed(self, func):
        self.publish_trigger_functions_failed.append(func)

    def add_publish_trigger_function_connection_error(self, func):
        self.publish_trigger_functions_connection_error.append(func)

    def add_publish_trigger_function_already_published(self, func):
        self.publish_trigger_functions_already_published.append(func)


PublishExpIface = PublishExperimentInterface()