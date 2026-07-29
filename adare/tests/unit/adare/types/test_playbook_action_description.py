"""A step-level ``description:`` written beside an action must survive parsing.

    - keyboard:
        key: enter
      description: 'Case Information: Next'

``_structure_action`` structured only ``obj['<action_key>']``, so the sibling was
discarded — and ``converter.forbid_extra_keys`` guards the *inner* mapping, so the
outer key was never even flagged. 352 descriptions across the 42 Autopsy playbooks
were being silently thrown away, which is exactly the annotation that makes a
40-step GUI playbook readable.
"""

import pytest

pytestmark = pytest.mark.unit

from adare.types.playbook import (
    ActionTestAction,
    ClickAction,
    CommandAction,
    IdleAction,
    KeyboardAction,
    LoopAction,
    build_playbook_converter,
    structure_action,
)


class TestSiblingDescription:

    def test_keyboard_keeps_its_sibling_description(self):
        action = structure_action({
            'keyboard': {'key': 'enter'},
            'description': 'Case Information: Next',
        })
        assert isinstance(action, KeyboardAction)
        assert action.description == 'Case Information: Next'

    def test_click_keeps_its_sibling_description(self):
        action = structure_action({
            'click': {'target': {'text': 'Recent Activity'}},
            'description': 'Toggle Recent Activity',
        })
        assert isinstance(action, ClickAction)
        assert action.description == 'Toggle Recent Activity'

    def test_idle_keeps_its_sibling_description(self):
        action = structure_action({
            'idle': {'duration': 5},
            'description': 'Wait till Next Button becomes clickable',
        })
        assert isinstance(action, IdleAction)
        assert action.description == 'Wait till Next Button becomes clickable'

    def test_command_keeps_its_sibling_description(self):
        action = structure_action({
            'command': {'command': 'dir', 'shell': True},
            'description': 'List the directory',
        })
        assert isinstance(action, CommandAction)
        assert action.description == 'List the directory'

    def test_absent_description_stays_empty(self):
        action = structure_action({'keyboard': {'key': 'enter'}})
        assert action.description == ''

    def test_inner_description_still_works(self):
        action = structure_action({'keyboard': {'key': 'enter', 'description': 'inner'}})
        assert action.description == 'inner'

    def test_identical_inner_and_sibling_is_accepted(self):
        action = structure_action({
            'keyboard': {'key': 'enter', 'description': 'same'},
            'description': 'same',
        })
        assert action.description == 'same'

    def test_conflicting_inner_and_sibling_raises(self):
        with pytest.raises(ValueError, match='two different descriptions'):
            structure_action({
                'keyboard': {'key': 'enter', 'description': 'inner'},
                'description': 'outer',
            })

    def test_inline_test_form_keeps_its_sibling_description(self):
        action = structure_action({'test': 'test_report_exists', 'description': 'Check it'})
        assert isinstance(action, ActionTestAction)
        assert action.name == 'test_report_exists'
        assert action.description == 'Check it'

    def test_every_action_type_can_hold_a_description(self):
        """The guard below only fires for a *new* action type. Today every one of
        them has the field, and that is what makes the sibling always storable."""
        import attrs

        from adare.types.playbook import _ACTION_CLASSES

        without = [
            key for key, cls in _ACTION_CLASSES.items()
            if 'description' not in {field.name for field in attrs.fields(cls)}
        ]
        assert without == [], (
            f'these action types cannot hold a step description: {without}. '
            f'Either add the field or accept that playbooks may not annotate them.'
        )

    def test_action_without_a_description_field_raises(self, monkeypatch):
        """A future action type with no `description` must fail loudly rather than
        drop the annotation."""
        import attrs

        from adare.types import playbook as playbook_module

        @attrs.define
        class _NoDescriptionAction:
            value: str = ''

        monkeypatch.setitem(
            playbook_module._ACTION_CLASSES, 'teleport', _NoDescriptionAction
        )
        with pytest.raises(ValueError, match="has no 'description' field"):
            structure_action({'teleport': {'value': 'x'}, 'description': 'nowhere to put this'})

    def test_unknown_action_still_raises(self):
        with pytest.raises(ValueError, match='Unknown action'):
            structure_action({'teleport': {}, 'description': 'x'})


class TestNestedActionsKeepDescriptions:
    """Actions inside a `loop:` go through the same hook, so they must behave the
    same."""

    def test_loop_body_keeps_sibling_descriptions(self):
        converter = build_playbook_converter()
        action = converter.structure(
            {
                'times': 2,
                'actions': [
                    {'keyboard': {'key': 'enter'}, 'description': 'confirm'},
                    {'idle': {'duration': 1}},
                ],
            },
            LoopAction,
        )
        assert [a.description for a in action.actions] == ['confirm', '']


class TestRealPlaybooks:
    """The count the fix was measured against."""

    def test_autopsy_playbook_has_all_sixteen_descriptions(self):
        import pathlib

        from adare.types.playbook import parse_playbook

        playbook_path = (
            pathlib.Path(__file__).resolve().parents[5]
            / 'paper/experiments/4_autopsy_tool_regression_testing'
            / 'autopsy_4.21.0_webhistory/playbook.yml'
        )
        if not playbook_path.exists():
            pytest.skip(f'paper artifact not present at {playbook_path}')

        playbook = parse_playbook(playbook_path)
        described = [a.description for a in playbook.actions if getattr(a, 'description', '')]
        assert len(described) == 16
        assert 'Case Information: Next' in described
        assert described.count('Toggle Recent Activity') == 4
