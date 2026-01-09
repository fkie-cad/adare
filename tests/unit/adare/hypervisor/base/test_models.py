"""
Unit tests for adare.hypervisor.base.models.

Tests the hypervisor-agnostic data models: PortForwardingRule, SharedFolderConfig, and CommandResult.
"""
import pytest

from adare.hypervisor.base.models import (
    CommandResult,
    PortForwardingRule,
    SharedFolderConfig,
)


class TestPortForwardingRule:
    """Tests for PortForwardingRule dataclass."""

    def test_creation_with_all_fields(self):
        """Test creating a rule with all fields specified."""
        rule = PortForwardingRule(
            name="ssh",
            protocol="tcp",
            host_ip="127.0.0.1",
            host_port=2222,
            guest_ip="10.0.2.15",
            guest_port=22,
        )
        assert rule.name == "ssh"
        assert rule.protocol == "tcp"
        assert rule.host_ip == "127.0.0.1"
        assert rule.host_port == 2222
        assert rule.guest_ip == "10.0.2.15"
        assert rule.guest_port == 22

    def test_creation_with_required_fields_only(self):
        """Test creating a rule with only required fields, using defaults for others."""
        rule = PortForwardingRule(name="http", protocol="tcp")
        assert rule.name == "http"
        assert rule.protocol == "tcp"
        assert rule.host_ip == ""
        assert rule.host_port == 0
        assert rule.guest_ip == ""
        assert rule.guest_port == 0

    def test_default_values(self):
        """Test that default values are correctly applied."""
        rule = PortForwardingRule(name="test", protocol="udp")
        assert rule.host_ip == ""
        assert rule.host_port == 0
        assert rule.guest_ip == ""
        assert rule.guest_port == 0

    def test_equality_identical_rules(self):
        """Test equality between two identical rules."""
        rule1 = PortForwardingRule(
            name="ssh",
            protocol="tcp",
            host_ip="127.0.0.1",
            host_port=2222,
            guest_ip="10.0.2.15",
            guest_port=22,
        )
        rule2 = PortForwardingRule(
            name="ssh",
            protocol="tcp",
            host_ip="127.0.0.1",
            host_port=2222,
            guest_ip="10.0.2.15",
            guest_port=22,
        )
        assert rule1 == rule2

    def test_equality_different_rules(self):
        """Test inequality between different rules."""
        rule1 = PortForwardingRule(name="ssh", protocol="tcp", host_port=2222)
        rule2 = PortForwardingRule(name="ssh", protocol="tcp", host_port=3333)
        assert rule1 != rule2

    @pytest.mark.parametrize(
        "rule1_params,rule2_params,expected_match",
        [
            # Identical rules should match
            (
                {"name": "ssh", "protocol": "tcp", "host_ip": "127.0.0.1", "host_port": 2222, "guest_ip": "10.0.2.15", "guest_port": 22},
                {"name": "ssh", "protocol": "tcp", "host_ip": "127.0.0.1", "host_port": 2222, "guest_ip": "10.0.2.15", "guest_port": 22},
                True,
            ),
            # Different names but same ports should match (matches() ignores name)
            (
                {"name": "ssh-rule", "protocol": "tcp", "host_ip": "127.0.0.1", "host_port": 2222, "guest_ip": "10.0.2.15", "guest_port": 22},
                {"name": "other-name", "protocol": "tcp", "host_ip": "127.0.0.1", "host_port": 2222, "guest_ip": "10.0.2.15", "guest_port": 22},
                True,
            ),
            # Different protocol should not match
            (
                {"name": "dns", "protocol": "tcp", "host_port": 53},
                {"name": "dns", "protocol": "udp", "host_port": 53},
                False,
            ),
            # Different host_ip should not match
            (
                {"name": "ssh", "protocol": "tcp", "host_ip": "127.0.0.1", "host_port": 2222},
                {"name": "ssh", "protocol": "tcp", "host_ip": "0.0.0.0", "host_port": 2222},
                False,
            ),
            # Different host_port should not match
            (
                {"name": "ssh", "protocol": "tcp", "host_port": 2222},
                {"name": "ssh", "protocol": "tcp", "host_port": 3333},
                False,
            ),
            # Different guest_ip should not match
            (
                {"name": "ssh", "protocol": "tcp", "guest_ip": "10.0.2.15", "guest_port": 22},
                {"name": "ssh", "protocol": "tcp", "guest_ip": "10.0.2.16", "guest_port": 22},
                False,
            ),
            # Different guest_port should not match
            (
                {"name": "ssh", "protocol": "tcp", "guest_port": 22},
                {"name": "ssh", "protocol": "tcp", "guest_port": 23},
                False,
            ),
            # Rules with defaults should match
            (
                {"name": "test", "protocol": "tcp"},
                {"name": "other", "protocol": "tcp"},
                True,
            ),
        ],
    )
    def test_matches_parametrized(self, rule1_params, rule2_params, expected_match):
        """Parametrized test for matches() method with various scenarios."""
        rule1 = PortForwardingRule(**rule1_params)
        rule2 = PortForwardingRule(**rule2_params)
        assert rule1.matches(rule2) == expected_match

    def test_matches_is_symmetric(self):
        """Test that matches() is symmetric (a.matches(b) == b.matches(a))."""
        rule1 = PortForwardingRule(name="a", protocol="tcp", host_port=8080)
        rule2 = PortForwardingRule(name="b", protocol="tcp", host_port=8080)
        assert rule1.matches(rule2) == rule2.matches(rule1)


