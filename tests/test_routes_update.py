"""Unit tests for app.py update routes: GET /api/version, POST /api/update."""

from unittest.mock import patch

import pytest

import app as flask_app


@pytest.fixture
def client():
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# GET /api/version
# ---------------------------------------------------------------------------

class TestAPIVersion:
    def test_returns_version_info(self, client):
        info = {"current": "v1.0.0", "latest": "v1.2.0", "update_available": True}
        with patch("nordvpn.check_update", return_value=info):
            resp = client.get("/api/version")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["current"] == "v1.0.0"
        assert data["latest"] == "v1.2.0"
        assert data["update_available"] is True

    def test_no_update_available(self, client):
        info = {"current": "v1.2.0", "latest": "v1.2.0", "update_available": False}
        with patch("nordvpn.check_update", return_value=info):
            data = client.get("/api/version").get_json()
        assert data["update_available"] is False

    def test_unknown_version(self, client):
        info = {"current": "unknown", "latest": "", "update_available": False}
        with patch("nordvpn.check_update", return_value=info):
            data = client.get("/api/version").get_json()
        assert data["current"] == "unknown"


# ---------------------------------------------------------------------------
# POST /api/update
# ---------------------------------------------------------------------------

class TestAPIUpdate:
    def test_update_success(self, client):
        with patch("nordvpn.perform_update", return_value=(True, "Update applied. Service restarting...")):
            resp = client.post("/api/update")
        data = resp.get_json()
        assert data["success"] is True
        assert "update applied" in data["message"].lower()

    def test_calls_perform_update(self, client):
        with patch("nordvpn.perform_update", return_value=(True, "ok")) as mock_fn:
            client.post("/api/update")
        mock_fn.assert_called_once()

    def test_update_failure(self, client):
        with patch("nordvpn.perform_update", return_value=(False, "git pull failed: network error")):
            resp = client.post("/api/update")
        data = resp.get_json()
        assert data["success"] is False
        assert "git pull failed" in data["message"].lower()
