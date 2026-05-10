"""Unit tests for nordvpn.py."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

import nordvpn


# ---------------------------------------------------------------------------
# _run
# ---------------------------------------------------------------------------

class TestRun:
    def test_success(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
            code, out, err = nordvpn._run(["nordvpn", "version"])
        assert code == 0
        assert out == "ok"
        assert err == ""

    def test_nonzero_returncode(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error msg")
            code, out, err = nordvpn._run(["nordvpn", "bad-cmd"])
        assert code == 1
        assert err == "error msg"

    def test_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["x"], timeout=5)):
            code, out, err = nordvpn._run(["nordvpn", "slow"], timeout=5)
        assert code == 1
        assert "timed out" in err

    def test_command_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            code, out, err = nordvpn._run(["nordvpn"])
        assert code == 127
        assert "not found" in err


# ---------------------------------------------------------------------------
# is_installed
# ---------------------------------------------------------------------------

class TestIsInstalled:
    def test_installed(self):
        with patch("shutil.which", return_value="/usr/bin/nordvpn"):
            assert nordvpn.is_installed() is True

    def test_not_installed(self):
        with patch("shutil.which", return_value=None):
            assert nordvpn.is_installed() is False


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------

class TestGetStatus:
    def test_not_installed(self):
        with patch("nordvpn.is_installed", return_value=False):
            status = nordvpn.get_status()
        assert status["installed"] is False
        assert status["logged_in"] is False
        assert status["meshnet_enabled"] is False

    def test_logged_in_meshnet_enabled(self):
        account_out = "Email Address: user@example.com\nVPN Service: Active"
        peer_out = "This device:\nHostname: mydevice.nord"
        vpn_out = "Status: Disconnected"

        def fake_run(cmd, **kwargs):
            if "account" in cmd:
                return (0, account_out, "")
            if "peer" in cmd and "list" in cmd:
                return (0, peer_out, "")
            if "status" in cmd:
                return (0, vpn_out, "")
            return (1, "", "")

        with patch("nordvpn.is_installed", return_value=True), \
             patch("nordvpn._run", side_effect=fake_run):
            status = nordvpn.get_status()

        assert status["installed"] is True
        assert status["logged_in"] is True
        assert status["meshnet_enabled"] is True
        assert status["email_address"] == "user@example.com"
        assert status["connection"] == "Disconnected"

    def test_not_logged_in(self):
        def fake_run(cmd, **kwargs):
            if "account" in cmd:
                return (1, "You are not logged in.", "")
            if "peer" in cmd:
                return (1, "", "")
            if "status" in cmd:
                return (0, "Status: Disconnected", "")
            return (1, "", "")

        with patch("nordvpn.is_installed", return_value=True), \
             patch("nordvpn._run", side_effect=fake_run):
            status = nordvpn.get_status()

        assert status["logged_in"] is False
        assert status["meshnet_enabled"] is False

    def test_meshnet_disabled(self):
        def fake_run(cmd, **kwargs):
            if "account" in cmd:
                return (0, "Email Address: user@example.com", "")
            if "peer" in cmd:
                return (0, "Meshnet is not enabled.", "")
            if "status" in cmd:
                return (0, "Status: Connected", "")
            return (1, "", "")

        with patch("nordvpn.is_installed", return_value=True), \
             patch("nordvpn._run", side_effect=fake_run):
            status = nordvpn.get_status()

        assert status["meshnet_enabled"] is False
        assert status["connection"] == "Connected"


# ---------------------------------------------------------------------------
# login / login_with_token / logout
# ---------------------------------------------------------------------------

class TestLogin:
    def test_returns_url(self):
        url = "https://api.nordvpn.com/v1/users/oauth/login-redirect?attempt=abc"
        with patch("nordvpn._run", return_value=(0, f"Open this URL: {url}", "")):
            ok, msg = nordvpn.login()
        assert ok is True
        assert msg == url

    def test_url_in_stderr(self):
        url = "https://api.nordvpn.com/v1/users/oauth/login-redirect?attempt=xyz"
        with patch("nordvpn._run", return_value=(1, "", f"Visit: {url}")):
            ok, msg = nordvpn.login()
        assert ok is True
        assert msg == url

    def test_already_logged_in(self):
        with patch("nordvpn._run", return_value=(1, "You are already logged in.", "")):
            ok, msg = nordvpn.login()
        assert ok is True

    def test_no_url_failure(self):
        with patch("nordvpn._run", return_value=(1, "some error", "")):
            ok, msg = nordvpn.login()
        assert ok is False


class TestLoginWithToken:
    def test_success_code_zero(self):
        with patch("nordvpn._run", return_value=(0, "Welcome to NordVPN!", "")):
            ok, msg = nordvpn.login_with_token("mytoken")
        assert ok is True

    def test_success_welcome_message(self):
        with patch("nordvpn._run", return_value=(1, "Welcome, user!", "")):
            ok, msg = nordvpn.login_with_token("mytoken")
        assert ok is True

    def test_already_logged_in(self):
        with patch("nordvpn._run", return_value=(1, "Already logged in.", "")):
            ok, msg = nordvpn.login_with_token("mytoken")
        assert ok is True

    def test_failure(self):
        with patch("nordvpn._run", return_value=(1, "Invalid token.", "")):
            ok, msg = nordvpn.login_with_token("badtoken")
        assert ok is False

    def test_token_is_passed_to_command(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.login_with_token("secret123")
        cmd = mock_run.call_args[0][0]
        assert "--token" in cmd
        assert "secret123" in cmd


class TestLogout:
    def test_success(self):
        with patch("nordvpn._run", return_value=(0, "You have been logged out.", "")):
            ok, msg = nordvpn.logout()
        assert ok is True

    def test_failure(self):
        with patch("nordvpn._run", return_value=(1, "", "Not logged in.")):
            ok, msg = nordvpn.logout()
        assert ok is False


# ---------------------------------------------------------------------------
# enable_meshnet / disable_meshnet
# ---------------------------------------------------------------------------

class TestMeshnet:
    def test_enable_success(self):
        with patch("nordvpn._run", return_value=(0, "Meshnet is enabled.", "")):
            ok, msg = nordvpn.enable_meshnet()
        assert ok is True

    def test_enable_already_enabled(self):
        with patch("nordvpn._run", return_value=(1, "Meshnet is already enabled.", "")):
            ok, msg = nordvpn.enable_meshnet()
        assert ok is True

    def test_enable_failure(self):
        with patch("nordvpn._run", return_value=(1, "", "error")):
            ok, _ = nordvpn.enable_meshnet()
        assert ok is False

    def test_disable_success(self):
        with patch("nordvpn._run", return_value=(0, "Meshnet is disabled.", "")):
            ok, _ = nordvpn.disable_meshnet()
        assert ok is True

    def test_disable_failure(self):
        with patch("nordvpn._run", return_value=(1, "", "error")):
            ok, _ = nordvpn.disable_meshnet()
        assert ok is False


# ---------------------------------------------------------------------------
# _parse_peer_list
# ---------------------------------------------------------------------------

PEER_LIST_FULL = """\
This device:
--------------
Hostname: mydevice.nord
Nickname: home-pc
Status: connected
IP: 100.64.0.1
OS: Linux

