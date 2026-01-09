"""
Unit tests for VirtualBox-specific models.

Tests PortForwardingRule with VirtualBox format conversion.
"""
import pytest

from adare.hypervisor.virtualbox.models import PortForwardingRule


class TestPortForwardingRuleToVboxFormat:
    """Tests for PortForwardingRule.to_vbox_format() method."""

    def test_to_vbox_format_basic(self):
        """Test basic conversion to VirtualBox format."""
        rule = PortForwardingRule(
            name="ssh",
            protocol="tcp",
            host_ip="127.0.0.1",
            host_port=2222,
            guest_ip="10.0.2.15",
            guest_port=22
        )
        result = rule.to_vbox_format()
        assert result == "ssh,tcp,127.0.0.1,2222,10.0.2.15,22"

    def test_to_vbox_format_empty_host_ip(self):
        """Test conversion with empty host_ip."""
        rule = PortForwardingRule(
            name="http",
            protocol="tcp",
            host_ip="",
            host_port=8080,
            guest_ip="10.0.2.15",
            guest_port=80
        )
        result = rule.to_vbox_format()
        assert result == "http,tcp,,8080,10.0.2.15,80"

    def test_to_vbox_format_empty_guest_ip(self):
        """Test conversion with empty guest_ip."""
        rule = PortForwardingRule(
            name="https",
            protocol="tcp",
            host_ip="127.0.0.1",
            host_port=8443,
            guest_ip="",
            guest_port=443
        )
        result = rule.to_vbox_format()
        assert result == "https,tcp,127.0.0.1,8443,,443"

    def test_to_vbox_format_both_ips_empty(self):
        """Test conversion with both host_ip and guest_ip empty."""
        rule = PortForwardingRule(
            name="dns",
            protocol="udp",
            host_ip="",
            host_port=5353,
            guest_ip="",
            guest_port=53
        )
        result = rule.to_vbox_format()
        assert result == "dns,udp,,5353,,53"

    def test_to_vbox_format_udp_protocol(self):
        """Test conversion with UDP protocol."""
        rule = PortForwardingRule(
            name="ntp",
            protocol="udp",
            host_ip="0.0.0.0",
            host_port=123,
            guest_ip="10.0.2.15",
            guest_port=123
        )
        result = rule.to_vbox_format()
        assert result == "ntp,udp,0.0.0.0,123,10.0.2.15,123"


class TestPortForwardingRuleFromVboxFormat:
    """Tests for PortForwardingRule.from_vbox_format() method."""

    def test_from_vbox_format_basic(self):
        """Test basic parsing from VirtualBox format."""
        result = PortForwardingRule.from_vbox_format("ssh,tcp,127.0.0.1,2222,10.0.2.15,22")
        assert result.name == "ssh"
        assert result.protocol == "tcp"
        assert result.host_ip == "127.0.0.1"
        assert result.host_port == 2222
        assert result.guest_ip == "10.0.2.15"
        assert result.guest_port == 22

    def test_from_vbox_format_empty_host_ip(self):
        """Test parsing with empty host_ip."""
        result = PortForwardingRule.from_vbox_format("http,tcp,,8080,10.0.2.15,80")
        assert result.name == "http"
        assert result.protocol == "tcp"
        assert result.host_ip == ""
        assert result.host_port == 8080
        assert result.guest_ip == "10.0.2.15"
        assert result.guest_port == 80

    def test_from_vbox_format_empty_guest_ip(self):
        """Test parsing with empty guest_ip."""
        result = PortForwardingRule.from_vbox_format("https,tcp,127.0.0.1,8443,,443")
        assert result.name == "https"
        assert result.protocol == "tcp"
        assert result.host_ip == "127.0.0.1"
        assert result.host_port == 8443
        assert result.guest_ip == ""
        assert result.guest_port == 443

    def test_from_vbox_format_both_ips_empty(self):
        """Test parsing with both IPs empty."""
        result = PortForwardingRule.from_vbox_format("dns,udp,,5353,,53")
        assert result.name == "dns"
        assert result.protocol == "udp"
        assert result.host_ip == ""
        assert result.host_port == 5353
        assert result.guest_ip == ""
        assert result.guest_port == 53

    def test_from_vbox_format_udp_protocol(self):
        """Test parsing UDP protocol."""
        result = PortForwardingRule.from_vbox_format("ntp,udp,0.0.0.0,123,10.0.2.15,123")
        assert result.protocol == "udp"


