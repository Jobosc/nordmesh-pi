# Remote access over HTTPS (Cloudflare Tunnel + Access)

Reach the Meshnet Manager from anywhere — including inside a Home Assistant
dashboard — over HTTPS, without opening a single port on your router.

```
                                    ┌─────────────────────────────┐
  Your phone ──https──> Cloudflare ─┤ Access: is this you?        │
  (anywhere)             edge       └──────────────┬──────────────┘
                                                   │ (authenticated only)
                                      outbound tunnel, no open ports
                                                   │
                                          ┌────────┴────────┐
                                          │ Pi              │
                                          │  cloudflared    │
                                          │      ↓          │
                                          │  app :5000      │
                                          │  (localhost)    │
                                          └─────────────────┘
```

The Pi dials *out* to Cloudflare, so your router stays closed and your home IP
stays private. Cloudflare terminates TLS for your hostname, so the certificate
is publicly trusted — which is what makes the Home Assistant iframe work.

## Before you start

- A domain whose DNS is managed by Cloudflare (the free plan is enough).
- The Meshnet Manager already installed — see [`../setup.sh`](../setup.sh).
- A Cloudflare Zero Trust team (free for up to 50 users).

> **The UI has no login of its own.** Anyone who reaches it can log out your
> NordVPN account, remove peers, and trigger an update that restarts the
> service. Do not skip the Access policy in step 2.

## 1. Create the tunnel

### Native install (Raspberry Pi)

```bash
sudo ./cloudflare/setup-tunnel.sh meshnet.example.com
```

The script installs `cloudflared`, walks you through the browser login, creates
the tunnel, points the DNS record at it, and installs a systemd service. It is
idempotent — re-run it to change hostname or repair the config.

### Docker

Create the tunnel in **Zero Trust → Networks → Tunnels**, set its public
hostname to point at `http://nordvpn-meshnet:5000`, then put the token in
`docker/.env`:

```bash
CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoi...
```

```bash
docker compose -f docker/docker-compose.yml --profile cloudflare up -d
```

The `cloudflare` profile means the tunnel only starts when you ask for it;
plain `up -d` still runs the app alone.

## 2. Put Cloudflare Access in front of it

1. **Zero Trust → Access → Applications → Add an application → Self-hosted**
2. Domain: `meshnet.example.com`
3. Add a policy — Action **Allow**, Include **Emails** → your email address
4. Save, then open the application's **Overview** tab and copy the
   **Application Audience (AUD) tag**

Visiting the hostname now prompts for a one-time code before anything reaches
the Pi.

## 3. Verify Access tokens on the Pi too

Cloudflare checks identity at the edge, but the Pi will happily serve anyone who
reaches it another way. Have the app verify Cloudflare's signed assertion as
well, so a misconfigured tunnel or a stray `HOST=0.0.0.0` can't quietly expose
peer management.

```bash
# install the verification dependency
uv sync --extra cloudflare

sudo systemctl edit nordvpn-meshnet
```

```ini
[Service]
Environment=CF_ACCESS_TEAM_DOMAIN=your-team.cloudflareaccess.com
Environment=CF_ACCESS_AUD=<the AUD tag from step 2>
```

```bash
sudo systemctl restart nordvpn-meshnet
```

For Docker, set `CF_ACCESS_TEAM_DOMAIN` and `CF_ACCESS_AUD` in `docker/.env` —
the image already ships the dependency.

Requests arriving through Cloudflare must now carry a valid, unexpired,
correctly-audienced token signed by your team's keys. Requests that did *not*
come through Cloudflare (your LAN, the Docker healthcheck) are still allowed;
set `CF_ACCESS_ALLOW_LOCAL=false` to require Access for those too.

If the variables are set but PyJWT is missing, the app refuses Cloudflare
traffic with a 503 rather than serving it unauthenticated.

Updates keep this dependency: a plain `uv sync` prunes extras, so both
`run.sh` and the in-app update button add `--extra cloudflare` automatically
whenever `CF_ACCESS_TEAM_DOMAIN` and `CF_ACCESS_AUD` are set. Without that,
updating would drop PyJWT and lock you out remotely.

## 4. Add it to Home Assistant

An HA dashboard iframe is loaded by **your browser**, not by Home Assistant. So
the URL has to be publicly reachable with a valid certificate — which is exactly
what step 1 gave you. A LAN IP or a self-signed certificate will show a blank
panel when you are away from home.

1. **Settings → Dashboards → + Add Dashboard → Webpage**
2. URL: `https://meshnet.example.com`
3. Give it a title and an icon (`mdi:lan-connect` suits it)

YAML `panel_iframe` still works on older installs but was deprecated in Home
Assistant 2024.4 and auto-migrated to this webpage dashboard.

### Put it on the same parent domain as Home Assistant

If you reach Home Assistant at `https://ha.example.com`, host this at
`https://meshnet.example.com` — same registrable domain. The Access session
cookie is then same-site with the HA page, so the iframe loads without the
browser's third-party-cookie rules blocking it.

If the two live on unrelated domains, the Access login is a cross-site iframe
and most browsers will block the cookie. You'll get a blank panel until you open
the URL once in its own tab.

### Narrow who may embed the UI

By default any origin may frame it. Once you know your HA origin, restrict it:

```ini
Environment=ALLOWED_FRAME_ANCESTORS=https://ha.example.com
```

Use `none` to forbid embedding entirely.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Blank panel in HA, works in its own tab | Access cookie blocked as third-party — put both on the same parent domain (above) |
| `502 Bad Gateway` from Cloudflare | App isn't running, or the tunnel points at the wrong port: `systemctl status nordvpn-meshnet` |
| Everything returns 401 | `CF_ACCESS_AUD` doesn't match the application's AUD tag |
| Everything returns 503 | `CF_ACCESS_*` set without the dependency — run `uv sync --extra cloudflare` |
| Access prompt never appears | The application's domain doesn't match the hostname exactly |
| Tunnel won't start | `journalctl -fu cloudflared` |

## Reverting

```bash
sudo systemctl disable --now cloudflared
sudo cloudflared tunnel delete nordmesh
```

Then delete the DNS record and the Access application in the Cloudflare
dashboard.
