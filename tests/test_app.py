"""Unit tests for Flask routes in app.py."""

from unittest.mock import MagicMock, patch

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
        assert data["message"] == url

    def test_login_with_token(self, client):
        with patch("nordvpn.login_with_token", return_value=(True, "Login successful.")):
            resp = client.post("/api/login", json={"token": "mytoken"})
        data = resp.get_json()
        assert data["success"] is True

    def test_login_failure(self, client):
        with patch("nordvpn.login", return_value=(False, "error")):
            resp = client.post("/api/login", json={})
        assert resp.get_json()["success"] is False

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
# POST /api/meshnet/enable and /api/meshnet/disable
# ---------------------------------------------------------------------------

class TestAPIMeshnet:
    def test_enable_success(self, client):
        with patch("nordvpn.enable_meshnet", return_value=(True, "Meshnet enabled.")):
            resp = client.post("/api/meshnet/enable")
        assert resp.get_json()["success"] is True

    def test_enable_failure(self, client):
        with patch("nordvpn.enable_meshnet", return_value=(False, "error")):
            resp = client.post("/api/meshnet/enable")
        assert resp.get_json()["success"] is False

    def test_disable_success(self, client):
        with patch("nordvpn.disable_meshnet", return_value=(True, "Meshnet disabled.")):
            resp = client.post("/api/meshnet/disable")
        assert resp.get_json()["success"] is True

    def test_disable_failure(self, client):
        with patch("nordvpn.disable_meshnet", return_value=(False, "error")):
            resp = client.post("/api/meshnet/disable")
        assert resp.get_json()["success"] is False


# ---------------------------------------------------------------------------
# GET /api/peers
# ---------------------------------------------------------------------------

class TestAPIPeers:
    def test_returns_peer_list(self, client):
        peers = [
            {"hostname": "peer1.nord", "is_local": True, "is_self": False, "permissions": {}},
            {"hostname": "peer2.nord", "is_local": False, "is_self": False, "permissions": {}},
        ]
        with patch("nordvpn.list_peers", return_value=peers):
            resp = client.get("/api/peers")
        data = resp.get_json()
        assert len(data) == 2
        assert data[0]["hostname"] == "peer1.nord"

    def test_returns_empty_list(self, client):
        with patch("nordvpn.list_peers", return_value=[]):
            resp = client.get("/api/peers")
        assert resp.get_json() == []


# ---------------------------------------------------------------------------
# POST /api/peers/<peer>/permissions
# ---------------------------------------------------------------------------

class TestAPISetPermissions:
    def test_success(self, client):
        results = [("incoming", True, "ok"), ("routing", True, "ok")]
        with patch("nordvpn.set_all_permissions", return_value=results):
            resp = client.post(
                "/api/peers/peer.nord/permissions",
                json={"incoming": True, "routing": True}
            )
        data = resp.get_json()
        assert len(data) == 2
        assert data[0]["success"] is True

    def test_peer_with_dots_in_name(self, client):
        with patch("nordvpn.set_all_permissions", return_value=[]) as mock_fn:
            client.post("/api/peers/my.peer.nord/permissions", json={})
        mock_fn.assert_called_once_with("my.peer.nord", {})

    def test_response_structure(self, client):
        results = [("incoming", False, "permission denied")]
        with patch("nordvpn.set_all_permissions", return_value=results):
            resp = client.post("/api/peers/peer.nord/permissions", json={"incoming": False})
        item = resp.get_json()[0]
        assert "permission" in item
        assert "success" in item
        assert "message" in item


# ---------------------------------------------------------------------------
# POST /api/peers/<peer>/nickname
# ---------------------------------------------------------------------------

class TestAPISetNickname:
    def test_set_nickname_success(self, client):
        with patch("nordvpn.set_nickname", return_value=(True, "ok")):
            resp = client.post("/api/peers/peer.nord/nickname", json={"nickname": "my-peer"})
        assert resp.get_json()["success"] is True

    def test_set_nickname_failure(self, client):
        with patch("nordvpn.set_nickname", return_value=(False, "error")):
            resp = client.post("/api/peers/peer.nord/nickname", json={"nickname": "bad"})
        assert resp.get_json()["success"] is False

    def test_nickname_passed_to_function(self, client):
        with patch("nordvpn.set_nickname", return_value=(True, "ok")) as mock_fn:
            client.post("/api/peers/peer.nord/nickname", json={"nickname": "custom-name"})
        mock_fn.assert_called_once_with("peer.nord", "custom-name")

    def test_empty_nickname_removes(self, client):
        with patch("nordvpn.set_nickname", return_value=(True, "ok")) as mock_fn:
            client.post("/api/peers/peer.nord/nickname", json={"nickname": ""})
        mock_fn.assert_called_once_with("peer.nord", "")

    def test_missing_nickname_key_defaults_to_empty(self, client):
        with patch("nordvpn.set_nickname", return_value=(True, "ok")) as mock_fn:
            client.post("/api/peers/peer.nord/nickname", json={})
        mock_fn.assert_called_once_with("peer.nord", "")


# ---------------------------------------------------------------------------
# POST /api/peers/<peer>/remove
# ---------------------------------------------------------------------------

class TestAPIRemovePeer:
    def test_remove_success(self, client):
        with patch("nordvpn.remove_peer", return_value=(True, "Removed.")):
            resp = client.post("/api/peers/peer.nord/remove")
        assert resp.get_json()["success"] is True

    def test_remove_failure(self, client):
        with patch("nordvpn.remove_peer", return_value=(False, "error")):
            resp = client.post("/api/peers/peer.nord/remove")
        assert resp.get_json()["success"] is False

    def test_peer_passed_to_function(self, client):
        with patch("nordvpn.remove_peer", return_value=(True, "ok")) as mock_fn:
            client.post("/api/peers/some.device.nord/remove")
        mock_fn.assert_called_once_with("some.device.nord")


