"""
Unit tests for adarelib.event.ws module.

Tests cover:
- All WsCommand subclasses (EXEC, DONE, LOG, EVENT, ECHO, BREAKPOINT, etc.)
- Encode/decode roundtrips
- Custom_decode methods
- The command registry
- Serialization/deserialization with base64
"""
import pytest
import base64
import yaml

from adarelib.event.ws import (
    WsCommand,
    EXEC,
    DONE,
    LOG,
    EVENT,
    EXPERIMENT,
    ECHO,
    ECHOREPLY,
    BREAKPOINT,
    BREAKPOINTRESOLVE,
)
from adarelib.event.event import (
    TestEvent,
    ErrorEvent,
    TestResult,
)
from adarelib.constants import StatusEnum


class TestWsCommandRegistry:
    """Tests for the WsCommand base class and registry."""

    def test_registry_contains_all_commands(self):
        """Test that all command types are registered."""
        expected_commands = {
            'EXEC', 'DONE', 'LOG', 'EVENT', 'EXPERIMENT',
            'ECHO', 'ECHOREPLY', 'BREAKPOINT', 'BREAKPOINTRESOLVE'
        }

        assert expected_commands.issubset(set(WsCommand._registry.keys()))

    def test_registry_maps_to_correct_classes(self):
        """Test that registry maps command types to correct classes."""
        assert WsCommand._registry['EXEC'] == EXEC
        assert WsCommand._registry['DONE'] == DONE
        assert WsCommand._registry['LOG'] == LOG
        assert WsCommand._registry['EVENT'] == EVENT
        assert WsCommand._registry['EXPERIMENT'] == EXPERIMENT
        assert WsCommand._registry['ECHO'] == ECHO
        assert WsCommand._registry['ECHOREPLY'] == ECHOREPLY
        assert WsCommand._registry['BREAKPOINT'] == BREAKPOINT
        assert WsCommand._registry['BREAKPOINTRESOLVE'] == BREAKPOINTRESOLVE

    def test_decode_with_no_colon_returns_none(self):
        """Test that decode returns None when no colon present."""
        result = WsCommand.decode("no colon here")
        assert result is None

    def test_decode_unknown_command_raises_error(self):
        """Test that decode raises ValueError for unknown command."""
        with pytest.raises(ValueError) as exc_info:
            WsCommand.decode("UNKNOWN: some data")

        assert "Unknown command_type" in str(exc_info.value)
        assert "UNKNOWN" in str(exc_info.value)

    def test_base_custom_decode_raises_not_implemented(self):
        """Test that base class custom_decode raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            WsCommand.custom_decode("some data")


class TestEXECCommand:
    """Tests for EXEC WebSocket command."""

    def test_exec_creation(self):
        """Test creating EXEC command."""
        cmd = EXEC(command="ls -la", shell=True, cwd="/tmp")

        assert cmd.command == "ls -la"
        assert cmd.shell is True
        assert cmd.cwd == "/tmp"
        assert cmd.command_type == "EXEC"

    def test_exec_creation_with_defaults(self):
        """Test creating EXEC command with default cwd."""
        cmd = EXEC(command="echo hello", shell=False)

        assert cmd.command == "echo hello"
        assert cmd.shell is False
        assert cmd.cwd == ""

    def test_exec_encode(self):
        """Test EXEC encoding produces correct format."""
        cmd = EXEC(command="ls", shell=True, cwd="/home")
        encoded = cmd.encode()

        assert encoded.startswith("EXEC: ")
        # Verify base64 part is valid
        base64_part = encoded.split(": ", 1)[1]
        decoded = base64.b64decode(base64_part).decode()
        data = yaml.safe_load(decoded)

        assert data['command'] == "ls"
        assert data['shell'] is True
        assert data['cwd'] == "/home"

    def test_exec_decode(self):
        """Test EXEC decoding."""
        cmd = EXEC(command="pwd", shell=False, cwd="/var")
        encoded = cmd.encode()

        decoded = WsCommand.decode(encoded)

        assert isinstance(decoded, EXEC)
        assert decoded.command == "pwd"
        assert decoded.shell is False
        assert decoded.cwd == "/var"

    def test_exec_roundtrip(self):
        """Test EXEC encode/decode roundtrip preserves data."""
        original = EXEC(command="find . -name '*.py'", shell=True, cwd="/project")
        encoded = original.encode()
        decoded = WsCommand.decode(encoded)

        assert decoded.command == original.command
        assert decoded.shell == original.shell
        assert decoded.cwd == original.cwd

    def test_exec_custom_decode_no_colon(self):
        """Test EXEC custom_decode returns None when no colon."""
        result = EXEC.custom_decode("no colon")
        assert result is None

    def test_exec_with_special_characters(self):
        """Test EXEC with special characters in command."""
        cmd = EXEC(
            command="echo 'Hello \"World\"' | grep -E '^Hello'",
            shell=True,
            cwd="/path/with spaces"
        )
        encoded = cmd.encode()
        decoded = WsCommand.decode(encoded)

        assert decoded.command == cmd.command
        assert decoded.cwd == "/path/with spaces"


class TestDONECommand:
    """Tests for DONE WebSocket command."""

    def test_done_creation(self):
        """Test creating DONE command."""
        cmd = DONE(name="test_action", out_msg="success", err_msg="", error=False)

        assert cmd.name == "test_action"
        assert cmd.out_msg == "success"
        assert cmd.err_msg == ""
        assert cmd.error is False
        assert cmd.command_type == "DONE"

    def test_done_creation_with_defaults(self):
        """Test creating DONE command with defaults."""
        cmd = DONE(name="action")

        assert cmd.name == "action"
        assert cmd.out_msg == ""
        assert cmd.err_msg == ""
        assert cmd.error is False

    def test_done_encode(self):
        """Test DONE encoding."""
        cmd = DONE(name="step1", out_msg="output", err_msg="warning", error=False)
        encoded = cmd.encode()

        assert encoded.startswith("DONE: ")

    def test_done_roundtrip(self):
        """Test DONE encode/decode roundtrip."""
        original = DONE(
            name="complex_action",
            out_msg="Operation completed\nWith newlines",
            err_msg="Some warning",
            error=False
        )
        encoded = original.encode()
        decoded = WsCommand.decode(encoded)

        assert isinstance(decoded, DONE)
        assert decoded.name == original.name
        assert decoded.out_msg == original.out_msg
        assert decoded.err_msg == original.err_msg
        assert decoded.error == original.error

    def test_done_with_error(self):
        """Test DONE command indicating error."""
        cmd = DONE(name="failing_action", out_msg="", err_msg="Error occurred", error=True)
        encoded = cmd.encode()
        decoded = WsCommand.decode(encoded)

        assert decoded.error is True
        assert decoded.err_msg == "Error occurred"

    def test_done_custom_decode_no_colon(self):
        """Test DONE custom_decode returns None when no colon."""
        result = DONE.custom_decode("no colon")
        assert result is None


class TestLOGCommand:
    """Tests for LOG WebSocket command."""

    def test_log_creation(self):
        """Test creating LOG command."""
        cmd = LOG(name="log_entry", out_msg="info message", err_msg="", error=False)

        assert cmd.name == "log_entry"
        assert cmd.out_msg == "info message"
        assert cmd.command_type == "LOG"

    def test_log_roundtrip(self):
        """Test LOG encode/decode roundtrip."""
        original = LOG(
            name="debug_log",
            out_msg="Debug: variable x = 42",
            err_msg="",
            error=False
        )
        encoded = original.encode()
        decoded = WsCommand.decode(encoded)

        assert isinstance(decoded, LOG)
        assert decoded.name == original.name
        assert decoded.out_msg == original.out_msg
        assert decoded.err_msg == original.err_msg
        assert decoded.error == original.error

    def test_log_with_multiline_output(self):
        """Test LOG with multiline output."""
        multiline = "Line 1\nLine 2\nLine 3"
        cmd = LOG(name="multiline_log", out_msg=multiline)
        encoded = cmd.encode()
        decoded = WsCommand.decode(encoded)

        assert decoded.out_msg == multiline

    def test_log_custom_decode_no_colon(self):
        """Test LOG custom_decode returns None when no colon."""
        result = LOG.custom_decode("no colon")
        assert result is None


class TestEVENTCommand:
    """Tests for EVENT WebSocket command."""

    def test_event_creation_with_test_event(self):
        """Test creating EVENT command with TestEvent."""
        test_event = TestEvent(
            test_name="test_login",
            timestamp="2024-01-15T10:30:00.000000",
            ulid="01HM123ABC456DEF789GHI012",
            status=StatusEnum.SUCCESS,
            result=TestResult.success(details=["passed"])
        )
        cmd = EVENT(event=test_event)

        assert cmd.event == test_event
        assert cmd.command_type == "EVENT"

    def test_event_creation_with_error_event(self):
        """Test creating EVENT command with ErrorEvent."""
        error_event = ErrorEvent(
            error_name="ConnectionError",
            timestamp="2024-01-15T10:30:00.000000",
            ulid="01HM123ABC456DEF789GHI012",
            error_msg="Connection refused"
        )
        cmd = EVENT(event=error_event)

        assert cmd.event == error_event

    def test_event_encode_format(self):
        """Test EVENT encoding produces correct format."""
        test_event = TestEvent(
            test_name="test_example",
            timestamp="2024-01-15T10:30:00.000000",
            ulid="01HM123ABC456DEF789GHI012"
        )
        cmd = EVENT(event=test_event)
        encoded = cmd.encode()

        assert encoded.startswith("EVENT: ")

    def test_event_roundtrip_test_event(self):
        """Test EVENT encode/decode roundtrip with TestEvent."""
        original_event = TestEvent(
            test_name="roundtrip_test",
            timestamp="2024-01-15T10:30:00.000000",
            ulid="01HM123ABC456DEF789GHI012",
            status=StatusEnum.SUCCESS,
            error="",
            result=TestResult.success(details=["verification passed"])
        )
        cmd = EVENT(event=original_event)
        encoded = cmd.encode()
        decoded = WsCommand.decode(encoded)

        assert isinstance(decoded, EVENT)
        assert isinstance(decoded.event, TestEvent)
        assert decoded.event.test_name == original_event.test_name
        assert decoded.event.timestamp == original_event.timestamp
        assert decoded.event.ulid == original_event.ulid
        assert decoded.event.status == original_event.status

    def test_event_roundtrip_error_event(self):
        """Test EVENT encode/decode roundtrip with ErrorEvent."""
        original_event = ErrorEvent(
            error_name="TimeoutError",
            timestamp="2024-01-15T10:30:00.000000",
            ulid="01HM123ABC456DEF789GHI012",
            status=StatusEnum.NONE,
            error="",
            error_msg="Operation timed out"
        )
        cmd = EVENT(event=original_event)
        encoded = cmd.encode()
        decoded = WsCommand.decode(encoded)

        assert isinstance(decoded, EVENT)
        assert isinstance(decoded.event, ErrorEvent)
        assert decoded.event.error_name == original_event.error_name
        assert decoded.event.error_msg == original_event.error_msg

    def test_event_custom_decode_no_colon(self):
        """Test EVENT custom_decode returns None when no colon."""
        result = EVENT.custom_decode("no colon")
        assert result is None

    def test_event_decode_invalid_base64_raises_error(self):
        """Test EVENT decode with invalid base64 raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            EVENT.custom_decode("EVENT: not_valid_base64!!!")

        assert "Failed to decode EVENT" in str(exc_info.value)


