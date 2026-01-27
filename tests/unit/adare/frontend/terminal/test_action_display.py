import pytest
from adare.frontend.terminal.action_display import get_action_display_info, ActionType

def test_keyboard_action_display_single_key():
    action_data = {'key': 'enter'}
    display_info = get_action_display_info(ActionType.KEYBOARD, action_data)
    # Goal: "press 'enter'"
    assert display_info == "press 'enter'"

def test_keyboard_action_display_short_text():
    action_data = {'text': 'hello'}
    display_info = get_action_display_info(ActionType.KEYBOARD, action_data)
    # Goal: "type 'hello'"
    assert display_info == "type 'hello'"

def test_keyboard_action_display_long_text():
    # 20 chars
    text = '01234567890123456789'
    action_data = {'text': text}
    display_info = get_action_display_info(ActionType.KEYBOARD, action_data)
    # Goal: "type '012345678901234...'" (15 chars + ...)
    assert display_info == "type '012345678901234...'"

def test_keyboard_action_display_combination():
    action_data = {'combination': ['ctrl', 'c']}
    display_info = get_action_display_info(ActionType.KEYBOARD, action_data)
    # Existing behavior
    assert display_info == "press ctrl+c"

def test_keyboard_action_display_legacy_keys():
    action_data = {'keys': 'legacy'}
    display_info = get_action_display_info(ActionType.KEYBOARD, action_data)
    # Existing behavior
    assert display_info == "type 'legacy'"

def test_keyboard_action_display_fallback():
    action_data = {}
    display_info = get_action_display_info(ActionType.KEYBOARD, action_data)
    # Existing fallback
    assert display_info == "keyboard input"
