# NordVPN Meshnet Manager

A lightweight web UI for managing NordVPN Meshnet on a Raspberry Pi. Run it on the Pi and control everything from any browser on your network.

```
[Your browser] --HTTP--> [Flask on Raspberry Pi] --CLI--> [nordvpn]
```

## Features

- **Guided setup** -- Installs NordVPN, handles login, and enables Meshnet step by step
- **Peer management** -- View all connected peers with live permission toggles:
  - Incoming traffic
  - Traffic routing
  - Local network access
  - File sharing
  - Auto-accept file transfers
- **Invitations** -- Send invitations with pre-selected permissions, revoke sent ones, accept or deny received ones
- **Responsive dark UI** -- Works on desktop and mobile browsers

## Requirements

- Raspberry Pi (or any Linux machine) with internet access
- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (the run script installs it automatically if missing)
- NordVPN account with an active subscription

## Quick Start

```bash
git clone <repo-url> && cd nordvpn_meshnet
chmod +x run.sh
./run.sh
```

Then open `http://<your-pi-ip>:5000` in a browser.

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

This starts 2 Gunicorn workers on port 5000.

### Running as a systemd service

```ini
# /etc/systemd/system/meshnet-ui.service
[Unit]
Description=NordVPN Meshnet Manager
After=network.target

[Service]
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
| POST | `/api/peers/<peer>/remove` | Remove a peer |
| GET | `/api/invitations` | List sent and received invitations |
| POST | `/api/invitations/send` | Send invitation (`email`, `permissions`) |
| POST | `/api/invitations/revoke` | Revoke a sent invitation |
| POST | `/api/invitations/accept` | Accept a received invitation |
| POST | `/api/invitations/deny` | Deny a received invitation |

## Security Note

This UI has no authentication. Anyone who can reach port 5000 on your Pi can manage your Meshnet. To restrict access:

- Bind to localhost only (`app.run(host="127.0.0.1")`) and use an SSH tunnel
- Or place it behind a reverse proxy (Caddy, nginx) with basic auth
- Or restrict access via firewall rules (`ufw allow from 192.168.1.0/24 to any port 5000`)