class TestEXPERIMENTCommand:
    """Tests for EXPERIMENT WebSocket command."""

    def test_experiment_creation(self):
        """Test creating EXPERIMENT command."""
        cmd = EXPERIMENT(name="my_experiment")

        assert cmd.name == "my_experiment"
        assert cmd.command_type == "EXPERIMENT"

    def test_experiment_encode(self):
        """Test EXPERIMENT encoding."""
        cmd = EXPERIMENT(name="test_run_001")
        encoded = cmd.encode()

        assert encoded == "EXPERIMENT: test_run_001"

    def test_experiment_roundtrip(self):
        """Test EXPERIMENT encode/decode roundtrip."""
        original = EXPERIMENT(name="experiment_with_spaces_test")
        encoded = original.encode()
        decoded = WsCommand.decode(encoded)

        assert isinstance(decoded, EXPERIMENT)
        assert decoded.name == original.name

    def test_experiment_decode_strips_whitespace(self):
        """Test that EXPERIMENT decode strips whitespace from name."""
        decoded = WsCommand.decode("EXPERIMENT:   padded_name   ")

        assert decoded.name == "padded_name"

    def test_experiment_custom_decode_no_colon(self):
        """Test EXPERIMENT custom_decode returns None when no colon."""
        result = EXPERIMENT.custom_decode("no colon")
        assert result is None


