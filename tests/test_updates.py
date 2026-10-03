"""Unit tests for nordvpn.py update functionality: _parse_version, get_current_version, get_latest_version, check_update, perform_update."""

from unittest.mock import patch

import pytest

import nordvpn


# ---------------------------------------------------------------------------
# _parse_version
# ---------------------------------------------------------------------------

class TestParseVersion:
    def test_v_prefix(self):
        assert nordvpn._parse_version("v1.2.3") == (1, 2, 3)

    def test_no_prefix(self):
        assert nordvpn._parse_version("2.0.0") == (2, 0, 0)

    def test_single_digit(self):
        assert nordvpn._parse_version("v3") == (3,)

    def test_dash_suffix_ignored(self):
        assert nordvpn._parse_version("v1.2.3-beta") == (1, 2, 3)

    def test_ordering(self):
        assert nordvpn._parse_version("v1.10.0") > nordvpn._parse_version("v1.9.0")

    def test_unknown_string(self):
        assert nordvpn._parse_version("unknown") == (0,)

    def test_empty_string(self):
        assert nordvpn._parse_version("") == (0,)


# ---------------------------------------------------------------------------
# get_current_version
# ---------------------------------------------------------------------------

class TestGetCurrentVersion:
    def test_returns_tag(self):
        with patch("nordvpn._run", return_value=(0, "v1.2.3", "")):
            assert nordvpn.get_current_version() == "v1.2.3"

    def test_strips_whitespace(self):
        with patch("nordvpn._run", return_value=(0, "  v1.0.0\n", "")):
            assert nordvpn.get_current_version() == "v1.0.0"

    def test_no_tags_returns_unknown(self):
        with patch("nordvpn._run", return_value=(1, "", "fatal: No names found")):
            assert nordvpn.get_current_version() == "unknown"


# ---------------------------------------------------------------------------
# get_latest_version
# ---------------------------------------------------------------------------

class TestGetLatestVersion:
    def test_returns_highest_tag(self):
        remote = (
            "abc\trefs/tags/v1.0.0\n"
            "def\trefs/tags/v1.2.0\n"
            "ghi\trefs/tags/v1.1.0\n"
        )
        with patch("nordvpn._run", return_value=(0, remote, "")):
            assert nordvpn.get_latest_version() == "v1.2.0"

    def test_skips_annotated_tag_derefs(self):
        remote = "abc\trefs/tags/v1.0.0\nabc\trefs/tags/v1.0.0^{}\n"
        with patch("nordvpn._run", return_value=(0, remote, "")):
            assert nordvpn.get_latest_version() == "v1.0.0"

    def test_empty_on_error(self):
        with patch("nordvpn._run", return_value=(1, "", "error")):
            assert nordvpn.get_latest_version() == ""

    def test_empty_on_no_output(self):
        with patch("nordvpn._run", return_value=(0, "", "")):
            assert nordvpn.get_latest_version() == ""


# ---------------------------------------------------------------------------
# check_update
# ---------------------------------------------------------------------------

class TestCheckUpdate:
    def test_update_available(self):
        with patch("nordvpn.get_current_version", return_value="v1.0.0"), \
             patch("nordvpn.get_latest_version", return_value="v1.2.0"):
            result = nordvpn.check_update()
        assert result["update_available"] is True
        assert result["current"] == "v1.0.0"
        assert result["latest"] == "v1.2.0"

    def test_on_latest_no_update(self):
        with patch("nordvpn.get_current_version", return_value="v1.2.0"), \
             patch("nordvpn.get_latest_version", return_value="v1.2.0"):
            assert nordvpn.check_update()["update_available"] is False

    def test_unknown_current_no_update(self):
        with patch("nordvpn.get_current_version", return_value="unknown"), \
             patch("nordvpn.get_latest_version", return_value="v1.2.0"):
            assert nordvpn.check_update()["update_available"] is False

    def test_no_latest_no_update(self):
        with patch("nordvpn.get_current_version", return_value="v1.0.0"), \
             patch("nordvpn.get_latest_version", return_value=""):
            assert nordvpn.check_update()["update_available"] is False


# ---------------------------------------------------------------------------
# perform_update
# ---------------------------------------------------------------------------

class TestPerformUpdate:
    def test_success_starts_restart_thread(self):
        import threading as _threading

        with patch("nordvpn._run", return_value=(0, "ok", "")), \
             patch("shutil.which", return_value="/usr/bin/uv"), \
             patch.object(_threading, "Thread") as mock_thread:
            ok, msg = nordvpn.perform_update()

        assert ok is True
        assert "update applied" in msg.lower()
        mock_thread.assert_called_once()

    def test_git_pull_failure(self):
        with patch("nordvpn._run", return_value=(1, "", "fatal: not a git repo")):
            ok, msg = nordvpn.perform_update()
        assert ok is False
        assert "git pull failed" in msg.lower()

    def test_uv_sync_failure(self):
        call_count = 0

        def fake_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # git pull
                return (0, "Already up to date.", "")
            return (1, "", "uv sync failed")

        with patch("nordvpn._run", side_effect=fake_run), \
             patch("shutil.which", return_value="/usr/bin/uv"):
            ok, msg = nordvpn.perform_update()
        assert ok is False
        assert "uv sync" in msg.lower()
