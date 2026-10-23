"""Tests for the playbook GUI-install engine's completion and login checks."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

import adare
from adare.hypervisor.qemu.vm_creator.playbook_creator import PlaybookVMCreationError, PlaybookVMCreator

pytestmark = pytest.mark.unit

PROFILES_DIR = Path(adare.__file__).parent.parent / 'appdata' / 'os-profiles'


def _creator() -> PlaybookVMCreator:
    # The step engine needs no VM state, so skip BaseVMCreator.__init__.
    return PlaybookVMCreator.__new__(PlaybookVMCreator)


def _wait_text(step: dict, screens: list[list[str]]) -> int:
    """Run a wait_text step against successive OCR reads; return polls used."""
    reads = iter(screens)
    lines = MagicMock(side_effect=lambda _frame: next(reads))
    with (
        patch.object(PlaybookVMCreator, '_screen_lines', lines),
        patch('adare.hypervisor.qemu.vm_creator.playbook_creator.time.sleep'),
    ):
        _creator()._wait_text(MagicMock(), {'timeout': 3600, **step})
    return lines.call_count


class TestWaitText:
    def test_returns_once_text_appears(self):
        polls = _wait_text({'text': 'Restart Now'}, [['Installing system'], ['Copying files'], ['Restart Now']])
        assert polls == 3

    def test_matches_any_of_several_texts_case_insensitively(self):
        assert _wait_text({'text': ['All done', 'has been installed']}, [['ALL DONE.']]) == 1

    def test_fail_text_aborts_immediately(self):
        with pytest.raises(PlaybookVMCreationError, match='installer crashed'):
            _wait_text(
                {'text': 'Restart Now', 'fail_on': ['installer crashed']},
                [['Installing system'], ["We're sorry; the Installer crashed."]],
            )

    def test_times_out_when_text_never_appears(self):
        with pytest.raises(PlaybookVMCreationError, match='never appeared'):
            _wait_text({'text': 'Restart Now', 'timeout': 0}, [['Installing system']])

    def test_gone_waits_for_text_to_disappear(self):
        assert _wait_text({'text': 'adare', 'gone': True}, [['adare', 'Password'], ['adare'], ['Activities']]) == 3

    def test_gone_times_out_while_text_stays(self):
        with pytest.raises(PlaybookVMCreationError, match='still on screen'):
            _wait_text({'text': 'adare', 'gone': True, 'timeout': 0}, [['adare']])

    def test_ocr_error_is_not_an_empty_screen(self):
        with (
            patch.dict('sys.modules', {'adare_cv_server': MagicMock()}),
            patch.object(PlaybookVMCreator, '_png_b64', return_value=''),
            patch('asyncio.run', return_value={'error': 'boom', 'all_text': []}),
            pytest.raises(PlaybookVMCreationError, match='OCR failed'),
        ):
            PlaybookVMCreator._screen_lines(b'')


class TestRunSteps:
    def test_failed_step_saves_a_screenshot(self, tmp_path):
        creator = _creator()
        steps = [{'action': 'wait_text', 'text': 'Restart Now', 'timeout': 0}]
        with (
            patch.object(PlaybookVMCreator, '_screen_lines', return_value=['Installing system']),
            patch.object(PlaybookVMCreator, '_save_shot') as save_shot,
            pytest.raises(PlaybookVMCreationError),
        ):
            creator._run_steps(MagicMock(), steps, tmp_path, 'install')
        save_shot.assert_called_once()
        assert save_shot.call_args.args[1] == tmp_path / 'install_00_FAILED.png'

    def test_required_wait_stable_fails_on_timeout(self, tmp_path):
        q = MagicMock()
        q.wait_stable.return_value = False
        steps = [{'action': 'wait_stable', 'timeout': 5, 'required': True}]
        with patch.object(PlaybookVMCreator, '_save_shot'), pytest.raises(PlaybookVMCreationError, match='never'):
            _creator()._run_steps(q, steps, tmp_path, 'install')

    def test_optional_wait_stable_timeout_continues(self, tmp_path):
        q = MagicMock()
        q.wait_stable.return_value = False
        _creator()._run_steps(q, [{'action': 'wait_stable', 'timeout': 5}], tmp_path, 'install')


def _playbook_profiles() -> list[tuple[str, dict]]:
    profiles = []
    for path in sorted(PROFILES_DIR.glob('*.yml')):
        data = yaml.safe_load(path.read_text())
        if data.get('install_mode') == 'playbook':
            profiles.append((path.stem, data))
    return profiles


@pytest.mark.parametrize(('name', 'profile'), _playbook_profiles(), ids=lambda v: v if isinstance(v, str) else '')
class TestPlaybookProfiles:
    def test_install_ends_by_confirming_completion_on_screen(self, name, profile):
        last = profile['install_steps'][-1]
        assert last['action'] == 'wait_text' and not last.get('gone'), (
            f'{name}: a still screen does not prove the installer finished'
        )
        assert last.get('fail_on'), f'{name}: list the installer failure texts so a crash fails fast'

    def test_verify_proves_the_login_succeeded(self, name, profile):
        gone = [s for s in profile['verify_steps'] if s['action'] == 'wait_text' and s.get('gone')]
        assert gone, f'{name}: verify_steps must check the greeter went away after login'


class TestProgressOutput:
    """Long waits must keep printing, so a run can be told apart from a hang."""

    def _printed(self, step: dict, screens: list[list[str]], stuck_s: float = 600.0) -> list[str]:
        mod = 'adare.hypervisor.qemu.vm_creator.playbook_creator'
        with (
            patch(f'{mod}.HEARTBEAT_S', 0),
            patch(f'{mod}.STUCK_S', stuck_s),
            patch(f'{mod}.print_step') as print_step,
        ):
            _wait_text(step, screens)
        return [c.args[0] for c in print_step.call_args_list]

    def test_wait_text_reports_elapsed_and_screen_text(self):
        out = self._printed({'text': 'Restart Now'}, [['Installing system'], ['Restart Now']])
        assert len(out) == 1
        assert "waiting for 'Restart Now'" in out[0] and 'screen: Installing system' in out[0]

    def test_wait_text_flags_a_frozen_screen(self):
        # q.dump() is a MagicMock returning the same frame every poll.
        out = self._printed({'text': 'Restart Now'}, [['Copying files'], ['Restart Now']], stuck_s=0)
        assert 'may be stuck' in out[0]

    def test_screen_text_cannot_inject_rich_markup(self):
        out = self._printed({'text': 'done'}, [['[red]x[/red]'], ['done']])
        assert '\\[red]' in out[0]

    def test_steps_print_timestamp_and_duration(self, tmp_path):
        q = MagicMock()
        q.wait_stable.return_value = True
        with patch('adare.hypervisor.qemu.vm_creator.playbook_creator.print_step') as print_step:
            _creator()._run_steps(q, [{'action': 'wait_stable', 'note': 'boot'}], tmp_path, 'install')
        header, done = (c.args[0] for c in print_step.call_args_list)
        assert header[2] == ':' and '[install 00] wait_stable  boot' in header
        assert done.strip().startswith('done in')