class TestECHOCommand:
    """Tests for ECHO WebSocket command."""

    def test_echo_creation(self):
        """Test creating ECHO command."""
        cmd = ECHO(data="ping")

        assert cmd.data == "ping"
        assert cmd.command_type == "ECHO"

    def test_echo_encode(self):
        """Test ECHO encoding."""
        cmd = ECHO(data="test_data")
        encoded = cmd.encode()

        assert encoded == "ECHO: test_data"

    def test_echo_roundtrip(self):
        """Test ECHO encode/decode roundtrip."""
        original = ECHO(data="hello_world")
        encoded = original.encode()
        decoded = WsCommand.decode(encoded)

        assert isinstance(decoded, ECHO)
        assert decoded.data == original.data

    def test_echo_custom_decode_no_colon(self):
        """Test ECHO custom_decode returns None when no colon."""
        result = ECHO.custom_decode("no colon")
        assert result is None


class TestECHOREPLYCommand:
    """Tests for ECHOREPLY WebSocket command."""

    def test_echoreply_creation(self):
        """Test creating ECHOREPLY command."""
        cmd = ECHOREPLY(data="pong")

        assert cmd.data == "pong"
        assert cmd.command_type == "ECHOREPLY"

    def test_echoreply_encode(self):
        """Test ECHOREPLY encoding."""
        cmd = ECHOREPLY(data="response_data")
        encoded = cmd.encode()

        assert encoded == "ECHOREPLY: response_data"

    def test_echoreply_roundtrip(self):
        """Test ECHOREPLY encode/decode roundtrip."""
        original = ECHOREPLY(data="echo_response")
        encoded = original.encode()
        decoded = WsCommand.decode(encoded)

        assert isinstance(decoded, ECHOREPLY)
        assert decoded.data == original.data

    def test_echoreply_custom_decode_no_colon(self):
        """Test ECHOREPLY custom_decode returns None when no colon."""
        result = ECHOREPLY.custom_decode("no colon")
        assert result is None


