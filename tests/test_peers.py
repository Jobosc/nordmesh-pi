"""Unit tests for nordvpn.py peer management: _parse_peer_list, list_peers, set_permission, set_all_permissions, set_nickname, remove_peer."""

from unittest.mock import patch

import pytest

import nordvpn


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


# ---------------------------------------------------------------------------
# _parse_peer_list
# ---------------------------------------------------------------------------

class TestParsePeerList:
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

    def test_nickname_dash_excluded(self):
        raw = """\
This device:
--------------
Hostname: mydevice.nord
Nickname: -
"""
        peers = nordvpn._parse_peer_list(raw)
        assert "nickname" not in peers[0]

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

    def test_empty_output(self):
        assert nordvpn._parse_peer_list("") == []


# ---------------------------------------------------------------------------
# list_peers
# ---------------------------------------------------------------------------

class TestListPeers:
    def test_calls_correct_command(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.list_peers()
        cmd = mock_run.call_args[0][0]
        assert "peer" in cmd
        assert "list" in cmd

    def test_returns_empty_on_error(self):
        with patch("nordvpn._run", return_value=(1, "", "meshnet is not enabled")):
            assert nordvpn.list_peers() == []


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

    def test_perm_name_in_command(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.set_permission("peer.nord", "fileshare", True)
        cmd = mock_run.call_args[0][0]
        assert "fileshare" in cmd

    def test_failure(self):
        with patch("nordvpn._run", return_value=(1, "", "error")):
            ok, _ = nordvpn.set_permission("peer.nord", "incoming", True)
        assert ok is False


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

    def test_peer_in_command(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.remove_peer("peer.nord")
        cmd = mock_run.call_args[0][0]
        assert "peer.nord" in cmd

    def test_failure(self):
        with patch("nordvpn._run", return_value=(1, "", "error")):
            ok, _ = nordvpn.remove_peer("peer.nord")
        assert ok is False
