"""Unit tests for connection_log.py and GET /api/connections."""

from unittest.mock import patch

import pytest

import app as flask_app
import connection_log


def peer(hostname, status="connected", **extra):
    return {"hostname": hostname, "status": status, **extra}


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "connection_log.json")


def seed(path, *peers):
    """Do a first run so later calls have something to compare against."""
    connection_log.record(list(peers), path=path, now="2026-01-01T00:00:00+00:00")


class TestRecord:
    def test_first_run_logs_nothing(self, path):
        """Peers already online at install time didn't just connect."""
        assert connection_log.record([peer("phone.nord")], path=path) == []
        assert connection_log.entries(path)[0]["connections"] == []

    def test_logs_disconnected_to_connected(self, path):
        seed(path, peer("phone.nord", "disconnected"))
        assert connection_log.record([peer("phone.nord")], path=path, now="T1") == ["phone.nord"]
        assert connection_log.entries(path)[0]["connections"] == ["T1"]

    def test_staying_connected_is_not_a_new_connection(self, path):
        seed(path, peer("phone.nord", "disconnected"))
        connection_log.record([peer("phone.nord")], path=path, now="T1")
        assert connection_log.record([peer("phone.nord")], path=path, now="T2") == []
        assert connection_log.entries(path)[0]["connections"] == ["T1"]

    def test_new_peer_coming_online_is_logged(self, path):
        seed(path)
        assert connection_log.record([peer("laptop.nord")], path=path, now="T1") == ["laptop.nord"]

    def test_keeps_only_last_five_newest_first(self, path):
        seed(path, peer("phone.nord", "disconnected"))
        for i in range(7):
            connection_log.record([peer("phone.nord")], path=path, now=f"T{i}")
            connection_log.record([peer("phone.nord", "disconnected")], path=path)
        assert connection_log.entries(path)[0]["connections"] == ["T6", "T5", "T4", "T3", "T2"]

    def test_ignores_this_device(self, path):
        seed(path)
        connection_log.record([peer("pi.nord", is_self=True)], path=path)
        assert connection_log.entries(path) == []

    def test_missing_peer_counts_as_disconnected(self, path):
        """Meshnet off or peer removed — its next appearance is a new connection."""
        seed(path, peer("phone.nord"))
        connection_log.record([], path=path)
        assert connection_log.entries(path)[0]["status"] == "disconnected"
        assert connection_log.record([peer("phone.nord")], path=path, now="T1") == ["phone.nord"]

    def test_stores_peer_details(self, path):
        seed(path)
        connection_log.record([peer("phone.nord", nickname="Phone", ip="100.64.0.2", os="android")], path=path)
        device = connection_log.entries(path)[0]
        assert (device["nickname"], device["ip"], device["os"]) == ("Phone", "100.64.0.2", "android")

    def test_survives_corrupt_file(self, path):
        with open(path, "w") as f:
            f.write("{not json")
        assert connection_log.record([peer("phone.nord")], path=path) == []
        assert connection_log.entries(path)[0]["hostname"] == "phone.nord"


class TestEntries:
    def test_empty_when_no_log(self, path):
        assert connection_log.entries(path) == []

    def test_most_recently_connected_first(self, path):
        seed(path, peer("a.nord", "disconnected"), peer("b.nord", "disconnected"), peer("c.nord", "disconnected"))
        connection_log.record([peer("a.nord", "disconnected"), peer("b.nord"), peer("c.nord", "disconnected")],
                              path=path, now="2026-01-02T00:00:00+00:00")
        connection_log.record([peer("a.nord"), peer("b.nord"), peer("c.nord", "disconnected")],
                              path=path, now="2026-01-03T00:00:00+00:00")
        assert [d["hostname"] for d in connection_log.entries(path)] == ["a.nord", "b.nord", "c.nord"]


class TestPollOnce:
    def test_daemon_failure_keeps_state(self, path):
        """A failed CLI call must not look like every peer disconnecting."""
        seed(path, peer("phone.nord"))
        with patch("nordvpn.fetch_peers", return_value=None), \
             patch("connection_log.log_path", return_value=path):
            connection_log.poll_once()
        assert connection_log.entries(path)[0]["status"] == "connected"

    def test_records_fetched_peers(self, path):
        seed(path, peer("phone.nord", "disconnected"))
        with patch("nordvpn.fetch_peers", return_value=[peer("phone.nord")]), \
             patch("connection_log.log_path", return_value=path):
            connection_log.poll_once()
        assert len(connection_log.entries(path)[0]["connections"]) == 1


class TestFetchPeers:
    def test_failure_returns_none(self):
        with patch("nordvpn._run", return_value=(1, "", "Cannot reach System Daemon.")):
            assert connection_log.nordvpn.fetch_peers() is None

    def test_meshnet_off_returns_empty(self):
        with patch("nordvpn._run", return_value=(1, "Meshnet is not enabled.", "")):
            assert connection_log.nordvpn.fetch_peers() == []


class TestPollerLock:
    def test_only_one_holder(self, tmp_path):
        """With several gunicorn workers, only one may poll."""
        lock_path = str(tmp_path / "poller.lock")
        first = connection_log._try_lock(lock_path)
        try:
            assert first is not None
            assert connection_log._try_lock(lock_path) is None
        finally:
            first.close()
        second = connection_log._try_lock(lock_path)
        assert second is not None
        second.close()


class TestRoute:
    def test_returns_devices(self, path):
        seed(path, peer("phone.nord", "disconnected"))
        connection_log.record([peer("phone.nord")], path=path, now="T1")
        flask_app.app.config["TESTING"] = True
        with patch("connection_log.log_path", return_value=path), \
             flask_app.app.test_client() as client:
            data = client.get("/api/connections").get_json()
        assert data["devices"][0]["hostname"] == "phone.nord"
        assert data["devices"][0]["connections"] == ["T1"]
        assert data["max_per_device"] == 5
        assert data["interval"] == flask_app.CONNECTION_LOG_INTERVAL_S
