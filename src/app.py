"""Flask web application for NordVPN Meshnet management."""

import logging
import os
import re
from flask import Flask, render_template, request, jsonify
import connection_log
import nordvpn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__, template_folder='../templates')


def _env_int(name: str, default: int, minimum: int) -> int:
    """Read a positive integer from the environment, falling back on junk values."""
    try:
        return max(minimum, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        log.warning("%s is not an integer — using default %d", name, default)
        return default


# How often the UI retries reaching the NordVPN daemon before showing the
# "can't connect" error screen, and how long it waits between tries.
CONNECT_ATTEMPTS = _env_int("NORDVPN_CONNECT_ATTEMPTS", 5, 1)
CONNECT_RETRY_DELAY_MS = _env_int("NORDVPN_CONNECT_RETRY_DELAY_MS", 3000, 250)

# Which origins may embed the UI in an iframe. Default "*" keeps the Home
# Assistant panel working from any HA URL; narrow it to your HA origin
# (e.g. "https://ha.example.com") once you know it.
FRAME_ANCESTORS = os.environ.get("ALLOWED_FRAME_ANCESTORS", "*").strip() or "*"

# Home Assistant ingress (the hass_ingress integration, or add-on ingress) serves
# the UI under a sub-path such as /api/ingress/nordmesh and announces it in this
# header. The frontend prefixes its API calls with it — otherwise "/api/status"
# would hit Home Assistant's own API instead of this app.
_INGRESS_PATH_RE = re.compile(r"^/[A-Za-z0-9_./-]*$")


# How often the connection log checks which peers are online.
CONNECTION_LOG_INTERVAL_S = _env_int("CONNECTION_LOG_INTERVAL_S", 30, 10)
if os.environ.get("NORDMESH_DISABLE_POLLER") != "1":
    connection_log.start_poller(CONNECTION_LOG_INTERVAL_S)


def _ingress_path() -> str:
    path = request.headers.get("X-Ingress-Path", "").rstrip("/")
    return path if _INGRESS_PATH_RE.match(path) else ""


@app.after_request
def set_security_headers(response):
    ancestors = "'none'" if FRAME_ANCESTORS.lower() in ("none", "'none'") else FRAME_ANCESTORS
    response.headers["Content-Security-Policy"] = f"frame-ancestors {ancestors}"
    # X-Frame-Options cannot express an allowlist, and any value other than
    # DENY/SAMEORIGIN is ignored by browsers — so only send it to forbid framing.
    if ancestors == "'none'":
        response.headers["X-Frame-Options"] = "DENY"
    else:
        response.headers.pop("X-Frame-Options", None)
    return response


@app.route("/")
def index():
    status = nordvpn.get_status()
    return render_template(
        "index.html",
        status=status,
        connect_attempts=CONNECT_ATTEMPTS,
        connect_retry_delay_ms=CONNECT_RETRY_DELAY_MS,
        base_path=_ingress_path(),
    )


@app.route("/api/status")
def api_status():
    return jsonify(nordvpn.get_status())


@app.route("/api/install", methods=["POST"])
def api_install():
    ok, msg = nordvpn.install_nordvpn()
    return jsonify({"success": ok, "message": msg})


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True, silent=True) or {}
    token = data.get("token")
    if token:
        ok, msg = nordvpn.login_with_token(token)
        return jsonify({"success": ok, "message": msg})

    user_input = data.get("user_input")  # answer typed by user in the terminal panel
    ok, msg = nordvpn.login(user_input=user_input)

    log.info("api_login: ok=%s needs_input=%s msg_prefix=%r", ok, msg.startswith("NEEDS_INPUT:"), msg[:80])

    if not ok and msg.startswith("NEEDS_INPUT:"):
        return jsonify({"success": False, "needs_input": True, "prompt": msg[len("NEEDS_INPUT:"):]})

    response = {"success": ok, "message": msg}
    if ok and msg.startswith("http"):
        response["url"] = msg
    return jsonify(response)


@app.route("/api/logout", methods=["POST"])
def api_logout():
    ok, msg = nordvpn.logout()
    return jsonify({"success": ok, "message": msg})


@app.route("/api/meshnet/enable", methods=["POST"])
def api_meshnet_enable():
    ok, msg = nordvpn.enable_meshnet()
    return jsonify({"success": ok, "message": msg})


@app.route("/api/meshnet/disable", methods=["POST"])
def api_meshnet_disable():
    ok, msg = nordvpn.disable_meshnet()
    return jsonify({"success": ok, "message": msg})


@app.route("/api/peers")
def api_peers():
    peers = nordvpn.list_peers()
    return jsonify(peers)


@app.route("/api/peers/<path:peer>/permissions", methods=["POST"])
def api_set_permissions(peer):
    perms = request.json
    results = nordvpn.set_all_permissions(peer, perms)
    return jsonify([{"permission": p, "success": s, "message": m} for p, s, m in results])


@app.route("/api/peers/<path:peer>/nickname", methods=["POST"])
def api_set_nickname(peer):
    nickname = request.json.get("nickname", "")
    ok, msg = nordvpn.set_nickname(peer, nickname)
    return jsonify({"success": ok, "message": msg})


@app.route("/api/peers/<path:peer>/remove", methods=["POST"])
def api_remove_peer(peer):
    ok, msg = nordvpn.remove_peer(peer)
    return jsonify({"success": ok, "message": msg})


@app.route("/api/connections")
def api_connections():
    return jsonify({
        "devices": connection_log.entries(),
        "interval": CONNECTION_LOG_INTERVAL_S,
        "max_per_device": connection_log.MAX_CONNECTIONS_PER_PEER,
    })


@app.route("/api/invitations")
def api_invitations():
    return jsonify(nordvpn.list_invitations())


@app.route("/api/invitations/send", methods=["POST"])
def api_send_invitation():
    data = request.json
    email = data.get("email", "")
    perms = data.get("permissions", {})
    ok, msg = nordvpn.send_invitation(email, perms)
    return jsonify({"success": ok, "message": msg})


@app.route("/api/invitations/revoke", methods=["POST"])
def api_revoke_invitation():
    email = request.json.get("email", "")
    ok, msg = nordvpn.revoke_invitation(email)
    return jsonify({"success": ok, "message": msg})


@app.route("/api/invitations/accept", methods=["POST"])
def api_accept_invitation():
    data = request.json
    email = data.get("email", "")
    perms = data.get("permissions", {})
    ok, msg = nordvpn.accept_invitation(email, perms)
    return jsonify({"success": ok, "message": msg})


@app.route("/api/invitations/deny", methods=["POST"])
def api_deny_invitation():
    email = request.json.get("email", "")
    ok, msg = nordvpn.deny_invitation(email)
    return jsonify({"success": ok, "message": msg})


@app.route("/api/version")
def api_version():
    return jsonify(nordvpn.check_update())


@app.route("/api/update", methods=["POST"])
def api_update():
    ok, msg = nordvpn.perform_update()
    return jsonify({"success": ok, "message": msg})


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 5000))
    app.run(host=host, port=port, debug=True)
