"""Record when Meshnet peers come online.

The NordVPN CLI keeps no connection history, so a background thread polls the
peer list and logs every disconnected -> connected transition. Times are when
the change was noticed, so they can lag the real connection by one poll
interval. The log lives in a JSON file so it survives restarts and updates.
"""

import fcntl
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

import nordvpn

log = logging.getLogger(__name__)

MAX_CONNECTIONS_PER_PEER = 5

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir() -> str:
    return os.environ.get("NORDMESH_DATA_DIR") or os.path.join(_REPO_ROOT, "data")


def log_path() -> str:
    return os.path.join(data_dir(), "connection_log.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(path: str | None = None) -> dict | None:
    """Return the stored log, or None if nothing has been recorded yet."""
    try:
        with open(path or log_path()) as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        log.warning("Ignoring unreadable connection log: %s", exc)
        return None
    return data if isinstance(data.get("peers"), dict) else None


def _save(data: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)  # atomic, so readers never see a half-written file


def record(peers: list[dict], path: str | None = None, now: str | None = None) -> list[str]:
    """Merge a fresh peer list into the log; return hostnames that just connected.

    On the very first run there is nothing to compare against, so peers that
    are already online are noted without logging a connection — otherwise
    every install would start with a burst of made-up entries.
    """
    path = path or log_path()
    now = now or _now()
    stored = load(path)
    first_run = stored is None
    data = stored or {"peers": {}}
    known = data["peers"]

    connected_now = []
    seen = set()
    for peer in peers:
        hostname = peer.get("hostname")
        if not hostname or peer.get("is_self"):
            continue
        seen.add(hostname)
        entry = known.setdefault(hostname, {"connections": []})
        online = str(peer.get("status", "")).lower() == "connected"
        if online and entry.get("status") != "connected" and not first_run:
            entry["connections"] = ([now] + entry["connections"])[:MAX_CONNECTIONS_PER_PEER]
            connected_now.append(hostname)
        entry["status"] = "connected" if online else "disconnected"
        for field in ("nickname", "ip", "os"):
            if peer.get(field):
                entry[field] = peer[field]
            else:
                entry.pop(field, None)

    # Peers that left the list (removed, or Meshnet turned off) are offline;
    # keep their history so it's still visible.
    for hostname, entry in known.items():
        if hostname not in seen:
            entry["status"] = "disconnected"

    data["updated"] = now
    _save(data, path)
    return connected_now


def entries(path: str | None = None) -> list[dict]:
    """Peers with their recent connections, most recently connected first."""
    data = load(path) or {"peers": {}}
    devices = [{"hostname": h, **e} for h, e in data["peers"].items()]
    # ISO timestamps sort chronologically; peers never seen connecting go last.
    devices.sort(key=lambda d: d["connections"][0] if d["connections"] else "", reverse=True)
    return devices


def poll_once() -> None:
    peers = nordvpn.fetch_peers()
    if peers is None:
        return  # daemon didn't answer — keep the last known state
    for hostname in record(peers):
        log.info("Meshnet peer connected: %s", hostname)


def _try_lock(lock_path: str):
    """Take the poller lock without blocking; return the open file or None.

    gunicorn runs several worker processes, and each one imports the app.
    Only the holder of this lock polls, so connections aren't logged twice.
    """
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    f = open(lock_path, "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def start_poller(interval: int) -> None:
    def _loop():
        lock = None
        while True:
            try:
                # Keep retrying, so another worker takes over if the holder dies.
                lock = lock or _try_lock(os.path.join(data_dir(), "poller.lock"))
                if lock:
                    poll_once()
            except Exception:
                log.exception("Connection log poll failed")
            time.sleep(interval)

    threading.Thread(target=_loop, name="connection-log", daemon=True).start()
