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
    """Initiate login. Returns a URL the user must open in a browser."""
    code, out, err = _run(["nordvpn", "login"], timeout=15)
    combined = out + "\n" + err
    url_match = re.search(r'https://[^\s]+', combined)
    if url_match:
        return True, url_match.group(0)
    if "already logged in" in combined.lower():
        return True, "Already logged in."
    return False, combined


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
    """Parse the nordvpn meshnet peer list output into structured data."""
    peers = []
    current = None
    section = "local"  # default; nordvpn lists local (own) devices first
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("-") or line.startswith("="):
            continue

        # Detect section headers like "Local Peers:", "External Peers:", etc.
        low = line.lower()
        if ":" in line and not current:
            # Before any peer is found, check for section headers
            if "external" in low:
                section = "external"
                continue
            if "local" in low or "this device" in low:
                section = "local"
                continue
        # Section headers can also appear between peers
        if ":" in line and line.split(":")[1].strip() == "":
            if "external" in low:
                if current:
                    peers.append(current)
                    current = None
                section = "external"
                continue
            if "local" in low or "this device" in low:
                if current:
                    peers.append(current)
                    current = None
                section = "local"
                continue

        # Detect peer header lines (hostname lines)
        if ":" not in line and line and not line.startswith(" "):
            if current:
                peers.append(current)
            current = {"hostname": line, "status": "unknown", "is_local": section == "local", "permissions": {}}
            continue

        if current and ":" in line:
            key, val = line.split(":", 1)
            key = key.strip().lower().replace(" ", "_")
            val = val.strip()
            if key == "status":
                current["status"] = val
            elif key == "ip":
                current["ip"] = val
            elif key == "os":
                current["os"] = val
            elif key in (
                "incoming",
                "routing",
                "local_network",
                "fileshare",
                "auto_accept",
                "peer_send_files",
            ):
                current["permissions"][key] = val.lower() in ("allowed", "enabled", "true")
            else:
                current[key] = val

    if current:
        peers.append(current)
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
    if permissions:
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
    if permissions:
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


def remove_peer(peer: str) -> tuple[bool, str]:
    code, out, err = _run(["nordvpn", "meshnet", "peer", "remove", peer])
    return code == 0, out or err
