"""Unit tests for app.py setup and auth routes: GET /, GET /api/status, POST /api/install, POST /api/login, POST /api/logout, and response headers."""

from unittest.mock import patch

import pytest

import app as flask_app


@pytest.fixture
def client():
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------

class TestIndex:
    def test_renders_without_error(self, client):
        with patch("nordvpn.get_status", return_value={"installed": False}):
            resp = client.get("/")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/status
# ---------------------------------------------------------------------------

class TestAPIStatus:
    def test_returns_status(self, client):
        status = {"installed": True, "logged_in": True, "meshnet_enabled": False, "connection": "Disconnected"}
        with patch("nordvpn.get_status", return_value=status):
            resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["installed"] is True
        assert data["logged_in"] is True

    def test_not_installed(self, client):
        with patch("nordvpn.get_status", return_value={"installed": False, "logged_in": False}):
            resp = client.get("/api/status")
        assert resp.get_json()["installed"] is False


# ---------------------------------------------------------------------------
# POST /api/install
# ---------------------------------------------------------------------------

class TestAPIInstall:
    def test_install_success(self, client):
        with patch("nordvpn.install_nordvpn", return_value=(True, "NordVPN installed successfully.")):
            resp = client.post("/api/install")
        data = resp.get_json()
        assert data["success"] is True
        assert "installed" in data["message"].lower()

    def test_install_failure(self, client):
        with patch("nordvpn.install_nordvpn", return_value=(False, "Installation failed.")):
            resp = client.post("/api/install")
        data = resp.get_json()
        assert data["success"] is False


# ---------------------------------------------------------------------------
# POST /api/login
# ---------------------------------------------------------------------------

class TestAPILogin:
    def test_login_returns_url(self, client):
        url = "https://nordvpn.com/oauth?attempt=abc"
        with patch("nordvpn.login", return_value=(True, url)):
            resp = client.post("/api/login", json={})
        data = resp.get_json()
        assert data["success"] is True
        assert data["url"] == url

    def test_login_url_also_in_message(self, client):
        url = "https://nordvpn.com/oauth?attempt=abc"
        with patch("nordvpn.login", return_value=(True, url)):
            data = client.post("/api/login", json={}).get_json()
        assert data["message"] == url

    def test_login_with_token(self, client):
        with patch("nordvpn.login_with_token", return_value=(True, "Login successful.")):
            resp = client.post("/api/login", json={"token": "mytoken"})
        assert resp.get_json()["success"] is True

    def test_login_passes_user_input(self, client):
        url = "https://nordvpn.com/oauth?attempt=abc"
        with patch("nordvpn.login", return_value=(True, url)) as mock_fn:
            client.post("/api/login", json={"user_input": "y"})
        mock_fn.assert_called_once_with(user_input="y")

    def test_login_no_user_input_passes_none(self, client):
        with patch("nordvpn.login", return_value=(False, "error")) as mock_fn:
            client.post("/api/login", json={})
        mock_fn.assert_called_once_with(user_input=None)

    def test_login_with_token_calls_token_fn(self, client):
        with patch("nordvpn.login_with_token", return_value=(True, "ok")) as mock_fn, \
             patch("nordvpn.login") as mock_login:
            client.post("/api/login", json={"token": "abc123"})
        mock_fn.assert_called_once_with("abc123")
        mock_login.assert_not_called()

    def test_login_without_token_calls_login_fn(self, client):
        with patch("nordvpn.login", return_value=(True, "url")) as mock_fn, \
             patch("nordvpn.login_with_token") as mock_token:
            client.post("/api/login", json={})
        mock_fn.assert_called_once()
        mock_token.assert_not_called()

    def test_login_needs_input(self, client):
        prompt = "Do you agree to share data? (y/n)"
        with patch("nordvpn.login", return_value=(False, f"NEEDS_INPUT:{prompt}")):
            data = client.post("/api/login", json={}).get_json()
        assert data["success"] is False
        assert data["needs_input"] is True
        assert data["prompt"] == prompt

    def test_login_no_body_accepted(self, client):
        """POST with no body / no Content-Type must not return 415."""
        with patch("nordvpn.login", return_value=(False, "error")):
            resp = client.post("/api/login")
        assert resp.status_code == 200

    def test_login_failure(self, client):
        with patch("nordvpn.login", return_value=(False, "error")):
            resp = client.post("/api/login", json={})
        assert resp.get_json()["success"] is False


# ---------------------------------------------------------------------------
# POST /api/logout
# ---------------------------------------------------------------------------

class TestAPILogout:
    def test_logout_success(self, client):
        with patch("nordvpn.logout", return_value=(True, "Logged out.")):
            resp = client.post("/api/logout")
        assert resp.get_json()["success"] is True

    def test_logout_failure(self, client):
        with patch("nordvpn.logout", return_value=(False, "Not logged in.")):
            resp = client.post("/api/logout")
        assert resp.get_json()["success"] is False


# ---------------------------------------------------------------------------
# Response headers (iframe embedding)
# ---------------------------------------------------------------------------

class TestResponseHeaders:
    def test_iframe_headers_on_index(self, client):
        with patch("nordvpn.get_status", return_value={"installed": False}):
            resp = client.get("/")
        assert resp.headers.get("X-Frame-Options") == "ALLOWALL"
        assert "frame-ancestors *" in resp.headers.get("Content-Security-Policy", "")

    def test_iframe_headers_on_api(self, client):
        with patch("nordvpn.get_status", return_value={"installed": False}):
            resp = client.get("/api/status")
        assert resp.headers.get("X-Frame-Options") == "ALLOWALL"
