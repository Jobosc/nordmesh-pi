# NordVPN Meshnet Manager

> **Fully vibecoded.** This project was built entirely with AI assistance using [Claude Code](https://claude.ai/code).

A lightweight web UI for managing NordVPN Meshnet on a Raspberry Pi (or any Linux machine). Run it on the device and control everything from any browser on your network.

```
[Your browser] ──HTTPS──> [Caddy on Raspberry Pi] ──HTTP──> [Flask] ──CLI──> [nordvpn]
```

## Features

- **Guided setup** — Installs NordVPN, handles login (token or browser link), and enables Meshnet step by step
- **Consent prompt handling** — Detects NordVPN's data-collection prompt at first login and displays it inline with Accept/Decline buttons
- **Peer management** — Peers split into "My Devices" and "External Devices", with live permission toggles per peer:
  - Incoming traffic
  - Traffic routing
  - Local network access
  - File sharing
- **Nicknames** — Set or remove a nickname for any peer; the hostname is shown in smaller text alongside it
- **Invitations** — Send invitations with pre-selected permissions, revoke sent ones, accept or deny received ones
- **Update management** — Check for and apply NordVPN updates from the header menu (available after login)
- **Docker support** — First-class Docker and Docker Compose setup with persistent login state
- **Home Assistant compatible** — Embeddable via iframe (Webpage card)
- **Responsive dark UI** — Works on desktop and mobile browsers

## Requirements

- Raspberry Pi or any Linux machine with internet access
- Python 3.10+ and [uv](https://docs.astral.sh/uv/) — or Docker
- NordVPN account (active subscription **not** required — Meshnet is free)

## Quick Start

### Native (Raspberry Pi / Linux)

```bash
git clone https://github.com/Jobosc/nordmesh-pi.git
cd nordmesh-pi
./run.sh
```

Open `http://localhost:5000` in a browser. If NordVPN is not yet installed, the UI will offer a one-click install, then guide you through login and enabling Meshnet.

For remote access from other devices on your network, set up Caddy as a reverse proxy (see [HTTPS with Caddy](#https-with-caddy)).

### Docker

```bash
git clone https://github.com/Jobosc/nordmesh-pi.git
cd nordmesh-pi
docker compose -f docker/docker-compose.yml up -d
```

The container runs on port `5000` by default. NordVPN login state is persisted in a named volume (`nordvpn-data`) so it survives container restarts.

Requires `NET_ADMIN` / `NET_RAW` capabilities and `/dev/net/tun` — already configured in `docker/docker-compose.yml`.

To change the port:

```bash
PORT=8080 docker compose -f docker/docker-compose.yml up -d
```

## Login Methods

| Method | How |
|---|---|
| **Access token** | Generate a token at [my.nordaccount.com](https://my.nordaccount.com) → Manual Setup, paste it into the UI |
| **Browser link** | Click "Login via Browser Link", open the returned URL on any device, complete the login there — the UI polls for completion and redirects automatically |

## Production (native)

For a long-running native setup, run:

```bash
./run.sh
```

This starts 2 Gunicorn workers bound to `0.0.0.0:5000`. The Docker setup always uses Gunicorn.

### Running as a systemd service

```ini
# /etc/systemd/system/meshnet-ui.service
[Unit]
Description=NordVPN Meshnet Manager
After=network.target

[Service]
Environment="PATH=/home/pi/.local/bin:/usr/local/bin:/usr/bin:/bin"
WorkingDirectory=/home/pi/nordmesh-pi
ExecStart=/home/pi/nordmesh-pi/run.sh
User=pi
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now meshnet-ui
```

A ready-made service file is included at `nordvpn-meshnet.service`.

## Permissions

The user running the app must be in the `nordvpn` group:

```bash
sudo usermod -aG nordvpn $USER
# Log out and back in for the change to take effect
```

## Project Structure

```
nordmesh-pi/
├── src/
│   ├── app.py                # Flask routes — thin layer delegating to nordvpn.py
│   └── nordvpn.py            # nordvpn CLI wrapper (all subprocess calls live here)
├── templates/
│   └── index.html            # Single-page UI (HTML + inline CSS + JS)
├── docker/
│   ├── Dockerfile            # Container image (debian:bookworm-slim + NordVPN via apt)
│   ├── docker-compose.yml    # Compose config with capabilities and persistent volume
│   └── docker-entrypoint.sh  # Starts nordvpnd, waits for it, then runs Gunicorn
├── tests/                    # pytest test suite
├── .dockerignore             # Build context exclusions (stays at project root)
├── nordvpn-meshnet.service   # Systemd unit file for native installs
├── pyproject.toml            # Dependencies (Flask, Gunicorn) managed by uv
├── run.sh                    # Startup script (installs uv if needed, runs Gunicorn)
├── setup.sh                  # One-shot Raspberry Pi setup script
└── teardown.sh               # Reverses the setup
```

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Web UI |
| GET | `/api/status` | Install, login, and Meshnet status |
| POST | `/api/install` | Install NordVPN |
| POST | `/api/login` | Login — body: `{"token": "…"}` or `{"user_input": "y/n"}` or empty for browser link |
| POST | `/api/logout` | Logout |
| POST | `/api/meshnet/enable` | Enable Meshnet |
| POST | `/api/meshnet/disable` | Disable Meshnet |
| GET | `/api/peers` | List all Meshnet peers |
| POST | `/api/peers/<peer>/permissions` | Set permissions for a peer |
| POST | `/api/peers/<peer>/nickname` | Set or remove a peer nickname |
| POST | `/api/peers/<peer>/remove` | Remove a peer |
| GET | `/api/invitations` | List sent and received invitations |
| POST | `/api/invitations/send` | Send invitation (`email`, `permissions`) |
| POST | `/api/invitations/revoke` | Revoke a sent invitation |
| POST | `/api/invitations/accept` | Accept a received invitation |
| POST | `/api/invitations/deny` | Deny a received invitation |
| GET | `/api/version` | Check current and latest NordVPN version |
| POST | `/api/update` | Pull latest code and restart |

## HTTPS with Caddy

1. Install Caddy:

```bash
sudo apt install caddy
```

2. Find your device's local IP:

```bash
hostname -I
```

3. Edit `/etc/caddy/Caddyfile`:

```
https://192.168.1.100 {
    reverse_proxy localhost:5000
    tls internal
}
```

Replace `192.168.1.100` with your actual IP. `tls internal` generates a self-signed certificate (one-time browser warning). If you have a domain pointing at the device, replace the IP with the domain and drop `tls internal` — Caddy provisions a Let's Encrypt certificate automatically.

4. Restart Caddy:

```bash
sudo systemctl restart caddy
```

### Home Assistant

Add a **Webpage card** pointing to `https://<your-device-ip>` to embed the UI in a dashboard.

## Security

This UI has no built-in authentication. To restrict access:

- Add basic auth in the Caddyfile: `basicauth { <user> <bcrypt-hash> }`
- Restrict by IP via firewall: `ufw allow from 192.168.1.0/24 to any port 443`