Local Peers:
--------------
Hostname: localdevice.nord
Nickname: -
Status: connected
IP: 100.64.0.2
OS: Linux
Allow Incoming Traffic: enabled
Allow Routing: disabled
Allow Local Network Access: enabled
Allow Sending Files: disabled
Accept Fileshare Automatically: disabled
Allows Incoming Traffic: enabled
Allows Routing: disabled
Allows Local Network Access: disabled
Allows Sending Files: enabled

External Peers:
--------------
Hostname: remotedevice.nord
Nickname: work-laptop
Status: disconnected
IP: 100.64.0.3
OS: Windows
Allow Incoming Traffic: disabled
Allow Routing: enabled
Allow Local Network Access: disabled
Allow Sending Files: enabled
Accept Fileshare Automatically: enabled
Allows Incoming Traffic: disabled
Allows Routing: disabled
Allows Local Network Access: disabled
Allows Sending Files: disabled
"""


class TestParsePeerList:
    def test_empty_output(self):
        assert nordvpn._parse_peer_list("") == []

    def test_self_device(self):
        raw = """\
This device:
--------------
Hostname: mydevice.nord
Nickname: home-pc
Status: connected
IP: 100.64.0.1
"""
        peers = nordvpn._parse_peer_list(raw)
        assert len(peers) == 1
        p = peers[0]
        assert p["hostname"] == "mydevice.nord"
        assert p["nickname"] == "home-pc"
        assert p["status"] == "connected"
        assert p["ip"] == "100.64.0.1"
        assert p["is_self"] is True
        assert p["is_local"] is True

    def test_nickname_dash_excluded(self):
        raw = """\
