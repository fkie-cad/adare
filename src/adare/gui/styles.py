""" contains predefined styles for nicegui components """

STYLE_TEXT_MUTED_LARGE = 'text-gray-400 font-medium text-lg'
STYLE_TEXT_MUTED_SMALL = 'text-gray-400 font-medium text-sm'

def btn_remove_color_prop(btn):
    """Remove color property from button, due to color handling in nicegui"""
    del btn._props['color']


STATUS_ICON_MAP = {
    'success': 'check_circle',
    'warning': 'error',
    'failed': 'cancel',
    'not reached': 'pending',
}

STATUS_COLOR_MAP = {
    'success': 'green',
    'warning': 'warning',
    'failed': 'red',
    'not reached': 'grey',
}