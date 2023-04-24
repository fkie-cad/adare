from nicegui import ui
import sys

# add pages (DON'T CHANGE ORDER and DON'T REMOVE ANY PAGE even if it seems unused)
from adare.gui.page_index import index as index_page
from adare.gui.page_experiment import index as experiment_page

# get port from command line arguments
port = 5000
if len(sys.argv) > 1:
    port = int(sys.argv[1])

# run the app
ui.run(title='adare', port=port)