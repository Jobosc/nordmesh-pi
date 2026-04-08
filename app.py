"""Flask web application for NordVPN Meshnet management."""

from flask import Flask, render_template, request, jsonify, redirect, url_for
import nordvpn

app = Flask(__name__)


@app.route("/")
def index():
    status = nordvpn.get_status()
    return render_template("index.html", status=status)


@app.route("/api/status")
def api_status():
    return jsonify(nordvpn.get_status())


@app.route("/api/install", methods=["POST"])
def api_install():
    ok, msg = nordvpn.install_nordvpn()
    return jsonify({"success": ok, "message": msg})


@app.route("/api/login", methods=["POST"])
def api_login():
    token = request.json.get("token") if request.is_json else None
    if token:
        ok, msg = nordvpn.login_with_token(token)
    else:
        ok, msg = nordvpn.login()
    return jsonify({"success": ok, "message": msg})


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
