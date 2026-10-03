"""Origin-side verification of Cloudflare Access JWTs.

Cloudflare Access authenticates users at the edge, but the Pi never sees that
unless it checks the signed assertion Cloudflare forwards. Verifying it here
means a request that reaches the app *without* passing Access is rejected
rather than trusted — so a misconfigured tunnel or a stray `HOST=0.0.0.0`
cannot silently expose peer management to the internet.

Enabled only when both CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD are set.
Requires the optional `cloudflare` extra: `uv sync --extra cloudflare`.
"""

import logging
import os

from flask import current_app, g, jsonify, request

log = logging.getLogger(__name__)

try:  # optional dependency — only needed when Access enforcement is on
    import jwt
    from jwt import PyJWKClient
    JWT_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised via monkeypatching
    JWT_AVAILABLE = False

# Cloudflare sets this on every request it proxies and overwrites any
# client-supplied value, so its presence means "arrived through the tunnel".
CLOUDFLARE_MARKER_HEADER = "CF-Ray"

ASSERTION_HEADER = "Cf-Access-Jwt-Assertion"
ASSERTION_COOKIE = "CF_Authorization"

_jwk_clients = {}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


def normalize_team_domain(value: str) -> str:
    """Accept 'myteam', 'myteam.cloudflareaccess.com' or a full URL."""
    domain = value.strip().rstrip("/")
    for prefix in ("https://", "http://"):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    if domain and "." not in domain:
        domain = f"{domain}.cloudflareaccess.com"
    return domain


def init_app(app) -> None:
    """Wire Access enforcement into a Flask app based on the environment."""
    team_domain = normalize_team_domain(os.environ.get("CF_ACCESS_TEAM_DOMAIN", ""))
    aud = os.environ.get("CF_ACCESS_AUD", "").strip()

    app.config.setdefault("CF_ACCESS_TEAM_DOMAIN", team_domain)
    app.config.setdefault("CF_ACCESS_AUD", aud)
    # Requests that did not come through Cloudflare are LAN/localhost traffic
    # (including the Docker healthcheck). Off by default means "LAN still works".
    app.config.setdefault("CF_ACCESS_ALLOW_LOCAL", _env_bool("CF_ACCESS_ALLOW_LOCAL", True))
    app.config.setdefault("CF_ACCESS_ENABLED", bool(team_domain and aud))

    app.before_request(enforce)

    if app.config["CF_ACCESS_ENABLED"]:
        if not JWT_AVAILABLE:
            log.error(
                "CF_ACCESS_TEAM_DOMAIN/CF_ACCESS_AUD are set but PyJWT is missing — "
                "Cloudflare requests will be refused. Install it with: uv sync --extra cloudflare"
            )
        else:
            log.info("Cloudflare Access enforcement enabled for team %s", team_domain)
    else:
        log.info("Cloudflare Access enforcement disabled (CF_ACCESS_TEAM_DOMAIN/CF_ACCESS_AUD unset)")


def _jwk_client(team_domain: str):
    client = _jwk_clients.get(team_domain)
    if client is None:
        client = PyJWKClient(
            f"https://{team_domain}/cdn-cgi/access/certs",
            cache_keys=True,
            lifespan=600,
        )
        _jwk_clients[team_domain] = client
    return client


def verify_token(token: str, team_domain: str, aud: str) -> dict:
    """Verify an Access JWT and return its claims. Raises on any failure."""
    signing_key = _jwk_client(team_domain).get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=aud,
        issuer=f"https://{team_domain}",
    )


def _deny(status: int, message: str):
    response = jsonify({"success": False, "error": message})
    response.status_code = status
    return response


def enforce():
    """before_request hook: reject Cloudflare traffic lacking a valid Access JWT."""
    cfg = current_app.config
    if not cfg.get("CF_ACCESS_ENABLED"):
        return None

    via_cloudflare = CLOUDFLARE_MARKER_HEADER in request.headers
    if not via_cloudflare:
        if cfg.get("CF_ACCESS_ALLOW_LOCAL"):
            return None
        return _deny(403, "Direct access is disabled; reach this app through Cloudflare Access.")

    if not JWT_AVAILABLE:
        # Fail closed: serving unauthenticated is worse than serving nothing.
        return _deny(503, "Cloudflare Access verification unavailable: PyJWT is not installed.")

    token = request.headers.get(ASSERTION_HEADER) or request.cookies.get(ASSERTION_COOKIE)
    if not token:
        return _deny(401, "Missing Cloudflare Access token.")

    try:
        claims = verify_token(token, cfg["CF_ACCESS_TEAM_DOMAIN"], cfg["CF_ACCESS_AUD"])
    except Exception as exc:
        log.warning("Rejected request with invalid Access token: %s", exc)
        return _deny(401, "Invalid Cloudflare Access token.")

    g.cf_access_email = claims.get("email", "")
    return None