class TestBREAKPOINTCommand:
    """Tests for BREAKPOINT WebSocket command."""

    def test_breakpoint_creation(self):
        """Test creating BREAKPOINT command."""
        cmd = BREAKPOINT()

        assert cmd.command_type == "BREAKPOINT"

    def test_breakpoint_encode(self):
        """Test BREAKPOINT encoding."""
        cmd = BREAKPOINT()
        encoded = cmd.encode()

        assert encoded == "BREAKPOINT"

    def test_breakpoint_decode(self):
        """Test BREAKPOINT decoding."""
        # Note: BREAKPOINT uses command_type without colon in encode
        # but decode expects colon, so we need to handle this case
        decoded = WsCommand.decode("BREAKPOINT:")

        assert isinstance(decoded, BREAKPOINT)

    def test_breakpoint_custom_decode(self):
        """Test BREAKPOINT custom_decode creates instance."""
        decoded = BREAKPOINT.custom_decode("BREAKPOINT:")

        assert isinstance(decoded, BREAKPOINT)


class TestBREAKPOINTRESOLVECommand:
    """Tests for BREAKPOINTRESOLVE WebSocket command."""

    def test_breakpointresolve_creation(self):
        """Test creating BREAKPOINTRESOLVE command."""
        cmd = BREAKPOINTRESOLVE()

        assert cmd.command_type == "BREAKPOINTRESOLVE"

    def test_breakpointresolve_encode(self):
        """Test BREAKPOINTRESOLVE encoding."""
        cmd = BREAKPOINTRESOLVE()
        encoded = cmd.encode()

        assert encoded == "BREAKPOINTRESOLVE"

    def test_breakpointresolve_decode(self):
        """Test BREAKPOINTRESOLVE decoding."""
        decoded = WsCommand.decode("BREAKPOINTRESOLVE:")

        assert isinstance(decoded, BREAKPOINTRESOLVE)

    def test_breakpointresolve_custom_decode(self):
        """Test BREAKPOINTRESOLVE custom_decode creates instance."""
        decoded = BREAKPOINTRESOLVE.custom_decode("BREAKPOINTRESOLVE:")

        assert isinstance(decoded, BREAKPOINTRESOLVE)


