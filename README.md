# NordVPN Meshnet Manager

A lightweight web UI for managing NordVPN Meshnet on a Raspberry Pi. Run it on the Pi and control everything from any browser on your network.

```
[Your browser] --HTTPS--> [Caddy on Raspberry Pi] --HTTP--> [Flask] --CLI--> [nordvpn]
```

## Features

- **Guided setup** -- Installs NordVPN, handles login, and enables Meshnet step by step
- **Peer management** -- View peers split into "My Devices" and "External Devices", with live permission toggles:
  - Incoming traffic
  - Traffic routing
  - Local network access
  - File sharing
- **Nickname editing** -- Set or change nicknames for any peer directly from the UI
- **Invitations** -- Send invitations with pre-selected permissions, revoke sent ones, accept or deny received ones
- **Home Assistant compatible** -- Embeddable via iframe (Webpage card)
- **Responsive dark UI** -- Works on desktop and mobile browsers

## Prerequisites

- [Raspberry Pi Imager](https://www.raspberrypi.com/software/) installed on your laptop — used to flash the SD card
- [Raspberry Pi OS](https://www.raspberrypi.com/software/operating-systems/) image downloaded and flashed onto the SD card using Raspberry Pi Imager

## Requirements

- Raspberry Pi (or any Linux machine) with internet access
- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (the run script installs it automatically if missing)
- [NordVPN](https://nordvpn.com/download/linux/) installed and configured (`sh <(curl -sSf https://downloads.nordcdn.com/apps/linux/install.sh)`)
- NordVPN account (an active subscription is **not** required — Meshnet is free for all NordVPN accounts)
- [Caddy](https://caddyserver.com/) (optional, for HTTPS access — `sudo apt install caddy`)

## Quick Start

```bash
git clone https://github.com/Jobosc/nordmesh-pi.git
./run.sh
```

Then open `http://localhost:5000` in a browser on the Pi. For remote access, set up Caddy as a reverse proxy (see [HTTPS with Caddy](#https-with-caddy)) and open `https://<your-pi-ip>` from any device on your network.

If NordVPN is not yet installed, the UI will offer a one-click install. After that it guides you through login and enabling Meshnet.

## Login Methods

| Method | How |
|---|---|
| **Access token** | Generate a token at [my.nordaccount.com](https://my.nordaccount.com) under "Manual Setup", paste it into the UI |
| **Browser link** | Click "Login via Browser Link", open the returned URL on any device, complete the login there |

## Production

For a long-running setup, use Gunicorn instead of the Flask dev server:

```bash
./run_production.sh
```

This starts 2 Gunicorn workers on localhost port 5000 (not exposed externally — use Caddy for HTTPS access).

### Running as a systemd service

```ini
# /etc/systemd/system/meshnet-ui.service
[Unit]
Description=NordVPN Meshnet Manager
After=network.target

[Service]
Environment="PATH=/home/pi/.local/bin:/usr/local/bin:/usr/bin:/bin"
WorkingDirectory=/home/pi/nordvpn_meshnet
ExecStart=/home/pi/nordvpn_meshnet/run_production.sh
User=pi
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now meshnet-ui
```

## Permissions

The user running the app must be in the `nordvpn` group to execute CLI commands without `sudo`:

```bash
sudo usermod -aG nordvpn $USER
# Log out and back in for the group change to take effect
```

To ensure NordVPN reconnects automatically after a reboot:

```bash
nordvpn set autoconnect on
```

## Project Structure

```
nordvpn_meshnet/
├── app.py              # Flask routes and API endpoints
├── nordvpn.py          # Python wrapper around the nordvpn CLI
├── templates/
│   └── index.html      # Single-page UI
├── pyproject.toml      # Project config and dependencies
├── run.sh              # Dev startup script
└── run_production.sh   # Production startup with Gunicorn
```

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Web UI |
| GET | `/api/status` | NordVPN install, login, and meshnet status |
| POST | `/api/install` | Install NordVPN |
| POST | `/api/login` | Login (with optional `token` in body) |
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

## HTTPS with Caddy

To serve the UI over HTTPS, install [Caddy](https://caddyserver.com/) and configure it as a reverse proxy.

1. Install Caddy:

```bash
sudo apt install caddy
```

2. Find your Pi's local IP:

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

Replace `192.168.1.100` with your Pi's actual IP. The `tls internal` directive generates a self-signed certificate (you'll see a one-time browser warning).

4. Restart Caddy:

```bash
sudo systemctl restart caddy
```

The UI is now available at `https://<your-pi-ip>`. If you have a domain pointing to the Pi, replace the IP with your domain in the Caddyfile and remove `tls internal` — Caddy will automatically provision a Let's Encrypt certificate.

### Home Assistant

To embed the UI in a Home Assistant dashboard, add a **Webpage card** with the URL `https://<your-pi-ip>`.

## Security Note

This UI has no authentication. Flask binds to localhost only, so direct access is limited to the Pi itself. When using Caddy, anyone who can reach the Pi's HTTPS port can manage your Meshnet. To restrict access:

- Add basic auth in the Caddyfile (`basicauth`)
- Restrict access via firewall rules (`ufw allow from 192.168.1.0/24 to any port 443`)
