"""Unit tests for nordvpn.meshnet_health and GET /api/health."""

from unittest.mock import patch

import pytest

import app as flask_app
import nordvpn

HEALTHY = {"installed": True, "daemon_ok": True, "logged_in": True, "meshnet_enabled": True}


@pytest.fixture
def client():
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


class TestMeshnetHealth:
    def test_ok(self):
        assert nordvpn.meshnet_health(HEALTHY)[0] == "ok"

    @pytest.mark.parametrize("broken, state", [
        ({"installed": False}, "not_installed"),
        ({"daemon_ok": False}, "daemon_unreachable"),
        ({"logged_in": False}, "logged_out"),
        ({"meshnet_enabled": False}, "meshnet_off"),
    ])
    def test_each_failure(self, broken, state):
        assert nordvpn.meshnet_health({**HEALTHY, **broken})[0] == state

    def test_reports_root_cause_first(self):
        """A dead daemon also reads as logged out — name the daemon, not the login."""
        status = {**HEALTHY, "daemon_ok": False, "logged_in": False, "meshnet_enabled": False,
                  "daemon_error": "Cannot reach System Daemon."}
        assert nordvpn.meshnet_health(status) == ("daemon_unreachable", "Cannot reach System Daemon.")

    def test_daemon_message_fallback(self):
        state, message = nordvpn.meshnet_health({**HEALTHY, "daemon_ok": False})
        assert message == "The NordVPN daemon is not responding."


class TestHealthRoute:
    def test_healthy(self, client):
        with patch("nordvpn.get_status", return_value=HEALTHY):
            resp = client.get("/api/health")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["ok"] is True and data["state"] == "ok"
        assert data["checked_at"]

    def test_unhealthy_still_answers_200(self, client):
        """Home Assistant tells "Meshnet down" from "Pi down" by getting an answer."""
        with patch("nordvpn.get_status", return_value={**HEALTHY, "meshnet_enabled": False}):
            resp = client.get("/api/health")
        data = resp.get_json()
        assert resp.status_code == 200
        assert data == {**data, "ok": False, "state": "meshnet_off", "message": "Meshnet is turned off."}
