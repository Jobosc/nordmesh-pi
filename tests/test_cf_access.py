"""Unit tests for cf_access.py: Cloudflare Access JWT enforcement at the origin."""

import time
from unittest.mock import patch

import pytest

import app as flask_app
import cf_access


@pytest.fixture
def client():
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c


@pytest.fixture
def enforcing(client):
    """A client with Access enforcement switched on.

    JWT_AVAILABLE is forced on so these tests exercise the enforcement logic
    whether or not the optional `cloudflare` extra is installed.
    """
    app = flask_app.app
    saved = {k: app.config.get(k) for k in
             ("CF_ACCESS_ENABLED", "CF_ACCESS_TEAM_DOMAIN", "CF_ACCESS_AUD", "CF_ACCESS_ALLOW_LOCAL")}
    app.config.update(
        CF_ACCESS_ENABLED=True,
        CF_ACCESS_TEAM_DOMAIN="myteam.cloudflareaccess.com",
        CF_ACCESS_AUD="aud-tag",
        CF_ACCESS_ALLOW_LOCAL=True,
    )
    with patch("cf_access.JWT_AVAILABLE", True):
        yield client
    app.config.update(saved)


CF_HEADERS = {"CF-Ray": "8abc123def456-FRA"}


# ---------------------------------------------------------------------------
# normalize_team_domain
# ---------------------------------------------------------------------------

class TestNormalizeTeamDomain:
    def test_bare_team_name_gets_suffix(self):
        assert cf_access.normalize_team_domain("myteam") == "myteam.cloudflareaccess.com"

    def test_full_domain_unchanged(self):
        assert cf_access.normalize_team_domain("myteam.cloudflareaccess.com") == "myteam.cloudflareaccess.com"

    def test_strips_scheme_and_trailing_slash(self):
        assert cf_access.normalize_team_domain("https://myteam.cloudflareaccess.com/") == "myteam.cloudflareaccess.com"

    def test_custom_domain_kept(self):
        assert cf_access.normalize_team_domain("auth.example.com") == "auth.example.com"

    def test_empty(self):
        assert cf_access.normalize_team_domain("  ") == ""


# ---------------------------------------------------------------------------
# Enforcement
# ---------------------------------------------------------------------------

class TestEnforcement:
    def test_disabled_by_default(self, client):
        """Without CF_ACCESS_* configured the app must behave exactly as before."""
        with patch("nordvpn.get_status", return_value={"installed": False}):
            resp = client.get("/api/status", headers=CF_HEADERS)
        assert resp.status_code == 200

    def test_local_request_allowed(self, enforcing):
        """No CF-Ray means LAN/localhost traffic — e.g. the Docker healthcheck."""
        with patch("nordvpn.get_status", return_value={"installed": False}):
            resp = enforcing.get("/api/status")
        assert resp.status_code == 200

    def test_local_request_blocked_when_not_allowed(self, enforcing):
        flask_app.app.config["CF_ACCESS_ALLOW_LOCAL"] = False
        resp = enforcing.get("/api/status")
        assert resp.status_code == 403

    def test_cloudflare_request_without_token_rejected(self, enforcing):
        resp = enforcing.get("/api/status", headers=CF_HEADERS)
        assert resp.status_code == 401
        assert "Missing" in resp.get_json()["error"]

    def test_cloudflare_request_with_invalid_token_rejected(self, enforcing):
        with patch("cf_access.verify_token", side_effect=Exception("bad signature")):
            resp = enforcing.get(
                "/api/status",
                headers={**CF_HEADERS, "Cf-Access-Jwt-Assertion": "garbage"},
            )
        assert resp.status_code == 401
        assert "Invalid" in resp.get_json()["error"]

    def test_cloudflare_request_with_valid_token_allowed(self, enforcing):
        with patch("cf_access.verify_token", return_value={"email": "user@example.com"}), \
             patch("nordvpn.get_status", return_value={"installed": False}):
            resp = enforcing.get(
                "/api/status",
                headers={**CF_HEADERS, "Cf-Access-Jwt-Assertion": "good-token"},
            )
        assert resp.status_code == 200

    def test_token_accepted_from_cookie(self, enforcing):
        """Browsers send the Access session as a cookie, not a header."""
        enforcing.set_cookie("CF_Authorization", "good-token", domain="localhost")
        with patch("cf_access.verify_token", return_value={"email": "user@example.com"}) as verify, \
             patch("nordvpn.get_status", return_value={"installed": False}):
            resp = enforcing.get("/api/status", headers=CF_HEADERS)
        assert resp.status_code == 200
        verify.assert_called_once()
        assert verify.call_args[0][0] == "good-token"

    def test_token_verified_against_configured_team_and_aud(self, enforcing):
        with patch("cf_access.verify_token", return_value={}) as verify, \
             patch("nordvpn.get_status", return_value={"installed": False}):
            enforcing.get("/api/status", headers={**CF_HEADERS, "Cf-Access-Jwt-Assertion": "t"})
        verify.assert_called_once_with("t", "myteam.cloudflareaccess.com", "aud-tag")

    def test_fails_closed_without_pyjwt(self, enforcing):
        """Serving unauthenticated is worse than serving nothing."""
        with patch("cf_access.JWT_AVAILABLE", False):
            resp = enforcing.get(
                "/api/status",
                headers={**CF_HEADERS, "Cf-Access-Jwt-Assertion": "good-token"},
            )
        assert resp.status_code == 503

    def test_index_is_protected_too(self, enforcing):
        """The dashboard itself must not render for unauthenticated visitors."""
        resp = enforcing.get("/", headers=CF_HEADERS)
        assert resp.status_code == 401

    def test_write_endpoints_are_protected(self, enforcing):
        with patch("nordvpn.perform_update") as update:
            resp = enforcing.post("/api/update", headers=CF_HEADERS)
        assert resp.status_code == 401
        update.assert_not_called()


