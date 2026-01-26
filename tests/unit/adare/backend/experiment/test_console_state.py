import pytest
import threading
from adare.backend.experiment.console_state import ConsoleState
from adarelib.constants import StatusEnum

class TestConsoleState:
    def test_log_success(self):
        state = ConsoleState()
        state.log_success("id1", "Success message", level=1)
        
        assert state.exists("id1")
        msg = state.messages["id1"]
        assert msg["message"] == "Success message"
        assert msg["status"] == StatusEnum.SUCCESS
        assert msg["level"] == 1

    def test_log_spinner_and_done(self):
        state = ConsoleState()
        state.log_spinner("spin1", "Loading")
        
        assert state.messages["spin1"]["spinner"] == "dots"
        
        state.log_spinner_done("spin1", StatusEnum.SUCCESS, "Done")
        assert state.messages["spin1"]["spinner"] is None
        assert state.messages["spin1"]["message"] == "Done"
        assert state.messages["spin1"]["status"] == StatusEnum.SUCCESS

    def test_snapshot_independence(self):
        state = ConsoleState()
        state.log_success("id1", "Initial")
        
        snap = state.get_snapshot()
        assert snap["id1"]["message"] == "Initial"
        
        # Modify state
        state.change_log_message("id1", "Changed")
        
        # Snapshot should maintain old value (shallow copy of dict of dicts - wait, are inner dicts copied?)
        # My implementation of snapshot: {k: v.copy() for k, v in self.messages.items()}
        # So yes, inner dicts are shallow copied. Changing a field in the NEW dict in state shouldn't affect snapshot.
        # But wait, change_log_message modifies the existing dictionary in place?
        # console_state.py: self.messages[identifier]['message'] = message
        # If I didn't replace the inner dict, but mutated it...
        
        # Let's check implementation of change_log_message:
        # self.messages[identifier]['message'] = message
        # This MUTATES the dict object.
        # If snapshot was a shallow copy of the outer dict, snap['id1'] points to the SAME dict object as state.messages['id1'].
        # So mutating it WILL affect the snapshot.
        # This means my snapshot implementation is NOT thread safe against mutation of inner dicts.
        
        # I need to verify this behavior and fix it if needed.
        # In `_generate_message` we read from snapshot.
        # If writer thread mutates the dict while reader thread reads it...
        # Reading a dict key is atomic in Python, but if we iterate or do complex things...
        
        # Update: I should check if `state.messages[identifier]` is replaced or mutated.
        # log_success replaces it: `self.messages[identifier] = {...}`.
        # change_log_message mutates it: `self.messages[identifier]['message'] = message`.
        
        # If I use `v.copy()` in snapshot, then I get a NEW dict for the inner dict.
        # `return {k: v.copy() for k, v in self.messages.items()}`
        # Then `snap['id1']` is a COPY.
        # Mutating `state.messages['id1']` will NOT affect `snap['id1']`.
        # So it IS thread safe.
        
        assert snap["id1"]["message"] == "Initial"
        assert state.messages["id1"]["message"] == "Changed"

