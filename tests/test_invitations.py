"""Unit tests for nordvpn.py invitation management: _parse_invitations, list_invitations, send_invitation, revoke_invitation, accept_invitation, deny_invitation."""

from unittest.mock import patch

import pytest

import nordvpn


# ---------------------------------------------------------------------------
# _parse_invitations
# ---------------------------------------------------------------------------

class TestParseInvitations:
    def test_empty_output(self):
        result = nordvpn._parse_invitations("")
        assert result == {"sent": [], "received": []}

    def test_sent_invitations(self):
        raw = """\
Sent Invitations:
user1@example.com
user2@example.com
"""
        result = nordvpn._parse_invitations(raw)
        assert result["sent"] == ["user1@example.com", "user2@example.com"]
        assert result["received"] == []

    def test_received_invitations(self):
        raw = """\
Received Invitations:
sender@example.com
"""
        result = nordvpn._parse_invitations(raw)
        assert result["sent"] == []
        assert result["received"] == ["sender@example.com"]

    def test_both_sections(self):
        raw = """\
Sent Invitations:
outgoing@example.com

Received Invitations:
incoming@example.com
"""
        result = nordvpn._parse_invitations(raw)
        assert "outgoing@example.com" in result["sent"]
        assert "incoming@example.com" in result["received"]

    def test_separator_lines_ignored(self):
        raw = """\
Sent Invitations:
--------------
user@example.com
--------------
"""
        result = nordvpn._parse_invitations(raw)
        assert result["sent"] == ["user@example.com"]


# ---------------------------------------------------------------------------
# list_invitations
# ---------------------------------------------------------------------------

class TestListInvitations:
    def test_returns_empty_on_error(self):
        with patch("nordvpn._run", return_value=(1, "", "error")):
            result = nordvpn.list_invitations()
        assert result == {"sent": [], "received": []}


# ---------------------------------------------------------------------------
# send_invitation
# ---------------------------------------------------------------------------