# ---------------------------------------------------------------------------
# Real signature verification (needs the optional `cloudflare` extra)
# ---------------------------------------------------------------------------

class TestVerifyToken:
    """Exercise the real crypto path, not a mock of it."""

    @pytest.fixture
    def rsa_key(self):
        pytest.importorskip("jwt", reason="requires: uv sync --extra cloudflare")
        crypto = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.rsa")
        return crypto.generate_private_key(public_exponent=65537, key_size=2048)

    @pytest.fixture
    def issue(self, rsa_key):
        """Return a factory that mints signed tokens and stubs out JWKS lookup."""
        import jwt as pyjwt

        class _Key:
            key = rsa_key.public_key()

        class _Client:
            def get_signing_key_from_jwt(self, token):
                return _Key()

        def _issue(**claims):
            payload = {
                "aud": "aud-tag",
                "iss": "https://myteam.cloudflareaccess.com",
                "email": "user@example.com",
                "exp": int(time.time()) + 300,
                "iat": int(time.time()),
            }
            payload.update(claims)
            return pyjwt.encode(payload, rsa_key, algorithm="RS256")

        with patch("cf_access._jwk_client", return_value=_Client()):
            yield _issue

    def test_valid_token_returns_claims(self, issue):
        claims = cf_access.verify_token(issue(), "myteam.cloudflareaccess.com", "aud-tag")
        assert claims["email"] == "user@example.com"

    def test_wrong_audience_rejected(self, issue):
        """An Access token for a different app must not unlock this one."""
        token = issue(aud="someone-elses-app")
        with pytest.raises(Exception):
            cf_access.verify_token(token, "myteam.cloudflareaccess.com", "aud-tag")

    def test_wrong_issuer_rejected(self, issue):
        token = issue(iss="https://attacker.cloudflareaccess.com")
        with pytest.raises(Exception):
            cf_access.verify_token(token, "myteam.cloudflareaccess.com", "aud-tag")

    def test_expired_token_rejected(self, issue):
        token = issue(exp=int(time.time()) - 60)
        with pytest.raises(Exception):
            cf_access.verify_token(token, "myteam.cloudflareaccess.com", "aud-tag")

    def test_token_signed_by_another_key_rejected(self, issue, rsa_key):
        """The signature must actually be checked, not just parsed."""
        import jwt as pyjwt
        from cryptography.hazmat.primitives.asymmetric import rsa

        attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        forged = pyjwt.encode(
            {
                "aud": "aud-tag",
                "iss": "https://myteam.cloudflareaccess.com",
                "email": "attacker@example.com",
                "exp": int(time.time()) + 300,
            },
            attacker_key,
            algorithm="RS256",
        )
        with pytest.raises(Exception):
            cf_access.verify_token(forged, "myteam.cloudflareaccess.com", "aud-tag")


# ---------------------------------------------------------------------------
# init_app configuration
# ---------------------------------------------------------------------------

class TestInitApp:
    def _fresh_app(self):
        from flask import Flask
        return Flask(__name__)

    def test_enabled_when_both_vars_set(self):
        app = self._fresh_app()
        with patch.dict("os.environ", {"CF_ACCESS_TEAM_DOMAIN": "myteam", "CF_ACCESS_AUD": "tag"}):
            cf_access.init_app(app)
        assert app.config["CF_ACCESS_ENABLED"] is True
        assert app.config["CF_ACCESS_TEAM_DOMAIN"] == "myteam.cloudflareaccess.com"

    def test_disabled_when_aud_missing(self):
        app = self._fresh_app()
        with patch.dict("os.environ", {"CF_ACCESS_TEAM_DOMAIN": "myteam"}, clear=True):
            cf_access.init_app(app)
        assert app.config["CF_ACCESS_ENABLED"] is False

    def test_disabled_when_nothing_set(self):
        app = self._fresh_app()
        with patch.dict("os.environ", {}, clear=True):
            cf_access.init_app(app)
        assert app.config["CF_ACCESS_ENABLED"] is False

    def test_allow_local_defaults_true(self):
        app = self._fresh_app()
        with patch.dict("os.environ", {}, clear=True):
            cf_access.init_app(app)
        assert app.config["CF_ACCESS_ALLOW_LOCAL"] is True

    def test_allow_local_can_be_disabled(self):
        app = self._fresh_app()
        with patch.dict("os.environ", {"CF_ACCESS_ALLOW_LOCAL": "false"}, clear=True):
            cf_access.init_app(app)
        assert app.config["CF_ACCESS_ALLOW_LOCAL"] is False
