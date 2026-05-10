"""Wrapper around the NordVPN CLI for Meshnet management."""

import subprocess
import shutil
import re


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run a shell command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", "Command timed out"
    except FileNotFoundError:
        return 127, "", f"Command not found: {cmd[0]}"


def is_installed() -> bool:
    return shutil.which("nordvpn") is not None


def install_nordvpn() -> tuple[bool, str]:
    """Install NordVPN using the official installer script."""
    code, out, err = _run(
        ["bash", "-c", 'sh <(curl -sSf https://downloads.nordcdn.com/apps/linux/install.sh) --nordaccount'],
        timeout=120,
    )
    if code == 0:
        return True, "NordVPN installed successfully."
    return False, f"Installation failed: {err or out}"


def get_status() -> dict:
    """Get NordVPN connection and account status."""
    info = {"installed": is_installed(), "logged_in": False, "meshnet_enabled": False, "connection": "Disconnected"}
    if not info["installed"]:
        return info

    code, out, _ = _run(["nordvpn", "account"])
    if code == 0 and "not logged in" not in out.lower():
        info["logged_in"] = True
        for line in out.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                info[key.strip().lower().replace(" ", "_")] = val.strip()

    code, out, _ = _run(["nordvpn", "meshnet", "peer", "list"])
    if code == 0 and "meshnet is not enabled" not in out.lower():
        info["meshnet_enabled"] = True

    code, out, _ = _run(["nordvpn", "status"])
    if code == 0:
        for line in out.splitlines():
            if line.lower().startswith("status:"):
                info["connection"] = line.split(":", 1)[1].strip()

    return info