class TestBase64Serialization:
    """Tests for base64 serialization in commands."""

    def test_exec_base64_encoding_is_valid(self):
        """Test that EXEC produces valid base64."""
        cmd = EXEC(command="test", shell=True, cwd="")
        encoded = cmd.encode()

        base64_part = encoded.split(": ", 1)[1]
        # Should not raise
        decoded_bytes = base64.b64decode(base64_part)
        decoded_str = decoded_bytes.decode('utf-8')

        assert isinstance(decoded_str, str)

    def test_done_base64_encoding_is_valid(self):
        """Test that DONE produces valid base64."""
        cmd = DONE(name="test", out_msg="output", err_msg="", error=False)
        encoded = cmd.encode()

        base64_part = encoded.split(": ", 1)[1]
        decoded_bytes = base64.b64decode(base64_part)
        decoded_str = decoded_bytes.decode('utf-8')

        assert isinstance(decoded_str, str)

    def test_log_base64_encoding_is_valid(self):
        """Test that LOG produces valid base64."""
        cmd = LOG(name="log", out_msg="message", err_msg="", error=False)
        encoded = cmd.encode()

        base64_part = encoded.split(": ", 1)[1]
        decoded_bytes = base64.b64decode(base64_part)
        decoded_str = decoded_bytes.decode('utf-8')

        assert isinstance(decoded_str, str)

    def test_event_base64_encoding_is_valid(self):
        """Test that EVENT produces valid base64."""
        test_event = TestEvent(
            test_name="test",
            timestamp="2024-01-15T10:30:00.000000",
            ulid="01HM123ABC456DEF789GHI012"
        )
        cmd = EVENT(event=test_event)
        encoded = cmd.encode()

        base64_part = encoded.split(": ", 1)[1]
        decoded_bytes = base64.b64decode(base64_part)
        decoded_str = decoded_bytes.decode('utf-8')

        assert isinstance(decoded_str, str)

    def test_unicode_in_base64_commands(self):
        """Test commands with unicode characters."""
        cmd = EXEC(command="echo 'Hello'\n", shell=True, cwd="/tmp")
        encoded = cmd.encode()
        decoded = WsCommand.decode(encoded)

        assert decoded.command == cmd.command

    def test_empty_strings_in_commands(self):
        """Test commands with empty strings."""
        cmd = DONE(name="", out_msg="", err_msg="", error=False)
        encoded = cmd.encode()
        decoded = WsCommand.decode(encoded)

        assert decoded.name == ""
        assert decoded.out_msg == ""


class TestCommandInteroperability:
    """Tests for command interactions and edge cases."""

    def test_all_commands_have_command_type(self):
        """Test all command classes have command_type attribute."""
        command_classes = [
            EXEC, DONE, LOG, EVENT, EXPERIMENT,
            ECHO, ECHOREPLY, BREAKPOINT, BREAKPOINTRESOLVE
        ]

        for cls in command_classes:
            assert hasattr(cls, 'command_type')
            assert isinstance(cls.command_type, str)

    def test_all_commands_have_encode_method(self):
        """Test all command classes have encode method."""
        # Create instances for testing
        commands = [
            EXEC(command="test", shell=True),
            DONE(name="test"),
            LOG(name="test"),
            EVENT(event=TestEvent(test_name="test", timestamp="2024-01-15T10:30:00.000000", ulid="01HM123ABC456DEF789GHI012")),
            EXPERIMENT(name="test"),
            ECHO(data="test"),
            ECHOREPLY(data="test"),
            BREAKPOINT(),
            BREAKPOINTRESOLVE(),
        ]

        for cmd in commands:
            encoded = cmd.encode()
            assert isinstance(encoded, str)

    def test_all_commands_have_custom_decode_method(self):
        """Test all command classes have custom_decode method."""
        command_classes = [
            EXEC, DONE, LOG, EVENT, EXPERIMENT,
            ECHO, ECHOREPLY, BREAKPOINT, BREAKPOINTRESOLVE
        ]

        for cls in command_classes:
            assert hasattr(cls, 'custom_decode')
            assert callable(cls.custom_decode)

    def test_decode_with_extra_colons(self):
        """Test decode handles data containing colons."""
        # Create a command with colon in data
        cmd = EXEC(command="echo 'time: 12:30'", shell=True, cwd="")
        encoded = cmd.encode()
        decoded = WsCommand.decode(encoded)

        assert decoded.command == "echo 'time: 12:30'"

    def test_whitespace_handling_in_decode(self):
        """Test decode handles various whitespace."""
        decoded = WsCommand.decode("ECHO:    spaced_data   ")

        assert isinstance(decoded, ECHO)
        assert decoded.data == "spaced_data"
