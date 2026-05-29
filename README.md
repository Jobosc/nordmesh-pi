# NordVPN Meshnet Manager

> **Fully vibecoded** — built entirely with [Claude Code](https://claude.ai/code).

A lightweight web UI for managing NordVPN Meshnet on a Raspberry Pi or any Linux machine.

## Quick Start

**Native**
```bash
git clone https://github.com/Jobosc/nordmesh-pi.git
cd nordmesh-pi
sudo ./setup.sh
```

**Docker**
```bash
docker compose -f docker/docker-compose.yml up -d
```

Open `http://<device-ip>:5000`. The UI guides you through installing NordVPN, logging in, and enabling Meshnet.

## Requirements

- Linux machine with internet access
- Python 3.10+ and [uv](https://docs.astral.sh/uv/) — or Docker
- NordVPN account (subscription **not** required — Meshnet is free)

## Login

| Method | How |
|---|---|
| **Access token** | Go to [my.nordaccount.com](https://my.nordaccount.com) → **Services** → **NordVPN** → scroll to **Manual Setup** → choose **Access Token** tab → click **Generate new token** |
| **Browser link** | Click "Login via Browser Link" — the UI detects completion and redirects automatically |


## Security

No built-in authentication. Restrict access via Caddy basic auth (`basicauth`) or firewall rules (`ufw`).
