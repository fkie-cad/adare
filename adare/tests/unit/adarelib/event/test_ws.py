"""Tests for WsCommand system encode/decode logic."""

import pytest

from adarelib.event.ws import (
    BREAKPOINT,
    BREAKPOINTRESOLVE,
    DONE,
    ECHO,
    ECHOREPLY,
    EXEC,
    EXPERIMENT,
    LOG,
    SimpleStringMessage,
    StatusMessage,
    WsCommand,
)


class TestRegistry:
    """WsCommand._registry contains all command types and dispatches correctly."""

    def test_registry_contains_all_command_types(self):
        expected = {
            "EXEC",
            "DONE",
            "LOG",
            "EVENT",
            "EXPERIMENT",
            "ECHO",
            "ECHOREPLY",
            "BREAKPOINT",
            "BREAKPOINTRESOLVE",
        }
        assert expected == set(WsCommand._registry.keys())

    def test_registry_dispatches_to_correct_class(self):
        mapping = {
            "EXEC": EXEC,
            "DONE": DONE,
            "LOG": LOG,
            "EXPERIMENT": EXPERIMENT,
            "ECHO": ECHO,
            "ECHOREPLY": ECHOREPLY,
            "BREAKPOINT": BREAKPOINT,
            "BREAKPOINTRESOLVE": BREAKPOINTRESOLVE,
        }
        for command_type, cls in mapping.items():
            assert WsCommand._registry[command_type] is cls


class TestExecRoundtrip:
    """EXEC encode then decode preserves all fields."""

    def test_roundtrip_with_all_fields(self):
        original = EXEC(command="ls -la", shell=True, cwd="/tmp")
        encoded = original.encode()
        decoded = WsCommand.decode(encoded)
        assert isinstance(decoded, EXEC)
        assert decoded.command == "ls -la"
        assert decoded.shell is True
        assert decoded.cwd == "/tmp"

    def test_roundtrip_shell_false(self):
        original = EXEC(command="echo hello", shell=False, cwd="/home")
        decoded = WsCommand.decode(original.encode())
        assert decoded.shell is False

    def test_empty_cwd_default(self):
        original = EXEC(command="pwd", shell=True)
        assert original.cwd == ""
        decoded = WsCommand.decode(original.encode())
        assert decoded.cwd == ""

    def test_encoded_starts_with_prefix(self):
        encoded = EXEC(command="ls", shell=True).encode()
        assert encoded.startswith("EXEC: ")


class TestDoneRoundtrip:
    """DONE encode then decode preserves all StatusMessage fields."""

    def test_roundtrip_all_fields(self):
        original = DONE(
            name="step1",
            out_msg="success output",
            err_msg="warning text",
            error=True,
        )
        decoded = WsCommand.decode(original.encode())
        assert isinstance(decoded, DONE)
        assert decoded.name == "step1"
        assert decoded.out_msg == "success output"
        assert decoded.err_msg == "warning text"
        assert decoded.error is True


class TestLogRoundtrip:
    """LOG encode then decode preserves all StatusMessage fields."""

    def test_roundtrip_all_fields(self):
        original = LOG(
            name="log_entry",
            out_msg="info message",
            err_msg="",
            error=False,
        )
        decoded = WsCommand.decode(original.encode())
        assert isinstance(decoded, LOG)
        assert decoded.name == "log_entry"
        assert decoded.out_msg == "info message"
        assert decoded.err_msg == ""
        assert decoded.error is False


class TestExperimentRoundtrip:
    """EXPERIMENT encode then decode preserves name."""

    def test_roundtrip(self):
        original = EXPERIMENT(name="my_experiment_v2")
        decoded = WsCommand.decode(original.encode())
        assert isinstance(decoded, EXPERIMENT)
        assert decoded.name == "my_experiment_v2"


class TestEchoRoundtrip:
    """ECHO encode then decode preserves data."""

    def test_roundtrip(self):
        original = ECHO(data="ping_payload_123")
        decoded = WsCommand.decode(original.encode())
        assert isinstance(decoded, ECHO)
        assert decoded.data == "ping_payload_123"


class TestEchoReplyRoundtrip:
    """ECHOREPLY encode then decode preserves data."""

    def test_roundtrip(self):
        original = ECHOREPLY(data="pong_response_456")
        decoded = WsCommand.decode(original.encode())
        assert isinstance(decoded, ECHOREPLY)
        assert decoded.data == "pong_response_456"


class TestBreakpointRoundtrip:
    """BREAKPOINT encode then decode produces correct instance."""

    def test_roundtrip(self):
        original = BREAKPOINT()
        encoded = original.encode()
        assert encoded == "BREAKPOINT"
        decoded = WsCommand.decode("BREAKPOINT: anything")
        assert isinstance(decoded, BREAKPOINT)


class TestBreakpointResolveRoundtrip:
    """BREAKPOINTRESOLVE encode then decode produces correct instance."""

    def test_roundtrip(self):
        original = BREAKPOINTRESOLVE()
        encoded = original.encode()
        assert encoded == "BREAKPOINTRESOLVE"
        decoded = WsCommand.decode("BREAKPOINTRESOLVE: anything")
        assert isinstance(decoded, BREAKPOINTRESOLVE)


class TestErrorCases:
    """WsCommand.decode error handling."""

    def test_unknown_command_type_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown command_type 'BOGUS'"):
            WsCommand.decode("BOGUS: some_data")

    def test_no_colon_returns_none(self):
        result = WsCommand.decode("no_colon_here")
        assert result is None

    def test_decode_base64_yaml_no_colon_returns_none(self):
        result = WsCommand._decode_base64_yaml("no_colon_here")
        assert result is None


class TestStatusMessageSharedBehavior:
    """DONE and LOG both inherit from StatusMessage with identical structure."""

    def test_done_inherits_status_message(self):
        assert issubclass(DONE, StatusMessage)

    def test_log_inherits_status_message(self):
        assert issubclass(LOG, StatusMessage)

    def test_done_and_log_encode_same_structure(self):
        done = DONE(name="x", out_msg="o", err_msg="e", error=False)
        log = LOG(name="x", out_msg="o", err_msg="e", error=False)
        done_encoded = done.encode()
        log_encoded = log.encode()
        # Both start with their command_type prefix
        assert done_encoded.startswith("DONE: ")
        assert log_encoded.startswith("LOG: ")
        # The base64 payloads carry the same data (different prefix, same payload)
        done_payload = done_encoded.split(": ", 1)[1]
        log_payload = log_encoded.split(": ", 1)[1]
        assert done_payload == log_payload
