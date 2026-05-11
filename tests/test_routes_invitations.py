"""Unit tests for app.py invitation routes: GET /api/invitations, POST /api/invitations/send, POST /api/invitations/revoke, POST /api/invitations/accept, POST /api/invitations/deny."""

from unittest.mock import patch

import pytest

import app as flask_app


@pytest.fixture
def client():
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


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

    def test_send_failure(self, client):
        with patch("nordvpn.send_invitation", return_value=(False, "error")):
            resp = client.post("/api/invitations/send", json={"email": "user@example.com", "permissions": {}})
        assert resp.get_json()["success"] is False


# ---------------------------------------------------------------------------
# POST /api/invitations/revoke
# ---------------------------------------------------------------------------

class TestAPIRevokeInvitation:
    def test_revoke_success(self, client):
        with patch("nordvpn.revoke_invitation", return_value=(True, "Revoked.")):
            resp = client.post("/api/invitations/revoke", json={"email": "user@example.com"})
        assert resp.get_json()["success"] is True

    def test_email_forwarded(self, client):
        with patch("nordvpn.revoke_invitation", return_value=(True, "ok")) as mock_fn:
            client.post("/api/invitations/revoke", json={"email": "user@example.com"})
        mock_fn.assert_called_once_with("user@example.com")

    def test_revoke_failure(self, client):
        with patch("nordvpn.revoke_invitation", return_value=(False, "error")):
            resp = client.post("/api/invitations/revoke", json={"email": "user@example.com"})
        assert resp.get_json()["success"] is False


# ---------------------------------------------------------------------------
# POST /api/invitations/accept
# ---------------------------------------------------------------------------

class TestAPIAcceptInvitation:
    def test_accept_success(self, client):
        with patch("nordvpn.accept_invitation", return_value=(True, "Accepted.")):
            resp = client.post("/api/invitations/accept", json={"email": "sender@example.com", "permissions": {}})
        assert resp.get_json()["success"] is True

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

    def test_accept_failure(self, client):
        with patch("nordvpn.accept_invitation", return_value=(False, "error")):
            resp = client.post("/api/invitations/accept", json={"email": "sender@example.com", "permissions": {}})
        assert resp.get_json()["success"] is False


# ---------------------------------------------------------------------------
# POST /api/invitations/deny
# ---------------------------------------------------------------------------

class TestAPIDenyInvitation:
    def test_deny_success(self, client):
        with patch("nordvpn.deny_invitation", return_value=(True, "Denied.")):
            resp = client.post("/api/invitations/deny", json={"email": "sender@example.com"})
        assert resp.get_json()["success"] is True

    def test_email_forwarded(self, client):
        with patch("nordvpn.deny_invitation", return_value=(True, "ok")) as mock_fn:
            client.post("/api/invitations/deny", json={"email": "sender@example.com"})
        mock_fn.assert_called_once_with("sender@example.com")

    def test_deny_failure(self, client):
        with patch("nordvpn.deny_invitation", return_value=(False, "error")):
            resp = client.post("/api/invitations/deny", json={"email": "sender@example.com"})
        assert resp.get_json()["success"] is False
