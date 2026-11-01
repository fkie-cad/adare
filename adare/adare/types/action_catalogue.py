"""The action-type catalogue the web workbench's palette is built from.

One source of truth: the entries are generated from ``types.playbook._ACTION_CLASSES`` (the
table the playbook parser resolves actions through), so the advertised names and fields cannot
drift from what ADARE can actually parse. Only presentation (category, display name, icon,
description) and the seed ``default_params`` live in ``_PRESENTATION``; every field list comes
from the attrs classes themselves.

An entry's ``type`` is the parser's YAML action key, and the web UI serialises an action as
``{<type>: {<params>}}`` -- exactly the shape ``structure_action`` / ``parse_playbook`` accept.
"""

from __future__ import annotations

from typing import Any

import attrs

from adare.types.playbook import _ACTION_CLASSES

CATEGORIES = ('gui', 'control', 'data', 'system')

# key -> (category, display_name, icon (lucide name), description, default_params).
# default_params must parse as ``{key: default_params}`` (enforced by a unit test).
_PRESENTATION: dict[str, tuple[str, str, str, str, dict[str, Any]]] = {
    'click': (
        'gui',
        'Click',
        'mouse-pointer-click',
        'Click a target found by text or image',
        {'target': {'text': 'OK'}},
    ),
    'drag': (
        'gui',
        'Drag',
        'move',
        'Drag from one target to another',
        {'src': {'text': 'Source'}, 'dst': {'text': 'Destination'}},
    ),
    'keyboard': ('gui', 'Keyboard', 'keyboard', 'Type text, press a key or a key combination', {'text': 'hello'}),
    'scroll': ('gui', 'Scroll', 'mouse', 'Scroll in a direction', {'direction': 'down', 'amount': 3}),
    'goto': ('gui', 'Go to', 'crosshair', 'Move the pointer to a target without clicking', {'target': {'text': 'OK'}}),
    'idle': ('control', 'Idle', 'timer', 'Wait for a fixed duration', {'duration': 1.0}),
    'wait_until': (
        'control',
        'Wait until',
        'hourglass',
        'Wait until a condition on screen holds',
        {'condition': {'exists': {'text': 'Ready'}}, 'timeout': 60.0},
    ),
    'pause': ('control', 'Pause', 'pause', 'Pause the playbook until resumed', {'message': 'Paused'}),
    'block': ('control', 'Block', 'square-stack', 'Group actions together', {'actions': []}),
    'loop': (
        'control',
        'Loop',
        'repeat',
        'Repeat actions a number of times or over a list',
        {'times': 2, 'actions': []},
    ),
    'stop': ('control', 'Stop', 'octagon-x', 'Stop the playbook (optionally on a variable condition)', {}),
    'continue': ('control', 'Continue', 'skip-forward', 'Skip the rest of the current loop iteration or block', {}),
    'screenshot': ('data', 'Screenshot', 'camera', 'Capture a screenshot', {}),
    'save_timestamp': ('data', 'Save timestamp', 'clock', 'Save the current time to a variable', {'variable': 'ts'}),
    'save_variable': (
        'data',
        'Save variable',
        'variable',
        'Save a value or Jinja2 expression to a variable',
        {'name': 'my_var', 'value': 'value'},
    ),
    'pull': ('data', 'Pull file', 'download', 'Pull a file or folder from the guest', {'src': '/path/in/guest'}),
    'snapshot_filesystem': (
        'data',
        'Snapshot filesystem',
        'hard-drive',
        'Capture a filesystem snapshot into a variable',
        {'variable': 'snapshot_before'},
    ),
    'pull_changed_files': (
        'data',
        'Pull changed files',
        'files',
        'Pull the files that changed between two filesystem snapshots',
        {'snapshot_before': 'snapshot_before', 'snapshot_after': 'snapshot_after'},
    ),
    'command': ('system', 'Command', 'terminal', 'Execute a shell command in the guest', {'command': 'echo hello'}),
    'test': ('system', 'Test', 'flask-conical', 'Run a test function defined in the playbook', {'name': 'my_test'}),
}


def _field_names(cls: type, *, required: bool) -> list[str]:
    return [f.name for f in attrs.fields(cls) if (f.default is attrs.NOTHING) == required]


def build_action_catalogue() -> list[dict[str, Any]]:
    """One palette entry per action class the parser knows, in the parser's own order."""
    entries = []
    for key, cls in _ACTION_CLASSES.items():
        category, display_name, icon, description, default_params = _PRESENTATION.get(
            key, ('system', key.replace('_', ' ').capitalize(), 'puzzle', '', {})
        )
        entries.append(
            {
                'type': key,
                'category': category,
                'display_name': display_name,
                'description': description,
                'icon': icon,
                'default_params': default_params,
                'required_fields': _field_names(cls, required=True),
                'optional_fields': _field_names(cls, required=False),
            }
        )
    return entries
