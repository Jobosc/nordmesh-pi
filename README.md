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


## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `HOST` / `PORT` | `0.0.0.0` / `5000` | Where the web UI listens |
| `NORDVPN_CONNECT_ATTEMPTS` | `5` | How many times the UI retries the NordVPN daemon before showing the "Can't Connect to NordVPN" screen |
| `NORDVPN_CONNECT_RETRY_DELAY_MS` | `3000` | Delay between those retries |
| `ALLOWED_FRAME_ANCESTORS` | `*` | Origins allowed to embed the UI in an iframe, e.g. `https://ha.example.com`. Use `none` to forbid embedding |
| `CF_ACCESS_TEAM_DOMAIN` | — | Cloudflare Zero Trust team domain. Set together with `CF_ACCESS_AUD` to verify Access tokens |
| `CF_ACCESS_AUD` | — | Cloudflare Access application audience (AUD) tag |
| `CF_ACCESS_ALLOW_LOCAL` | `true` | Allow requests that didn't arrive through Cloudflare (LAN, healthchecks) |

If the NordVPN daemon isn't reachable (`nordvpnd` stopped, missing socket permissions, or missing container capabilities), the UI retries and then shows an error screen with the daemon's own message and a **Try Again** button. It recovers on its own as soon as the daemon responds.

## Remote access (HTTPS + Home Assistant)

To reach the UI from outside your network — or embed it in a Home Assistant
dashboard — see **[docs/remote-access.md](docs/remote-access.md)**. It sets up a
Cloudflare Tunnel (HTTPS, no open router ports) protected by Cloudflare Access:

```bash
sudo ./cloudflare/setup-tunnel.sh meshnet.example.com
```

## Security

**The UI has no authentication of its own.** Anyone who can reach it can log out
your NordVPN account, remove peers, send invitations, and trigger an update that
restarts the service — so never expose it directly to the internet.

- **Remote access:** use Cloudflare Access, as described in [docs/remote-access.md](docs/remote-access.md), and set `CF_ACCESS_TEAM_DOMAIN` / `CF_ACCESS_AUD` so the app verifies tokens itself.
- **LAN only:** keep it bound to the local network and restrict with Caddy basic auth (`basicauth`) or firewall rules (`ufw`).
