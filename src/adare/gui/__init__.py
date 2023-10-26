import pkg_resources
from pathlib import Path
from nicegui import ui
from adare.config.configdirectory import WEBAPP_STATIC_FILES

import logging
log = logging.getLogger(__name__)

def add_static_css_files():
    """ add all css files from static folder to the head of the html """
    for css_file in Path(WEBAPP_STATIC_FILES).glob('*.css'):
        ui.add_head_html(f"<style>{css_file.read_text()}</style>")
        log.debug(f'added css file {css_file}')


def add_bootstrap_icons():
    """ add bootstrap icons to the head of the html """
    ui.add_head_html(f'<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.3.0/font/bootstrap-icons.css">')
    log.debug(f'added bootstrap icons')