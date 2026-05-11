"""Unit tests for nordvpn.py login-related functions: login (detection run + user_input path), login_with_token, logout."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

import nordvpn


def _mock_login_proc(stdout_data: bytes, returncode: int | None):
    """Build a minimal Popen mock for login() tests."""
    proc = MagicMock()
    proc.stdout.fileno.return_value = 5
    proc.returncode = returncode
    proc.poll.return_value = returncode
    return proc, stdout_data


# ---------------------------------------------------------------------------
# login — URL in various output positions
# ---------------------------------------------------------------------------

class TestLoginLegacy:
    def test_returns_url_in_stdout(self):
        url = "https://api.nordvpn.com/v1/users/oauth/login-redirect?attempt=abc"
        proc, data = _mock_login_proc(f"Open this URL: {url}".encode(), returncode=None)
        with patch("subprocess.Popen", return_value=proc), \
             patch("select.select", return_value=([proc.stdout], [], [])), \
             patch("os.read", side_effect=[data, b""]):
            ok, msg = nordvpn.login()
        assert ok is True
        assert msg == url

    def test_returns_url_after_visit_prefix(self):
        url = "https://api.nordvpn.com/v1/users/oauth/login-redirect?attempt=xyz"
        proc, data = _mock_login_proc(f"Visit: {url}".encode(), returncode=None)
        with patch("subprocess.Popen", return_value=proc), \
             patch("select.select", return_value=([proc.stdout], [], [])), \
             patch("os.read", side_effect=[data, b""]):
            ok, msg = nordvpn.login()
        assert ok is True
        assert msg == url

    def test_no_url_failure(self):
        with patch("subprocess.Popen", side_effect=FileNotFoundError):
            ok, msg = nordvpn.login()
        assert ok is False


# ---------------------------------------------------------------------------
# login — detection run (user_input=None)
# ---------------------------------------------------------------------------

class TestLogin:
    def test_detection_url_found_process_running(self):
        url = "https://api.nordvpn.com/v1/users/oauth/login-redirect?attempt=abc"
        proc, data = _mock_login_proc(f"Open this URL: {url}".encode(), returncode=None)
        with patch("subprocess.Popen", return_value=proc), \
             patch("select.select", return_value=([proc.stdout], [], [])), \
             patch("os.read", side_effect=[data, b""]):
            ok, msg = nordvpn.login()
        assert ok is True
        assert msg == url

    def test_detection_already_logged_in(self):
        proc, _ = _mock_login_proc(b"", returncode=0)
        with patch("subprocess.Popen", return_value=proc), \
             patch("select.select", return_value=([proc.stdout], [], [])), \
             patch("os.read", side_effect=[b"You are already logged in.", b""]):
            ok, msg = nordvpn.login()
        assert ok is True
        assert "already logged in" in msg.lower()

    def test_detection_consent_prompt_process_running(self):
        prompt = b"We value your privacy. Do you agree? (y/n)"
        proc, _ = _mock_login_proc(b"", returncode=None)
        with patch("subprocess.Popen", return_value=proc), \
             patch("select.select", return_value=([proc.stdout], [], [])), \
             patch("os.read", side_effect=[prompt, b""]):
            ok, msg = nordvpn.login()
        assert ok is False
        assert msg.startswith("NEEDS_INPUT:")
        assert "y/n" in msg

    def test_detection_consent_prompt_process_exited(self):
        # nordvpn may exit immediately (no tty in Docker) after printing the prompt
        prompt = b"We value your privacy. Do you agree? (y/n)"
        proc, _ = _mock_login_proc(b"", returncode=1)
        with patch("subprocess.Popen", return_value=proc), \
             patch("select.select", return_value=([proc.stdout], [], [])), \
             patch("os.read", side_effect=[prompt, b""]):
            ok, msg = nordvpn.login()
        assert ok is False
        assert msg.startswith("NEEDS_INPUT:")

    def test_detection_privacy_url_does_not_short_circuit(self):
        """The privacy-policy URL inside the consent text must not be returned as the login URL."""
        privacy_url = b"https://my.nordaccount.com/legal/privacy-policy/"
        prompt = b"We value your privacy. See " + privacy_url + b" (y/n)"
        proc, _ = _mock_login_proc(b"", returncode=1)
        with patch("subprocess.Popen", return_value=proc), \
             patch("select.select", return_value=([proc.stdout], [], [])), \
             patch("os.read", side_effect=[prompt, b""]):
            ok, msg = nordvpn.login()
        assert ok is False
        assert msg.startswith("NEEDS_INPUT:")

    def test_detection_ansi_stripped_from_output(self):
        prompt = b"\x1b[1mWe value your privacy.\x1b[0m (y/n)"
        proc, _ = _mock_login_proc(b"", returncode=1)
        with patch("subprocess.Popen", return_value=proc), \
             patch("select.select", return_value=([proc.stdout], [], [])), \
             patch("os.read", side_effect=[prompt, b""]):
            ok, msg = nordvpn.login()
        assert ok is False
        assert "\x1b" not in msg

    def test_detection_nordvpn_not_found(self):
        with patch("subprocess.Popen", side_effect=FileNotFoundError):
            ok, msg = nordvpn.login()
        assert ok is False
        assert "not found" in msg.lower()

    # --- user_input path ---

    def test_user_input_sends_answer_and_returns_url(self):
        url = "https://api.nordvpn.com/v1/users/oauth/login-redirect?attempt=abc"
        proc = MagicMock()
        proc.communicate.return_value = (f"Open this URL: {url}", "")
        with patch("subprocess.Popen", return_value=proc):
            ok, msg = nordvpn.login(user_input="y")
        assert ok is True
        assert msg == url
        proc.communicate.assert_called_once_with(input="y\n", timeout=15)

    def test_user_input_n_works_too(self):
        url = "https://api.nordvpn.com/v1/users/oauth/login-redirect?attempt=abc"
        proc = MagicMock()
        proc.communicate.return_value = (f"Open this URL: {url}", "")
        with patch("subprocess.Popen", return_value=proc):
            ok, msg = nordvpn.login(user_input="n")
        assert ok is True
        proc.communicate.assert_called_once_with(input="n\n", timeout=15)

    def test_user_input_timeout_kills_and_extracts(self):
        url = "https://api.nordvpn.com/v1/users/oauth/login-redirect?attempt=abc"
        proc = MagicMock()
        proc.communicate.side_effect = [
            subprocess.TimeoutExpired("nordvpn", 15),
            (f"Open this URL: {url}", ""),
        ]
        with patch("subprocess.Popen", return_value=proc):
            ok, msg = nordvpn.login(user_input="y")
        assert ok is True
        assert msg == url
        proc.kill.assert_called_once()

    def test_user_input_nordvpn_not_found(self):
        with patch("subprocess.Popen", side_effect=FileNotFoundError):
            ok, msg = nordvpn.login(user_input="y")
        assert ok is False
        assert "not found" in msg.lower()


# ---------------------------------------------------------------------------
# login_with_token
# ---------------------------------------------------------------------------

class TestLoginWithToken:
    def test_success_code_zero(self):
        with patch("nordvpn._run", return_value=(0, "Welcome to NordVPN!", "")):
            ok, msg = nordvpn.login_with_token("mytoken")
        assert ok is True

    def test_success_welcome_message(self):
        with patch("nordvpn._run", return_value=(1, "Welcome, user!", "")):
            ok, msg = nordvpn.login_with_token("mytoken")
        assert ok is True

    def test_already_logged_in(self):
        with patch("nordvpn._run", return_value=(1, "Already logged in.", "")):
            ok, msg = nordvpn.login_with_token("mytoken")
        assert ok is True

    def test_token_is_passed_to_command(self):
        with patch("nordvpn._run", return_value=(0, "", "")) as mock_run:
            nordvpn.login_with_token("secret123")
        cmd = mock_run.call_args[0][0]
        assert "--token" in cmd
        assert "secret123" in cmd

    def test_failure(self):
        with patch("nordvpn._run", return_value=(1, "Invalid token.", "")):
            ok, msg = nordvpn.login_with_token("badtoken")
        assert ok is False


# ---------------------------------------------------------------------------
# logout
# ---------------------------------------------------------------------------

class TestLogout:
    def test_success(self):
        with patch("nordvpn._run", return_value=(0, "You have been logged out.", "")):
            ok, msg = nordvpn.logout()
        assert ok is True

    def test_failure(self):
        with patch("nordvpn._run", return_value=(1, "", "Not logged in.")):
            ok, msg = nordvpn.logout()
        assert ok is False