def login() -> tuple[bool, str]:
    """Initiate login. Returns a URL the user must open in a browser.

    nordvpn login has two quirks this function handles:
    1. On first run it may ask whether analytics data can be collected —
       we answer "n" via stdin so the prompt doesn't block us.
    2. After printing the login URL it blocks waiting for browser auth,
       so we kill it after 15 s and drain the pipe to recover the URL.
    """
    try:
        proc = subprocess.Popen(
            ["nordvpn", "login"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # merge stderr so URL is captured regardless of stream
            text=True,
        )
    except FileNotFoundError:
        return False, "Command not found: nordvpn"

    try:
        # "n\n" declines the data-collection prompt on first run.
        # If no prompt appears the input is discarded harmlessly.
        stdout, _ = proc.communicate(input="n\n", timeout=15)
    except subprocess.TimeoutExpired:
        # nordvpn printed the URL then blocked waiting for browser auth — kill
        # it and drain whatever it wrote so we can extract the URL.
        proc.kill()
        stdout, _ = proc.communicate()

    # Prefer a URL that follows browser/login context keywords (the real auth URL).
    # NordVPN also prints policy URLs before the login URL, so we skip those.
    login_match = re.search(r'(?:browser|open|link)[^\n]*?(https://[^\s]+)', stdout, re.IGNORECASE)
    if login_match:
        return True, login_match.group(1)
    for m in re.finditer(r'https://[^\s]+', stdout):
        if not any(x in m.group(0) for x in ('privacy', 'terms', 'legal')):
            return True, m.group(0)
    if "already logged in" in stdout.lower():
        return True, "Already logged in."
    return False, stdout.strip() or "Login failed: no URL received."


def login_with_token(token: str) -> tuple[bool, str]:
    """Login using an access token."""
    code, out, err = _run(["nordvpn", "login", "--token", token])
    combined = out + "\n" + err
    if code == 0 or "welcome" in combined.lower() or "already logged in" in combined.lower():
        return True, "Login successful."
    return False, combined


def logout() -> tuple[bool, str]:
    code, out, err = _run(["nordvpn", "logout"])
    return code == 0, out or err


def enable_meshnet() -> tuple[bool, str]:
    code, out, err = _run(["nordvpn", "set", "meshnet", "on"])
    if code == 0 or "already enabled" in (out + err).lower():
        return True, "Meshnet enabled."
    return False, out or err


def disable_meshnet() -> tuple[bool, str]:
    code, out, err = _run(["nordvpn", "set", "meshnet", "off"])
    return code == 0, out or err


def list_peers() -> list[dict]:
    """List all meshnet peers with their permissions."""
    code, out, _ = _run(["nordvpn", "meshnet", "peer", "list"])
    if code != 0:
        return []
    return _parse_peer_list(out)


def _parse_peer_list(raw: str) -> list[dict]:
    """Parse the nordvpn meshnet peer list output into structured data.

    The nordvpn CLI outputs peers in sections: "This device:", "Local Peers:",
    "External Peers:". Each peer has "Hostname:" and "Nickname:" fields (in
    either order), plus permission lines like "Allow Incoming Traffic: enabled".
    """
    # Map CLI output keys to internal permission names used by the frontend
    # "Allow X" = permissions you grant to the peer
    PERM_MAP = {
        "allow_incoming_traffic": "incoming",
        "allow_routing": "routing",
        "allow_local_network_access": "local_network",
        "allow_sending_files": "fileshare",
        "accept_fileshare_automatically": "auto_accept",
    }
    # "Allows X" = permissions the peer grants to you (read-only info)
    ALLOWS_MAP = {
        "allows_incoming_traffic": "allows_incoming",
        "allows_routing": "allows_routing",
        "allows_local_network_access": "allows_local_network",
        "allows_sending_files": "allows_fileshare",
    }

    peers = []
    current = None
    pending = {}  # buffer for fields that appear before Hostname
    section = "self"  # nordvpn lists "This device" first

    def _flush():
        nonlocal current, pending
        if current:
            peers.append(current)
        current = None
        pending = {}

    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("-") or line.startswith("="):
            continue
        # Blank lines separate peers — flush the current peer
        if not line:
            if current:
                _flush()
            continue

        # Detect section headers: "This device:", "Local Peers:", "External Peers:"
        low = line.lower()
        if ":" in line and line.split(":", 1)[1].strip() == "":
            if "external" in low:
                _flush()
                section = "external"
                continue
            if "this device" in low:
                _flush()
                section = "self"
                continue
            if "local" in low:
                _flush()
                section = "local"
                continue

        # Lines without colon are bare hostnames (fallback format)
        if ":" not in line:
            _flush()
            current = {"hostname": line, "status": "unknown", "is_local": section in ("self", "local"), "is_self": section == "self", "permissions": {}}
            continue

        # Key-value lines
        key, val = line.split(":", 1)
        key_norm = key.strip().lower().replace(" ", "_")
        val = val.strip()

        # "Hostname:" starts a new peer
        if key_norm == "hostname":
            _flush()
            current = {"hostname": val, "status": "unknown", "is_local": section in ("self", "local"), "is_self": section == "self", "permissions": {}}
            # Apply any buffered fields (e.g. Nickname that appeared first)
            if pending:
                for pk, pv in pending.items():
                    current[pk] = pv
                pending = {}
            continue

        # If we have no current peer yet, buffer the field until Hostname appears
        if current is None:
            if key_norm == "nickname" and val != "-":
                pending["nickname"] = val
            continue

        # Standard fields
        if key_norm == "status":
            current["status"] = val
        elif key_norm == "ip":
            current["ip"] = val
        elif key_norm == "os":
            current["os"] = val
        elif key_norm == "nickname":
            if val != "-":
                current["nickname"] = val
        elif key_norm in PERM_MAP:
            current["permissions"][PERM_MAP[key_norm]] = val.lower() in ("allowed", "enabled", "true")
        elif key_norm in ALLOWS_MAP:
            current["permissions"][ALLOWS_MAP[key_norm]] = val.lower() in ("allowed", "enabled", "true")
        else:
            current[key_norm] = val

    _flush()
    return peers


def list_invitations() -> dict:
    """List sent and received meshnet invitations."""
    code, out, _ = _run(["nordvpn", "meshnet", "inv", "list"])
    if code != 0:
        return {"sent": [], "received": []}
    return _parse_invitations(out)


def _parse_invitations(raw: str) -> dict:
    sent = []
    received = []
    section = None
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("-"):
            continue
        low = stripped.lower()
        if "sent" in low and "invitation" in low:
            section = "sent"
            continue
        if "received" in low and "invitation" in low:
            section = "received"
            continue
        if section == "sent" and stripped:
            sent.append(stripped)
        elif section == "received" and stripped:
            received.append(stripped)
    return {"sent": sent, "received": received}


# --- Permissions ---
PERMISSIONS = [
    ("incoming", "Allow incoming traffic"),
    ("routing", "Allow traffic routing"),
    ("local", "Allow local network access"),
    ("fileshare", "Allow file sharing"),
    ("auto-accept", "Auto-accept file transfers"),
]


def set_permission(peer: str, perm: str, allow: bool) -> tuple[bool, str]:
    """Set a specific permission for a peer. perm is one of: incoming, routing, local, fileshare, auto-accept."""
    action = "allow" if allow else "deny"
    code, out, err = _run(["nordvpn", "meshnet", "peer", perm, action, peer])
    return code == 0, out or err


def set_all_permissions(peer: str, perms: dict[str, bool]) -> list[tuple[str, bool, str]]:
    """Set multiple permissions at once. Returns list of (perm, success, message)."""
    results = []
    for perm, allow in perms.items():
        ok, msg = set_permission(peer, perm, allow)
        results.append((perm, ok, msg))
    return results


# --- Invitations ---

def send_invitation(email: str, permissions: dict[str, bool] | None = None) -> tuple[bool, str]:
    """Send a meshnet invitation to an email address with optional permissions."""
    cmd = ["nordvpn", "meshnet", "inv", "send"]
    if permissions is not None:
        if permissions.get("incoming"):
            cmd.append("--allow-incoming-traffic")
        if permissions.get("routing"):
            cmd.append("--allow-traffic-routing")
        if permissions.get("local"):
            cmd.append("--allow-local-network")
        if permissions.get("fileshare"):
            cmd.append("--allow-peer-send-files")
    cmd.append(email)
    code, out, err = _run(cmd)
    if code == 0:
        return True, f"Invitation sent to {email}."
    return False, out or err


def revoke_invitation(email: str) -> tuple[bool, str]:
    code, out, err = _run(["nordvpn", "meshnet", "inv", "revoke", email])
    return code == 0, out or err


def accept_invitation(email: str, permissions: dict[str, bool] | None = None) -> tuple[bool, str]:
    cmd = ["nordvpn", "meshnet", "inv", "accept"]
    if permissions is not None:
        if permissions.get("incoming"):
            cmd.append("--allow-incoming-traffic")
        if permissions.get("routing"):
            cmd.append("--allow-traffic-routing")
        if permissions.get("local"):
            cmd.append("--allow-local-network")
        if permissions.get("fileshare"):
            cmd.append("--allow-peer-send-files")
    cmd.append(email)
    code, out, err = _run(cmd)
    return code == 0, out or err


def deny_invitation(email: str) -> tuple[bool, str]:
    code, out, err = _run(["nordvpn", "meshnet", "inv", "deny", email])
    return code == 0, out or err


def set_nickname(peer: str, nickname: str) -> tuple[bool, str]:
    """Set or remove a nickname for a peer."""
    if nickname:
        code, out, err = _run(["nordvpn", "meshnet", "peer", "nickname", "set", peer, nickname])
    else:
        code, out, err = _run(["nordvpn", "meshnet", "peer", "nickname", "remove", peer])
    return code == 0, out or err


def remove_peer(peer: str) -> tuple[bool, str]:
    code, out, err = _run(["nordvpn", "meshnet", "peer", "remove", peer])
    return code == 0, out or err
