import pkg_resources
from pathlib import Path
from nicegui import ui

STATIC_DIR = pkg_resources.resource_filename('adare.gui', 'static')

def add_static_css_files():
    """ add all css files from static folder to the head of the html """
    for css_file in Path(STATIC_DIR).glob('*.css'):
        ui.add_head_html(f"<style>{css_file.read_text()}</style>")