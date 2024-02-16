# external imports
from nicegui import ui
from adare.config.configdirectory import WEBAPP_FILES

# configure logging
import logging
log = logging.getLogger(__name__)

# add pages (DON'T CHANGE ORDER and DON'T REMOVE ANY PAGE even if it seems unused)
from adare.gui.pages.experiment import index as experiment_page
from adare.gui.pages.request import index as request_page
from adare.gui.pages.login import index as login_page
from adare.gui.pages.experimentrun import index as runs_page
from adare.gui.pages.log import index as log_page

def runserver(port: int, quiet: bool = False):

    # get favicon path
    favicon_path = WEBAPP_FILES/'favicon.ico'

    # check if favicon exists
    if not favicon_path.is_file():
        log.error(f'favicon not found at {favicon_path.as_posix()}')
    else:
        log.info(f'favicon found at {favicon_path.as_posix()}')

    # run the app
    ui.run(title='adare', port=port, reload=False, favicon=favicon_path.as_posix())


if __name__ == '__main__':
    runserver(port=8080)