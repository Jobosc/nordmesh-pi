"""Unit tests for nordvpn.py meshnet lifecycle: enable_meshnet, disable_meshnet, get_status, is_installed, install_nordvpn."""

from unittest.mock import patch

import pytest

import nordvpn


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

    def test_not_installed(self):
        with patch("nordvpn.is_installed", return_value=False):
            status = nordvpn.get_status()
        assert status["installed"] is False
        assert status["logged_in"] is False
        assert status["meshnet_enabled"] is False


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
