"""Unit tests for low-level nordvpn.py helpers: _run, _strip_ansi, _needs_user_input, _extract_login_url."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

import nordvpn


# ---------------------------------------------------------------------------
# _run
# ---------------------------------------------------------------------------

class TestRun:
    def test_success(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
            code, out, err = nordvpn._run(["nordvpn", "version"])
        assert code == 0
        assert out == "ok"
        assert err == ""

    def test_nonzero_returncode(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error msg")
            code, out, err = nordvpn._run(["nordvpn", "bad-cmd"])
        assert code == 1
        assert err == "error msg"

    def test_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["x"], timeout=5)):
            code, out, err = nordvpn._run(["nordvpn", "slow"], timeout=5)
        assert code == 1
        assert "timed out" in err

    def test_command_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            code, out, err = nordvpn._run(["nordvpn"])
        assert code == 127
        assert "not found" in err


# ---------------------------------------------------------------------------
# _strip_ansi
# ---------------------------------------------------------------------------

class TestStripAnsi:
    def test_no_ansi(self):
        assert nordvpn._strip_ansi("hello world") == "hello world"

    def test_bold(self):
        assert nordvpn._strip_ansi("\x1b[1mhello\x1b[0m") == "hello"

    def test_color(self):
        assert nordvpn._strip_ansi("\x1b[32mgreen\x1b[0m") == "green"

    def test_multiple_codes(self):
        assert nordvpn._strip_ansi("\x1b[1m\x1b[32mtext\x1b[0m") == "text"

    def test_empty_string(self):
        assert nordvpn._strip_ansi("") == ""


# ---------------------------------------------------------------------------
# _needs_user_input
# ---------------------------------------------------------------------------

class TestNeedsUserInput:
    def test_yn_prompt(self):
        assert nordvpn._needs_user_input("Do you agree? (y/n)") is True

    def test_yes_no_prompt(self):
        assert nordvpn._needs_user_input("Continue? (yes/no)") is True

    def test_press_y(self):
        assert nordvpn._needs_user_input('Press "y" (yes) to allow.') is True

    def test_no_prompt(self):
        assert nordvpn._needs_user_input("Open this URL to login.") is False

    def test_url_only(self):
        assert nordvpn._needs_user_input("https://api.nordvpn.com/login") is False

    def test_case_insensitive(self):
        assert nordvpn._needs_user_input("AGREE? (Y/N)") is True

    def test_ansi_stripped_before_check(self):
        # ANSI bold wrapping the (y/n) must not break detection
        assert nordvpn._needs_user_input("Agree? \x1b[1m(y/n)\x1b[0m") is True

    def test_full_nordvpn_privacy_prompt(self):
        prompt = (
            "We value your privacy.\n\n"
            "By pressing \"y\" (yes), you allow us to collect data.\n"
            "https://my.nordaccount.com/legal/privacy-policy/\n\n"
            "Do you allow us to collect and use limited app performance data? (y/n)"
        )
        assert nordvpn._needs_user_input(prompt) is True


# ---------------------------------------------------------------------------
# _extract_login_url
# ---------------------------------------------------------------------------

class TestExtractLoginUrl:
    def test_url_after_open(self):
        url = "https://api.nordvpn.com/v1/users/oauth/login-redirect?attempt=abc"
        ok, msg = nordvpn._extract_login_url(f"Open this URL: {url}")
        assert ok is True
        assert msg == url

    def test_url_after_browser(self):
        url = "https://api.nordvpn.com/v1/oauth"
        ok, msg = nordvpn._extract_login_url(f"Open in your browser: {url}")
        assert ok is True
        assert msg == url

    def test_url_after_link(self):
        url = "https://api.nordvpn.com/login"
        ok, msg = nordvpn._extract_login_url(f"Use this link: {url}")
        assert ok is True
        assert msg == url

    def test_already_logged_in(self):
        ok, msg = nordvpn._extract_login_url("You are already logged in.")
        assert ok is True
        assert "already logged in" in msg.lower()

    def test_privacy_url_filtered(self):
        ok, _ = nordvpn._extract_login_url(
            "Read our policy: https://my.nordaccount.com/legal/privacy-policy/"
        )
        assert ok is False

    def test_terms_url_filtered(self):
        ok, _ = nordvpn._extract_login_url("See https://nordvpn.com/terms-of-service")
        assert ok is False

    def test_no_url_returns_false(self):
        ok, _ = nordvpn._extract_login_url("Some error occurred.")
        assert ok is False

    def test_empty_returns_failure_message(self):
        ok, msg = nordvpn._extract_login_url("")
        assert ok is False
        assert msg  # non-empty fallback message
