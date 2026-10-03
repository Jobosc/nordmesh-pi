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

    def test_injects_connection_retry_config(self, client):
        """The retry limit must reach the page, or the error screen never shows."""
        with patch("nordvpn.get_status", return_value={"installed": False}), \
             patch.object(flask_app, "CONNECT_ATTEMPTS", 7), \
             patch.object(flask_app, "CONNECT_RETRY_DELAY_MS", 1500):
            html = client.get("/").get_data(as_text=True)
        assert "const CONNECT_ATTEMPTS = 7;" in html
        assert "const CONNECT_RETRY_DELAY_MS = 1500;" in html

    def _base_path(self, client, headers=None):
        with patch("nordvpn.get_status", return_value={"installed": False}):
            html = client.get("/", headers=headers or {}).get_data(as_text=True)
        line = next(l for l in html.splitlines() if "const BASE_PATH" in l)
        return line.strip()

    def test_base_path_empty_when_accessed_directly(self, client):
        assert self._base_path(client) == 'const BASE_PATH = "";'

    def test_base_path_follows_ingress_header(self, client):
        """Behind Home Assistant ingress, API calls must stay under the sub-path."""
        line = self._base_path(client, {"X-Ingress-Path": "/api/ingress/nordmesh/"})
        assert line == 'const BASE_PATH = "/api/ingress/nordmesh";'

    def test_base_path_rejects_unsafe_header(self, client):
        line = self._base_path(client, {"X-Ingress-Path": '/x";alert(1);//'})
        assert line == 'const BASE_PATH = "";'


# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

class TestEnvInt:
    def test_reads_env_value(self):
        with patch.dict("os.environ", {"X_ATTEMPTS": "9"}):
            assert flask_app._env_int("X_ATTEMPTS", 5, 1) == 9

    def test_default_when_unset(self):
        assert flask_app._env_int("X_UNSET_ATTEMPTS", 5, 1) == 5

    def test_default_when_not_a_number(self):
        with patch.dict("os.environ", {"X_ATTEMPTS": "lots"}):
            assert flask_app._env_int("X_ATTEMPTS", 5, 1) == 5

    def test_clamped_to_minimum(self):
        with patch.dict("os.environ", {"X_ATTEMPTS": "0"}):
            assert flask_app._env_int("X_ATTEMPTS", 5, 1) == 1


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

    def test_exposes_daemon_failure(self, client):
        status = {"installed": True, "daemon_ok": False, "daemon_error": "Cannot reach System Daemon."}
        with patch("nordvpn.get_status", return_value=status):
            data = client.get("/api/status").get_json()
        assert data["daemon_ok"] is False
        assert data["daemon_error"] == "Cannot reach System Daemon."


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
    def test_iframe_allowed_by_default_on_index(self, client):
        with patch("nordvpn.get_status", return_value={"installed": False}):
            resp = client.get("/")
        assert "frame-ancestors *" in resp.headers.get("Content-Security-Policy", "")
        # X-Frame-Options has no "allow any origin" value; sending one would
        # either be ignored or block the Home Assistant iframe.
        assert resp.headers.get("X-Frame-Options") is None

    def test_iframe_allowed_by_default_on_api(self, client):
        with patch("nordvpn.get_status", return_value={"installed": False}):
            resp = client.get("/api/status")
        assert "frame-ancestors *" in resp.headers.get("Content-Security-Policy", "")
        assert resp.headers.get("X-Frame-Options") is None

    def test_frame_ancestors_can_be_restricted(self, client):
        with patch("nordvpn.get_status", return_value={"installed": False}), \
             patch.object(flask_app, "FRAME_ANCESTORS", "https://ha.example.com"):
            resp = client.get("/")
        assert resp.headers["Content-Security-Policy"] == "frame-ancestors https://ha.example.com"
        assert resp.headers.get("X-Frame-Options") is None

    def test_framing_can_be_forbidden(self, client):
        with patch("nordvpn.get_status", return_value={"installed": False}), \
             patch.object(flask_app, "FRAME_ANCESTORS", "none"):
            resp = client.get("/")
        assert resp.headers["Content-Security-Policy"] == "frame-ancestors 'none'"
        assert resp.headers["X-Frame-Options"] == "DENY"
