"""Wrapper around the NordVPN CLI for Meshnet management."""

import subprocess
import shutil
import re
import os
import select
import time


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


def _is_consent_prompt(text: str) -> bool:
    """Return True if text looks like a NordVPN analytics/data-collection prompt."""
    low = text.lower()
    return any(k in low for k in ['y/n', 'yes/no', 'analytics', 'anonymous', 'statistics', 'data collection', 'help us improve', 'share data'])


def _extract_login_url(stdout: str) -> tuple[bool, str]:
    """Extract the auth URL from nordvpn login output."""
    login_match = re.search(r'(?:browser|open|link)[^\n]*?(https://[^\s]+)', stdout, re.IGNORECASE)
    if login_match:
        return True, login_match.group(1)
    for m in re.finditer(r'https://[^\s]+', stdout):
        if not any(x in m.group(0) for x in ('privacy', 'terms', 'legal')):
            return True, m.group(0)
    if "already logged in" in stdout.lower():
        return True, "Already logged in."
    return False, stdout.strip() or "Login failed: no URL received."


def _login_with_input(input_text: str) -> tuple[bool, str]:
    """Run nordvpn login, send input_text to stdin, return (success, url_or_error)."""
    try:
        proc = subprocess.Popen(
            ["nordvpn", "login"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except FileNotFoundError:
        return False, "Command not found: nordvpn"

    try:
        stdout, _ = proc.communicate(input=input_text, timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, _ = proc.communicate()

    return _extract_login_url(stdout)


def login(analytics_consent: str | None = None) -> tuple[bool, str]:
    """Initiate login. Returns a URL the user must open in a browser.

    On first run NordVPN may ask whether analytics data can be collected.
    When analytics_consent is None this function detects that prompt and
    returns (False, "CONSENT_REQUIRED:<prompt text>") so the caller can
    surface the question to the user.  Pass analytics_consent="y" or "n"
    on the follow-up call to answer the prompt and proceed to get the URL.

    After printing the login URL nordvpn blocks waiting for browser auth,
    so we kill it after 15 s and drain the pipe to recover the URL.
    """
    # If caller already has a consent answer, just run with it directly.
    if analytics_consent is not None:
        return _login_with_input(analytics_consent + "\n")

    # Detection run: read initial output to check for a consent prompt.
    try:
        proc = subprocess.Popen(
            ["nordvpn", "login"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
    except FileNotFoundError:
        return False, "Command not found: nordvpn"

    initial_output = ""
    deadline = time.time() + 3.0
    while time.time() < deadline:
        remaining = deadline - time.time()
        try:
            ready, _, _ = select.select([proc.stdout], [], [], min(remaining, 0.2))
        except (ValueError, OSError):
            break
        if ready:
            chunk = os.read(proc.stdout.fileno(), 4096)
            if chunk:
                initial_output += chunk.decode("utf-8", errors="replace")
            else:
                break
        if _is_consent_prompt(initial_output) or re.search(r'https://[^\s]+', initial_output):
            break

    if _is_consent_prompt(initial_output):
        proc.kill()
        proc.communicate()
        return False, "CONSENT_REQUIRED:" + initial_output.strip()

    # No consent prompt — collect remaining output (nordvpn will block after printing URL).
    try:
        proc.stdin.close()
    except OSError:
        pass
    try:
        remaining_bytes, _ = proc.communicate(timeout=12)
        remaining_text = remaining_bytes.decode("utf-8", errors="replace") if isinstance(remaining_bytes, bytes) else (remaining_bytes or "")
    except subprocess.TimeoutExpired:
        proc.kill()
        remaining_bytes, _ = proc.communicate()
        remaining_text = remaining_bytes.decode("utf-8", errors="replace") if isinstance(remaining_bytes, bytes) else ""

    return _extract_login_url(initial_output + remaining_text)


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


# --- Update management ---

def _parse_version(v: str) -> tuple[int, ...]:
    """Parse 'v1.2.3' or '1.2.3' into (1, 2, 3) for comparison."""
    parts = re.split(r'[.\-]', v.strip().lstrip('v'))
    try:
        return tuple(int(x) for x in parts if x.isdigit())
    except Exception:
        return (0,)


def get_current_version() -> str:
    """Return the current version from the nearest git tag."""
    code, out, _ = _run(["git", "describe", "--tags", "--abbrev=0"])
    return out.strip() if code == 0 else "unknown"


def get_latest_version() -> str:
    """Return the highest version tag found on the git remote."""
    code, out, _ = _run(["git", "ls-remote", "--tags", "origin"], timeout=10)
    if code != 0 or not out:
        return ""
    tags = []
    for line in out.splitlines():
        parts = line.split('\t')
        if len(parts) == 2:
            ref = parts[1].strip()
            if ref.endswith('^{}'):   # skip annotated tag derefs
                continue
            tag = ref.replace('refs/tags/', '')
            if tag:
                tags.append(tag)
    if not tags:
        return ""
    tags.sort(key=_parse_version, reverse=True)
    return tags[0]


def check_update() -> dict:
    """Return current version, latest version, and whether an update is available."""
    current = get_current_version()
    latest = get_latest_version()
    update_available = (
        current not in ("", "unknown")
        and bool(latest)
        and _parse_version(latest) > _parse_version(current)
    )
    return {"current": current, "latest": latest, "update_available": update_available}


def perform_update() -> tuple[bool, str]:
    """Pull latest code, sync deps, then restart the service."""
    import os, threading

    code, out, err = _run(["git", "pull"], timeout=60)
    if code != 0:
        return False, f"git pull failed: {err or out}"

    uv = shutil.which("uv") or os.path.expanduser("~/.local/bin/uv")
    code, out, err = _run([uv, "sync"], timeout=120)
    if code != 0:
        return False, f"uv sync failed: {err or out}"

    def _restart():
        import time
        time.sleep(2)
        _run(["sudo", "systemctl", "restart", "nordvpn-meshnet"], timeout=15)

    threading.Thread(target=_restart, daemon=True).start()
    return True, "Update applied. Service restarting..."


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