class TestPortForwardingRuleFromVboxFormatInvalid:
    """Tests for invalid input handling in from_vbox_format()."""

    @pytest.mark.parametrize("invalid_input,description", [
        ("ssh,tcp,127.0.0.1,2222,10.0.2.15", "missing guest_port (5 fields)"),
        ("ssh,tcp,127.0.0.1,2222", "missing guest_ip and guest_port (4 fields)"),
        ("ssh,tcp,127.0.0.1", "only 3 fields"),
        ("ssh,tcp", "only 2 fields"),
        ("ssh", "only 1 field"),
        ("", "empty string"),
        ("ssh,tcp,127.0.0.1,2222,10.0.2.15,22,extra", "too many fields (7 fields)"),
    ])
    def test_from_vbox_format_wrong_field_count(self, invalid_input, description):
        """Test that wrong number of fields raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            PortForwardingRule.from_vbox_format(invalid_input)
        assert "Invalid VirtualBox port forwarding format" in str(exc_info.value)

    def test_from_vbox_format_non_numeric_port_uses_zero(self):
        """Test that non-numeric port values result in 0 (current behavior)."""
        # The current implementation uses isdigit() check and defaults to 0
        result = PortForwardingRule.from_vbox_format("ssh,tcp,127.0.0.1,abc,10.0.2.15,xyz")
        assert result.host_port == 0
        assert result.guest_port == 0


class TestPortForwardingRuleRoundtrip:
    """Tests for roundtrip conversion (to_vbox_format -> from_vbox_format)."""

    @pytest.mark.parametrize("name,protocol,host_ip,host_port,guest_ip,guest_port", [
        ("ssh", "tcp", "127.0.0.1", 2222, "10.0.2.15", 22),
        ("http", "tcp", "", 8080, "10.0.2.15", 80),
        ("https", "tcp", "127.0.0.1", 8443, "", 443),
        ("dns", "udp", "", 5353, "", 53),
        ("custom", "tcp", "0.0.0.0", 9000, "192.168.1.100", 9000),
        ("agent", "tcp", "", 8765, "", 8765),
    ])
    def test_roundtrip_gives_equivalent_object(
        self, name, protocol, host_ip, host_port, guest_ip, guest_port
    ):
        """Test that to_vbox_format then from_vbox_format produces equivalent rule."""
        original = PortForwardingRule(
            name=name,
            protocol=protocol,
            host_ip=host_ip,
            host_port=host_port,
            guest_ip=guest_ip,
            guest_port=guest_port
        )
        vbox_string = original.to_vbox_format()
        restored = PortForwardingRule.from_vbox_format(vbox_string)

        assert restored.name == original.name
        assert restored.protocol == original.protocol
        assert restored.host_ip == original.host_ip
        assert restored.host_port == original.host_port
        assert restored.guest_ip == original.guest_ip
        assert restored.guest_port == original.guest_port

    @pytest.mark.parametrize("vbox_string", [
        "ssh,tcp,127.0.0.1,2222,10.0.2.15,22",
        "http,tcp,,8080,10.0.2.15,80",
        "https,tcp,127.0.0.1,8443,,443",
        "dns,udp,,5353,,53",
        "agent,tcp,0.0.0.0,8765,10.0.2.15,8765",
    ])
    def test_roundtrip_from_string_preserves_format(self, vbox_string):
        """Test that from_vbox_format then to_vbox_format preserves the string."""
        rule = PortForwardingRule.from_vbox_format(vbox_string)
        result = rule.to_vbox_format()
        assert result == vbox_string


class TestPortForwardingRuleEdgeCases:
    """Tests for edge cases in PortForwardingRule format conversion."""

    def test_special_characters_in_name(self):
        """Test rule name with special characters."""
        rule = PortForwardingRule(
            name="my-rule_123",
            protocol="tcp",
            host_ip="",
            host_port=8080,
            guest_ip="",
            guest_port=80
        )
        vbox_string = rule.to_vbox_format()
        restored = PortForwardingRule.from_vbox_format(vbox_string)
        assert restored.name == "my-rule_123"

    def test_ipv4_addresses_various_formats(self):
        """Test various IPv4 address formats."""
        rule = PortForwardingRule(
            name="test",
            protocol="tcp",
            host_ip="192.168.100.200",
            host_port=1234,
            guest_ip="10.255.255.255",
            guest_port=5678
        )
        vbox_string = rule.to_vbox_format()
        restored = PortForwardingRule.from_vbox_format(vbox_string)
        assert restored.host_ip == "192.168.100.200"
        assert restored.guest_ip == "10.255.255.255"

    def test_high_port_numbers(self):
        """Test high port numbers (max valid port is 65535)."""
        rule = PortForwardingRule(
            name="highport",
            protocol="tcp",
            host_ip="",
            host_port=65535,
            guest_ip="",
            guest_port=65534
        )
        vbox_string = rule.to_vbox_format()
        restored = PortForwardingRule.from_vbox_format(vbox_string)
        assert restored.host_port == 65535
        assert restored.guest_port == 65534

    def test_zero_port_numbers(self):
        """Test zero port numbers."""
        rule = PortForwardingRule(
            name="zeroport",
            protocol="tcp",
            host_ip="",
            host_port=0,
            guest_ip="",
            guest_port=0
        )
        vbox_string = rule.to_vbox_format()
        restored = PortForwardingRule.from_vbox_format(vbox_string)
        assert restored.host_port == 0
        assert restored.guest_port == 0

    def test_whitespace_in_ip_preserved(self):
        """Test that whitespace in IP fields is preserved (not trimmed)."""
        # This tests current behavior - whitespace is preserved
        result = PortForwardingRule.from_vbox_format("test,tcp, 127.0.0.1 ,8080, 10.0.2.15 ,80")
        assert result.host_ip == " 127.0.0.1 "
        assert result.guest_ip == " 10.0.2.15 "