This device:
--------------
Hostname: mydevice.nord
Nickname: -
"""
        peers = nordvpn._parse_peer_list(raw)
        assert "nickname" not in peers[0]

    def test_local_peer_section(self):
        raw = """\
Local Peers:
--------------
Hostname: localdevice.nord
Nickname: local-box
Status: connected
IP: 100.64.0.2
"""
        peers = nordvpn._parse_peer_list(raw)
        assert len(peers) == 1
        assert peers[0]["is_local"] is True
        assert peers[0]["is_self"] is False

    def test_external_peer_section(self):
        raw = """\
External Peers:
--------------
Hostname: remotedevice.nord
Nickname: remote
Status: disconnected
IP: 100.64.0.3
"""
        peers = nordvpn._parse_peer_list(raw)
        assert len(peers) == 1
        assert peers[0]["is_local"] is False
        assert peers[0]["is_self"] is False

    def test_permissions_enabled(self):
        raw = """\
External Peers:
--------------
Hostname: peer.nord
Allow Incoming Traffic: enabled
Allow Routing: enabled
Allow Local Network Access: enabled
Allow Sending Files: enabled
Accept Fileshare Automatically: enabled
"""
        peers = nordvpn._parse_peer_list(raw)
        perms = peers[0]["permissions"]
        assert perms["incoming"] is True
        assert perms["routing"] is True
        assert perms["local_network"] is True
        assert perms["fileshare"] is True
        assert perms["auto_accept"] is True

    def test_permissions_disabled(self):
        raw = """\
External Peers:
--------------
Hostname: peer.nord
Allow Incoming Traffic: disabled
Allow Routing: disabled
Allow Local Network Access: disabled
Allow Sending Files: disabled
Accept Fileshare Automatically: disabled
"""
        peers = nordvpn._parse_peer_list(raw)
        perms = peers[0]["permissions"]
        assert perms["incoming"] is False
        assert perms["routing"] is False
        assert perms["local_network"] is False
        assert perms["fileshare"] is False
        assert perms["auto_accept"] is False

    def test_allows_permissions(self):
        raw = """\