# ---------------------------------------------------------------------------
# GET /api/invitations
# ---------------------------------------------------------------------------

class TestAPIGetInvitations:
    def test_returns_invitations(self, client):
        invitations = {"sent": ["a@example.com"], "received": ["b@example.com"]}
        with patch("nordvpn.list_invitations", return_value=invitations):
            resp = client.get("/api/invitations")
        data = resp.get_json()
        assert data["sent"] == ["a@example.com"]
        assert data["received"] == ["b@example.com"]

    def test_empty_invitations(self, client):
        with patch("nordvpn.list_invitations", return_value={"sent": [], "received": []}):
            resp = client.get("/api/invitations")
        data = resp.get_json()
        assert data["sent"] == []
        assert data["received"] == []


# ---------------------------------------------------------------------------
# POST /api/invitations/send
# ---------------------------------------------------------------------------

class TestAPISendInvitation:
    def test_send_success(self, client):
        with patch("nordvpn.send_invitation", return_value=(True, "Invitation sent to user@example.com.")):
            resp = client.post("/api/invitations/send", json={"email": "user@example.com", "permissions": {}})
        data = resp.get_json()
        assert data["success"] is True

    def test_send_failure(self, client):
        with patch("nordvpn.send_invitation", return_value=(False, "error")):
            resp = client.post("/api/invitations/send", json={"email": "user@example.com", "permissions": {}})
        assert resp.get_json()["success"] is False

    def test_email_and_permissions_forwarded(self, client):
        with patch("nordvpn.send_invitation", return_value=(True, "ok")) as mock_fn:
            client.post(
                "/api/invitations/send",
                json={"email": "user@example.com", "permissions": {"incoming": True}}
            )
        mock_fn.assert_called_once_with("user@example.com", {"incoming": True})

    def test_missing_email_sends_empty_string(self, client):
        with patch("nordvpn.send_invitation", return_value=(False, "error")) as mock_fn:
            client.post("/api/invitations/send", json={"permissions": {}})
        mock_fn.assert_called_once_with("", {})


# ---------------------------------------------------------------------------
# POST /api/invitations/revoke
# ---------------------------------------------------------------------------

class TestAPIRevokeInvitation:
    def test_revoke_success(self, client):
        with patch("nordvpn.revoke_invitation", return_value=(True, "Revoked.")):
            resp = client.post("/api/invitations/revoke", json={"email": "user@example.com"})
        assert resp.get_json()["success"] is True

    def test_revoke_failure(self, client):
        with patch("nordvpn.revoke_invitation", return_value=(False, "error")):
            resp = client.post("/api/invitations/revoke", json={"email": "user@example.com"})
        assert resp.get_json()["success"] is False

    def test_email_forwarded(self, client):
        with patch("nordvpn.revoke_invitation", return_value=(True, "ok")) as mock_fn:
            client.post("/api/invitations/revoke", json={"email": "user@example.com"})
        mock_fn.assert_called_once_with("user@example.com")


# ---------------------------------------------------------------------------
# POST /api/invitations/accept
# ---------------------------------------------------------------------------

class TestAPIAcceptInvitation:
    def test_accept_success(self, client):
        with patch("nordvpn.accept_invitation", return_value=(True, "Accepted.")):
            resp = client.post("/api/invitations/accept", json={"email": "sender@example.com", "permissions": {}})
        assert resp.get_json()["success"] is True

    def test_accept_failure(self, client):
        with patch("nordvpn.accept_invitation", return_value=(False, "error")):
            resp = client.post("/api/invitations/accept", json={"email": "sender@example.com", "permissions": {}})
        assert resp.get_json()["success"] is False

    def test_email_and_permissions_forwarded(self, client):
        with patch("nordvpn.accept_invitation", return_value=(True, "ok")) as mock_fn:
            client.post(
                "/api/invitations/accept",
                json={"email": "sender@example.com", "permissions": {"incoming": True}}
            )
        mock_fn.assert_called_once_with("sender@example.com", {"incoming": True})

    def test_empty_permissions_forwarded(self, client):
        """Empty permissions {} must be forwarded as-is, not defaulted."""
        with patch("nordvpn.accept_invitation", return_value=(True, "ok")) as mock_fn:
            client.post("/api/invitations/accept", json={"email": "sender@example.com", "permissions": {}})
        mock_fn.assert_called_once_with("sender@example.com", {})


# ---------------------------------------------------------------------------
# POST /api/invitations/deny
# ---------------------------------------------------------------------------

class TestAPIDenyInvitation:
    def test_deny_success(self, client):
        with patch("nordvpn.deny_invitation", return_value=(True, "Denied.")):
            resp = client.post("/api/invitations/deny", json={"email": "sender@example.com"})
        assert resp.get_json()["success"] is True

    def test_deny_failure(self, client):
        with patch("nordvpn.deny_invitation", return_value=(False, "error")):
            resp = client.post("/api/invitations/deny", json={"email": "sender@example.com"})
        assert resp.get_json()["success"] is False

    def test_email_forwarded(self, client):
        with patch("nordvpn.deny_invitation", return_value=(True, "ok")) as mock_fn:
            client.post("/api/invitations/deny", json={"email": "sender@example.com"})
        mock_fn.assert_called_once_with("sender@example.com")


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