class TestSharedFolderConfig:
    """Tests for SharedFolderConfig dataclass."""

    def test_creation_with_all_fields(self):
        """Test creating a config with all fields specified."""
        config = SharedFolderConfig(
            name="shared",
            host_path="/home/user/shared",
            readonly=True,
        )
        assert config.name == "shared"
        assert config.host_path == "/home/user/shared"
        assert config.readonly is True

    def test_creation_with_required_fields_only(self):
        """Test creating a config with only required fields."""
        config = SharedFolderConfig(name="data", host_path="/data")
        assert config.name == "data"
        assert config.host_path == "/data"
        assert config.readonly is False

    def test_default_readonly_is_false(self):
        """Test that readonly defaults to False."""
        config = SharedFolderConfig(name="test", host_path="/test")
        assert config.readonly is False

    def test_readonly_true(self):
        """Test explicitly setting readonly to True."""
        config = SharedFolderConfig(name="docs", host_path="/docs", readonly=True)
        assert config.readonly is True

    def test_readonly_false_explicit(self):
        """Test explicitly setting readonly to False."""
        config = SharedFolderConfig(name="scratch", host_path="/scratch", readonly=False)
        assert config.readonly is False

    def test_equality_identical_configs(self):
        """Test equality between identical configs."""
        config1 = SharedFolderConfig(name="shared", host_path="/shared", readonly=True)
        config2 = SharedFolderConfig(name="shared", host_path="/shared", readonly=True)
        assert config1 == config2

    def test_equality_different_configs(self):
        """Test inequality between different configs."""
        config1 = SharedFolderConfig(name="shared", host_path="/shared1")
        config2 = SharedFolderConfig(name="shared", host_path="/shared2")
        assert config1 != config2

    @pytest.mark.parametrize(
        "config1_params,config2_params,expected_match",
        [
            # Identical configs should match
            (
                {"name": "shared", "host_path": "/shared", "readonly": False},
                {"name": "shared", "host_path": "/shared", "readonly": False},
                True,
            ),
            # Different names should not match
            (
                {"name": "folder1", "host_path": "/shared"},
                {"name": "folder2", "host_path": "/shared"},
                False,
            ),
            # Different host_path should not match
            (
                {"name": "shared", "host_path": "/path1"},
                {"name": "shared", "host_path": "/path2"},
                False,
            ),
            # Different readonly flag should not match
            (
                {"name": "shared", "host_path": "/shared", "readonly": True},
                {"name": "shared", "host_path": "/shared", "readonly": False},
                False,
            ),
            # Both readonly=True should match
            (
                {"name": "docs", "host_path": "/docs", "readonly": True},
                {"name": "docs", "host_path": "/docs", "readonly": True},
                True,
            ),
            # Both readonly=False (default) should match
            (
                {"name": "data", "host_path": "/data"},
                {"name": "data", "host_path": "/data", "readonly": False},
                True,
            ),
        ],
    )
    def test_matches_parametrized(self, config1_params, config2_params, expected_match):
        """Parametrized test for matches() method with various scenarios."""
        config1 = SharedFolderConfig(**config1_params)
        config2 = SharedFolderConfig(**config2_params)
        assert config1.matches(config2) == expected_match

    def test_matches_is_symmetric(self):
        """Test that matches() is symmetric."""
        config1 = SharedFolderConfig(name="a", host_path="/a", readonly=True)
        config2 = SharedFolderConfig(name="a", host_path="/a", readonly=True)
        assert config1.matches(config2) == config2.matches(config1)