External Peers:
--------------
Hostname: peer.nord
Allows Incoming Traffic: enabled
Allows Routing: disabled
Allows Local Network Access: enabled
Allows Sending Files: disabled
"""
        peers = nordvpn._parse_peer_list(raw)
        perms = peers[0]["permissions"]
        assert perms["allows_incoming"] is True
        assert perms["allows_routing"] is False
        assert perms["allows_local_network"] is True
        assert perms["allows_fileshare"] is False

    def test_multiple_peers(self):
        peers = nordvpn._parse_peer_list(PEER_LIST_FULL)
        assert len(peers) == 3
        hostnames = [p["hostname"] for p in peers]
        assert "mydevice.nord" in hostnames
        assert "localdevice.nord" in hostnames
        assert "remotedevice.nord" in hostnames

    def test_sections_set_correct_flags(self):
        peers = nordvpn._parse_peer_list(PEER_LIST_FULL)
        by_host = {p["hostname"]: p for p in peers}

        assert by_host["mydevice.nord"]["is_self"] is True
        assert by_host["mydevice.nord"]["is_local"] is True

        assert by_host["localdevice.nord"]["is_self"] is False
        assert by_host["localdevice.nord"]["is_local"] is True

        assert by_host["remotedevice.nord"]["is_self"] is False
        assert by_host["remotedevice.nord"]["is_local"] is False

    def test_separator_lines_ignored(self):
        raw = """\
This device:
==============
Hostname: mydevice.nord
--------------
Status: connected
"""
        peers = nordvpn._parse_peer_list(raw)
        assert len(peers) == 1
        assert peers[0]["hostname"] == "mydevice.nord"

    def test_nickname_before_hostname(self):
        """Nickname appearing before Hostname should still be captured."""
        raw = """\
