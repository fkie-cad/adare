
import pytest

from adare.types.playbook import CommandAction


class TestCommandAction:

    def test_raw_string_parsing_r_double_quote(self):
        """Test parsing of r"..." raw string format."""
        # The input value simulates what the YAML loader might pass if it parses 'command: r"..."' as a string
        # BUT wait, YAML loader usually handles quotes.
        # If the user writes:
        # command: r"something"
        # The YAML loader parses this as the string 'r"something"'.

        action = CommandAction(command='r"C:\\Windows\\System32"')
        assert action.command == 'C:\\Windows\\System32'

    def test_raw_string_parsing_r_single_quote(self):
        """Test parsing of r'...' raw string format."""
        action = CommandAction(command="r'C:\\Windows\\System32'")
        assert action.command == 'C:\\Windows\\System32'

    def test_normal_string_unchanged(self):
        """Test that normal strings are untouched."""
        action = CommandAction(command='"normal string"')
        # It should NOT strip normal quotes unless we decide to do so, but standard YAML does that.
        # But if the string passed to __init__ has quotes, it means they were part of the string.
        # However, the goal is ONLY to support the specific r"..." syntax which YAML doesn't support natively.
        assert action.command == '"normal string"'

    def test_no_quotes_unchanged(self):
        action = CommandAction(command='echo hello')
        assert action.command == 'echo hello'

    def test_mismatched_quotes_unchanged(self):
        """Test that mismatched quotes are not stripped."""
        action = CommandAction(command='r"mismatched\'')
        assert action.command == 'r"mismatched\''

    def test_nested_quotes_handling(self):
        """Test handling of nested quotes inside raw strings."""
        # Input: r"nested 'quotes'"
        action = CommandAction(command='r"nested \'quotes\'"')
        assert action.command == "nested 'quotes'"

    def test_valid_list_raises_error(self):
        """Test that list input still raises validation error (existing behavior check)."""
        with pytest.raises(ValueError, match="CommandAction.command must be a string"):
            CommandAction(command=["ls", "-la"])

    def test_powershell_variable_no_auto_wrap_in_action(self):
        """Test that command starting with $ is NOT wrapped in CommandAction (wrapping handled in Executor)."""
        # Input: $x = 1
        cmd_str = "$x = 1"
        action = CommandAction(command=cmd_str)
        # Should NOT be wrapped yet
        assert action.command == cmd_str
        assert not action.command.startswith("powershell")

    def test_powershell_subexpression_no_auto_wrap_in_action(self):
        """Test that command starting with ( is NOT wrapped in CommandAction."""
        cmd_str = "(New-Object -ComObject WScript.Shell).CreateShortcut('...')"
        action = CommandAction(command=cmd_str)
        assert action.command == cmd_str

    def test_powershell_with_whitespace_no_auto_wrap_in_action(self):
        """Test that leading whitespace doesn't trigger wrap in CommandAction."""
        cmd_str = "  $x = 1"
        action = CommandAction(command=cmd_str)
        assert action.command == cmd_str

    def test_powershell_explicit_command_no_wrap(self):
        """Test that command already invoking powershell is NOT wrapped."""
        cmd_str = "powershell -Command '$x=1'"
        action = CommandAction(command=cmd_str)
        assert action.command == cmd_str
        assert not action.command.startswith("powershell -EncodedCommand ")

    def test_r_string_powershell_combo_strip_only(self):
        """Test that r-string STRIPPING happens but NO wrapping in CommandAction."""
        # Input in YAML: command: r"$x = 1"
        action = CommandAction(command='r"$x = 1"')
        # Should strip r"" but NOT wrap
        assert action.command == "$x = 1"