class TestSendInvitation:
    def test_success(self):
        with patch("nordvpn._run", return_value=(0, "", "")):
            ok, msg = nordvpn.send_invitation("user@example.com")
        assert ok is True
        assert "user@example.com" in msg

    def test_email_is_last_argument(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.send_invitation("user@example.com", permissions={"incoming": True})
        cmd = mock_run.call_args[0][0]
        assert cmd[-1] == "user@example.com"

    def test_incoming_permission(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.send_invitation("user@example.com", permissions={"incoming": True})
        cmd = mock_run.call_args[0][0]
        assert "--allow-incoming-traffic" in cmd
        assert "--allow-traffic-routing" not in cmd

    def test_routing_permission(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.send_invitation("user@example.com", permissions={"routing": True})
        cmd = mock_run.call_args[0][0]
        assert "--allow-traffic-routing" in cmd

    def test_local_permission(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.send_invitation("user@example.com", permissions={"local": True})
        cmd = mock_run.call_args[0][0]
        assert "--allow-local-network" in cmd

    def test_fileshare_permission(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.send_invitation("user@example.com", permissions={"fileshare": True})
        cmd = mock_run.call_args[0][0]
        assert "--allow-peer-send-files" in cmd

    def test_all_permissions(self):
        perms = {"incoming": True, "routing": True, "local": True, "fileshare": True}
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.send_invitation("user@example.com", permissions=perms)
        cmd = mock_run.call_args[0][0]
        assert "--allow-incoming-traffic" in cmd
        assert "--allow-traffic-routing" in cmd
        assert "--allow-local-network" in cmd
        assert "--allow-peer-send-files" in cmd

    def test_no_permissions_no_flags(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.send_invitation("user@example.com", permissions={})
        cmd = mock_run.call_args[0][0]
        assert "--allow-incoming-traffic" not in cmd
        assert "--allow-traffic-routing" not in cmd
        assert "--allow-local-network" not in cmd
        assert "--allow-peer-send-files" not in cmd

    def test_none_permissions_no_flags(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.send_invitation("user@example.com", permissions=None)
        cmd = mock_run.call_args[0][0]
        assert "--allow-incoming-traffic" not in cmd

    def test_false_permissions_excluded(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.send_invitation("user@example.com", permissions={"incoming": False, "routing": False})
        cmd = mock_run.call_args[0][0]
        assert "--allow-incoming-traffic" not in cmd
        assert "--allow-traffic-routing" not in cmd

    def test_failure(self):
        with patch("nordvpn._run", return_value=(1, "", "error")):
            ok, _ = nordvpn.send_invitation("user@example.com")
        assert ok is False


# ---------------------------------------------------------------------------
# revoke_invitation
# ---------------------------------------------------------------------------

class TestRevokeInvitation:
    def test_success(self):
        with patch("nordvpn._run", return_value=(0, "Revoked.", "")):
            ok, _ = nordvpn.revoke_invitation("user@example.com")
        assert ok is True

    def test_email_in_command(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.revoke_invitation("user@example.com")
        cmd = mock_run.call_args[0][0]
        assert "user@example.com" in cmd

    def test_failure(self):
        with patch("nordvpn._run", return_value=(1, "", "Not found.")):
            ok, _ = nordvpn.revoke_invitation("user@example.com")
        assert ok is False


# ---------------------------------------------------------------------------
# accept_invitation
# ---------------------------------------------------------------------------

class TestAcceptInvitation:
    def test_success(self):
        with patch("nordvpn._run", return_value=(0, "Accepted.", "")):
            ok, _ = nordvpn.accept_invitation("sender@example.com")
        assert ok is True

    def test_email_is_last_argument(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.accept_invitation("sender@example.com", permissions={"incoming": True})
        cmd = mock_run.call_args[0][0]
        assert cmd[-1] == "sender@example.com"

    def test_incoming_permission(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.accept_invitation("sender@example.com", permissions={"incoming": True})
        cmd = mock_run.call_args[0][0]
        assert "--allow-incoming-traffic" in cmd
        assert "--allow-traffic-routing" not in cmd

    def test_all_permissions(self):
        perms = {"incoming": True, "routing": True, "local": True, "fileshare": True}
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.accept_invitation("sender@example.com", permissions=perms)
        cmd = mock_run.call_args[0][0]
        assert "--allow-incoming-traffic" in cmd
        assert "--allow-traffic-routing" in cmd
        assert "--allow-local-network" in cmd
        assert "--allow-peer-send-files" in cmd

    def test_no_permissions_no_flags(self):
        """Accepting with explicit empty permissions grants nothing, not all."""
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.accept_invitation("sender@example.com", permissions={})
        cmd = mock_run.call_args[0][0]
        assert "--allow-incoming-traffic" not in cmd
        assert "--allow-traffic-routing" not in cmd
        assert "--allow-local-network" not in cmd
        assert "--allow-peer-send-files" not in cmd

    def test_none_permissions_no_flags(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.accept_invitation("sender@example.com", permissions=None)
        cmd = mock_run.call_args[0][0]
        assert "--allow-incoming-traffic" not in cmd

    def test_failure(self):
        with patch("nordvpn._run", return_value=(1, "", "error")):
            ok, _ = nordvpn.accept_invitation("sender@example.com")
        assert ok is False


# ---------------------------------------------------------------------------
# deny_invitation
# ---------------------------------------------------------------------------

class TestDenyInvitation:
    def test_success(self):
        with patch("nordvpn._run", return_value=(0, "Denied.", "")):
            ok, _ = nordvpn.deny_invitation("sender@example.com")
        assert ok is True

    def test_failure(self):
        with patch("nordvpn._run", return_value=(1, "", "error")):
            ok, _ = nordvpn.deny_invitation("sender@example.com")
        assert ok is False