External Peers:
--------------
Nickname: early-nick
Hostname: peer.nord
Status: connected
"""
        peers = nordvpn._parse_peer_list(raw)
        assert len(peers) == 1
        assert peers[0]["nickname"] == "early-nick"

    def test_list_peers_returns_empty_on_error(self):
        with patch("nordvpn._run", return_value=(1, "", "meshnet is not enabled")):
            assert nordvpn.list_peers() == []

    def test_list_peers_calls_correct_command(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.list_peers()
        cmd = mock_run.call_args[0][0]
        assert "peer" in cmd
        assert "list" in cmd


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

    def test_list_invitations_returns_empty_on_error(self):
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

    def test_failure(self):
        with patch("nordvpn._run", return_value=(1, "", "error")):
            ok, _ = nordvpn.send_invitation("user@example.com")
        assert ok is False

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

    def test_email_is_last_argument(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.send_invitation("user@example.com", permissions={"incoming": True})
        cmd = mock_run.call_args[0][0]
        assert cmd[-1] == "user@example.com"

    def test_false_permissions_excluded(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.send_invitation("user@example.com", permissions={"incoming": False, "routing": False})
        cmd = mock_run.call_args[0][0]
        assert "--allow-incoming-traffic" not in cmd
        assert "--allow-traffic-routing" not in cmd


# ---------------------------------------------------------------------------
# revoke_invitation
# ---------------------------------------------------------------------------

class TestRevokeInvitation:
    def test_success(self):
        with patch("nordvpn._run", return_value=(0, "Revoked.", "")):
            ok, _ = nordvpn.revoke_invitation("user@example.com")
        assert ok is True

    def test_failure(self):
        with patch("nordvpn._run", return_value=(1, "", "Not found.")):
            ok, _ = nordvpn.revoke_invitation("user@example.com")
        assert ok is False

    def test_email_in_command(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.revoke_invitation("user@example.com")
        cmd = mock_run.call_args[0][0]
        assert "user@example.com" in cmd


# ---------------------------------------------------------------------------
# accept_invitation
# ---------------------------------------------------------------------------

class TestAcceptInvitation:
    def test_success(self):
        with patch("nordvpn._run", return_value=(0, "Accepted.", "")):
            ok, _ = nordvpn.accept_invitation("sender@example.com")
        assert ok is True

    def test_failure(self):
        with patch("nordvpn._run", return_value=(1, "", "error")):
            ok, _ = nordvpn.accept_invitation("sender@example.com")
        assert ok is False

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

    def test_email_is_last_argument(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.accept_invitation("sender@example.com", permissions={"incoming": True})
        cmd = mock_run.call_args[0][0]
        assert cmd[-1] == "sender@example.com"


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


# ---------------------------------------------------------------------------
# set_permission
# ---------------------------------------------------------------------------

class TestSetPermission:
    def test_allow(self):
        with patch("nordvpn._run", return_value=(0, "ok", "")) as mock_run:
            ok, _ = nordvpn.set_permission("peer.nord", "incoming", True)
        assert ok is True
        cmd = mock_run.call_args[0][0]
        assert "allow" in cmd
        assert "peer.nord" in cmd

    def test_deny(self):
        with patch("nordvpn._run", return_value=(0, "ok", "")) as mock_run:
            ok, _ = nordvpn.set_permission("peer.nord", "routing", False)
        assert ok is True
        cmd = mock_run.call_args[0][0]
        assert "deny" in cmd
        assert "peer.nord" in cmd

    def test_failure(self):
        with patch("nordvpn._run", return_value=(1, "", "error")):
            ok, _ = nordvpn.set_permission("peer.nord", "incoming", True)
        assert ok is False

    def test_perm_name_in_command(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.set_permission("peer.nord", "fileshare", True)
        cmd = mock_run.call_args[0][0]
        assert "fileshare" in cmd


# ---------------------------------------------------------------------------
# set_all_permissions
# ---------------------------------------------------------------------------

class TestSetAllPermissions:
    def test_returns_results_for_each_perm(self):
        with patch("nordvpn._run", return_value=(0, "ok", "")):
            results = nordvpn.set_all_permissions(
                "peer.nord",
                {"incoming": True, "routing": False}
            )
        assert len(results) == 2
        perms_returned = {r[0] for r in results}
        assert "incoming" in perms_returned
        assert "routing" in perms_returned

    def test_all_success(self):
        with patch("nordvpn._run", return_value=(0, "ok", "")):
            results = nordvpn.set_all_permissions(
                "peer.nord",
                {"incoming": True, "routing": True}
            )
        assert all(r[1] for r in results)

    def test_partial_failure(self):
        call_count = 0

        def fake_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            return (0, "ok", "") if call_count == 1 else (1, "", "error")

        with patch("nordvpn._run", side_effect=fake_run):
            results = nordvpn.set_all_permissions(
                "peer.nord",
                {"incoming": True, "routing": True}
            )
        successes = [r[1] for r in results]
        assert True in successes
        assert False in successes

    def test_empty_perms(self):
        with patch("nordvpn._run", return_value=(0, "", "")):
            results = nordvpn.set_all_permissions("peer.nord", {})
        assert results == []


# ---------------------------------------------------------------------------
# set_nickname
# ---------------------------------------------------------------------------

class TestSetNickname:
    def test_set_nickname(self):
        with patch("nordvpn._run", return_value=(0, "ok", "")) as mock_run:
            ok, _ = nordvpn.set_nickname("peer.nord", "my-peer")
        assert ok is True
        cmd = mock_run.call_args[0][0]
        assert "set" in cmd
        assert "my-peer" in cmd

    def test_remove_nickname(self):
        with patch("nordvpn._run", return_value=(0, "ok", "")) as mock_run:
            ok, _ = nordvpn.set_nickname("peer.nord", "")
        assert ok is True
        cmd = mock_run.call_args[0][0]
        assert "remove" in cmd

    def test_failure(self):
        with patch("nordvpn._run", return_value=(1, "", "error")):
            ok, _ = nordvpn.set_nickname("peer.nord", "name")
        assert ok is False


# ---------------------------------------------------------------------------
# remove_peer
# ---------------------------------------------------------------------------

class TestRemovePeer:
    def test_success(self):
        with patch("nordvpn._run", return_value=(0, "Removed.", "")):
            ok, _ = nordvpn.remove_peer("peer.nord")
        assert ok is True

    def test_failure(self):
        with patch("nordvpn._run", return_value=(1, "", "error")):
            ok, _ = nordvpn.remove_peer("peer.nord")
        assert ok is False

    def test_peer_in_command(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.remove_peer("peer.nord")
        cmd = mock_run.call_args[0][0]
        assert "peer.nord" in cmd
