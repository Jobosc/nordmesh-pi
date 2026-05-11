"""Unit tests for app.py meshnet and peer management routes: POST /api/meshnet/enable, POST /api/meshnet/disable, GET /api/peers, POST /api/peers/<peer>/permissions, POST /api/peers/<peer>/nickname, POST /api/peers/<peer>/remove."""

from unittest.mock import patch

import pytest

import app as flask_app


@pytest.fixture
def client():
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


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

    def test_set_nickname_failure(self, client):
        with patch("nordvpn.set_nickname", return_value=(False, "error")):
            resp = client.post("/api/peers/peer.nord/nickname", json={"nickname": "bad"})
        assert resp.get_json()["success"] is False


# ---------------------------------------------------------------------------
# POST /api/peers/<peer>/remove
# ---------------------------------------------------------------------------

class TestAPIRemovePeer:
    def test_remove_success(self, client):
        with patch("nordvpn.remove_peer", return_value=(True, "Removed.")):
            resp = client.post("/api/peers/peer.nord/remove")
        assert resp.get_json()["success"] is True

    def test_peer_passed_to_function(self, client):
        with patch("nordvpn.remove_peer", return_value=(True, "ok")) as mock_fn:
            client.post("/api/peers/some.device.nord/remove")
        mock_fn.assert_called_once_with("some.device.nord")

    def test_remove_failure(self, client):
        with patch("nordvpn.remove_peer", return_value=(False, "error")):
            resp = client.post("/api/peers/peer.nord/remove")
        assert resp.get_json()["success"] is False