class TestCommandResult:
    """Tests for CommandResult dataclass."""

    def test_creation_with_all_fields(self):
        """Test creating a result with all fields specified."""
        result = CommandResult(
            returncode=0,
            stdout="Hello World",
            stderr="",
            duration=5,
        )
        assert result.returncode == 0
        assert result.stdout == "Hello World"
        assert result.stderr == ""
        assert result.duration == 5

    def test_creation_with_required_fields_only(self):
        """Test creating a result with only required fields."""
        result = CommandResult(returncode=1, stdout="output", stderr="error")
        assert result.returncode == 1
        assert result.stdout == "output"
        assert result.stderr == "error"
        assert result.duration is None

    def test_default_duration_is_none(self):
        """Test that duration defaults to None."""
        result = CommandResult(returncode=0, stdout="", stderr="")
        assert result.duration is None

    def test_successful_command(self):
        """Test representing a successful command execution."""
        result = CommandResult(
            returncode=0,
            stdout="success output",
            stderr="",
            duration=10,
        )
        assert result.returncode == 0
        assert result.stdout == "success output"
        assert result.stderr == ""
        assert result.duration == 10

    def test_failed_command(self):
        """Test representing a failed command execution."""
        result = CommandResult(
            returncode=1,
            stdout="",
            stderr="Error: command failed",
            duration=2,
        )
        assert result.returncode == 1
        assert result.stdout == ""
        assert result.stderr == "Error: command failed"
        assert result.duration == 2

    def test_command_with_both_stdout_and_stderr(self):
        """Test command that produces both stdout and stderr."""
        result = CommandResult(
            returncode=0,
            stdout="Normal output",
            stderr="Warning: something minor",
            duration=3,
        )
        assert result.returncode == 0
        assert result.stdout == "Normal output"
        assert result.stderr == "Warning: something minor"
        assert result.duration == 3

    def test_multiline_output(self):
        """Test command with multiline output."""
        stdout = "line1\nline2\nline3"
        stderr = "warning1\nwarning2"
        result = CommandResult(
            returncode=0,
            stdout=stdout,
            stderr=stderr,
        )
        assert result.stdout == stdout
        assert result.stderr == stderr
        assert "line2" in result.stdout
        assert "warning1" in result.stderr

    def test_empty_output(self):
        """Test command with empty output strings."""
        result = CommandResult(returncode=0, stdout="", stderr="")
        assert result.stdout == ""
        assert result.stderr == ""

    def test_negative_returncode(self):
        """Test command with negative returncode (e.g., killed by signal)."""
        result = CommandResult(returncode=-9, stdout="", stderr="Killed")
        assert result.returncode == -9
        assert result.stderr == "Killed"

    def test_equality_identical_results(self):
        """Test equality between identical results."""
        result1 = CommandResult(returncode=0, stdout="out", stderr="err", duration=5)
        result2 = CommandResult(returncode=0, stdout="out", stderr="err", duration=5)
        assert result1 == result2

    def test_equality_different_results(self):
        """Test inequality between different results."""
        result1 = CommandResult(returncode=0, stdout="out1", stderr="")
        result2 = CommandResult(returncode=0, stdout="out2", stderr="")
        assert result1 != result2

    def test_duration_zero(self):
        """Test command with zero duration (instant execution)."""
        result = CommandResult(returncode=0, stdout="", stderr="", duration=0)
        assert result.duration == 0
        assert result.duration is not None

    def test_all_fields_accessible(self):
        """Test that all fields are accessible as attributes."""
        result = CommandResult(
            returncode=42,
            stdout="standard output",
            stderr="standard error",
            duration=100,
        )
        # Verify all fields can be accessed
        _ = result.returncode
        _ = result.stdout
        _ = result.stderr
        _ = result.duration
        # Verify values
        assert result.returncode == 42
        assert result.stdout == "standard output"
        assert result.stderr == "standard error"
        assert result.duration == 100
