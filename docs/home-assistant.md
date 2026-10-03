# Home Assistant integration (optional)

Nordmesh works on its own. Open `http://<pi-ip>` in a browser on your home
network and you're done. This guide is for people who also run
[Home Assistant](https://www.home-assistant.io/) and want to:

- **Open Nordmesh from the HA sidebar**, including away from home, protected
  by your HA login and HTTPS.
- **Get a push notification** when the Pi loses Meshnet or goes offline.

Both parts are independent; set up either or both. Nothing changes on the Pi.
Home Assistant only needs to reach it over your home network.

## Contents

1. [Before you start](#1-before-you-start)
2. [Sidebar panel](#2-sidebar-panel)
3. [Alerts](#3-alerts)
4. [Troubleshooting](#4-troubleshooting)
5. [Removing the integration](#5-removing-the-integration)

---

## 1. Before you start

You need:

- Home Assistant on the same home network as the Pi.
- For the sidebar panel: [HACS](https://hacs.xyz/).
- For alerts: the [Home Assistant Companion app](https://companion.home-assistant.io/)
  on your phone, logged in to your HA.
- For anything away from home: a way to reach Home Assistant remotely, such as
  Nabu Casa, your own domain, or a VPN. No remote access yet? See
  [Reaching Home Assistant through Meshnet](#reaching-home-assistant-through-meshnet).

### Find the Pi's address

On the Pi:

```bash
hostname -I
```

The first address (e.g. `192.168.178.34`) is the Pi. Give it a **fixed IP**
with a DHCP reservation in your router. Otherwise the address can change after
a reboot and Home Assistant loses the connection.

The URL Home Assistant uses depends on how Nordmesh was installed:

| Install | URL |
|---|---|
| Native (`setup.sh`) | `http://<pi-ip>` (Caddy on port 80; the app itself only listens on localhost) |
| Docker | `http://<pi-ip>:5000` |

The examples below use `http://192.168.1.50`. Replace it with your own.

### Check that Home Assistant can reach the Pi

From Home Assistant's terminal (the **Terminal & SSH** add-on):

```bash
curl -sI --max-time 5 http://192.168.1.50/ | head -1
```

It should print `HTTP/1.1 200 OK`. If it doesn't, fix that first; see
[Troubleshooting](#4-troubleshooting).

Use plain `http://`. Traffic between Home Assistant and the Pi stays on your
home network, and Home Assistant adds HTTPS for you when you open it remotely.

---

## 2. Sidebar panel

The [hass_ingress](https://github.com/lovelylain/hass_ingress) integration makes
Home Assistant proxy Nordmesh, the same way it does for add-ons. Your browser only
ever talks to Home Assistant, so the panel works wherever HA works and is
covered by HA's login. The Pi never has to be reachable from the internet.

1. In **HACS**, search for **Ingress** and download it.
2. Add to `configuration.yaml`:

   ```yaml
   ingress:
     nordmesh:
       title: Meshnet
       icon: mdi:vpn
       url: http://192.168.1.50
       require_admin: true
   ```

3. Restart Home Assistant. **Meshnet** appears in the sidebar.

Later edits apply from **Developer Tools → YAML → Ingress** without a restart.

`require_admin: true` hides the panel from non-admin HA users. Remove it if
everyone in your household should be able to manage Meshnet.

Nordmesh notices it's running inside the panel (from the `X-Ingress-Path`
header Home Assistant sends) and adjusts its links automatically. This needs
Nordmesh **0.2.1 or newer**.

### Alternative: Webpage dashboard (home network only)

Without HACS, you can embed Nordmesh directly via **Settings → Dashboards →
Add Dashboard → Webpage**, URL `http://192.168.1.50`.

This loads Nordmesh straight from the Pi in your browser, so it only works on
your home network. It also only works when you opened Home Assistant over
`http://`; an `https://` HA page blocks an embedded `http://` page.

| | Ingress panel | Webpage dashboard |
|---|---|---|
| Works away from home | Yes | No |
| Works when HA is opened over HTTPS | Yes | No |
| Protected by your HA login | Yes | No |
| Needs HACS | Yes | No |

---

## 3. Alerts

Nordmesh reports its Meshnet health at `/api/health` (Nordmesh 0.2.4 or newer):

```json
{"ok": false, "state": "logged_out", "message": "NordVPN is logged out.", "checked_at": "2026-10-03T09:30:00+00:00"}
```

| `state` | Meaning |
|---|---|
| `ok` | Meshnet is running |
| `meshnet_off` | Meshnet was turned off |
| `logged_out` | The NordVPN account is logged out (e.g. the token expired) |
| `daemon_unreachable` | The NordVPN service on the Pi isn't responding |
| `not_installed` | NordVPN is missing |

Home Assistant checks this every minute and notifies your phone. Because Home
Assistant does the checking, you also get an alert when the Pi is off or has
dropped off your network, which the Pi couldn't report on its own.

### Add the sensors

In `configuration.yaml`:

```yaml
rest:
  - resource: http://192.168.1.50/api/health
    scan_interval: 60
    timeout: 30
    binary_sensor:
      - name: Nordmesh Meshnet
        unique_id: nordmesh_meshnet
        device_class: connectivity
        value_template: "{{ 'on' if value_json.ok else 'off' }}"
    sensor:
      - name: Nordmesh Meshnet Status
        unique_id: nordmesh_meshnet_status
        value_template: "{{ value_json.message[:250] }}"
```

Restart Home Assistant. `binary_sensor.nordmesh_meshnet` is then:

- **on** when Meshnet works,
- **off** when the Pi reports a problem (the reason is in
  `sensor.nordmesh_meshnet_status`),
- **unavailable** when the Pi doesn't answer at all.

### Find your phone's notify action

**Developer Tools → Actions**, type `notify.mobile_app` and note the entry for
your phone, e.g. `notify.mobile_app_pixel_8`.

### Add the automations

**Settings → Automations & Scenes → Create automation → ⋮ → Edit in YAML**,
paste the first automation, save, and repeat for the second. Replace
`notify.mobile_app_your_phone` in both.

```yaml
alias: "Nordmesh: Meshnet lost"
description: Notify when the Pi loses Meshnet for 3 minutes
triggers:
  - trigger: state
    entity_id: binary_sensor.nordmesh_meshnet
    to: ["off", "unavailable"]
    for: "00:03:00"
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: Meshnet unavailable
      message: >-
        {% if trigger.to_state.state == 'unavailable' %}
          The Pi isn't responding. It may be off or disconnected from your network.
        {% else %}
          {{ states('sensor.nordmesh_meshnet_status') }}
        {% endif %}
mode: single
```

```yaml
alias: "Nordmesh: Meshnet restored"
description: Notify when Meshnet comes back after an outage
triggers:
  - trigger: state
    entity_id: binary_sensor.nordmesh_meshnet
    from: ["off", "unavailable"]
    to: "on"
conditions:
  # Only after outages long enough to have triggered the alert above.
  - condition: template
    value_template: >-
      {{ (trigger.to_state.last_changed - trigger.from_state.last_changed).total_seconds() >= 180 }}
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: Meshnet restored
      message: Meshnet is running again on the Pi.
mode: single
```

The 3-minute delay keeps brief hiccups, like the service restarting during an
update, from sending alerts. To tune it, change `for:` and the `180` together.

### Test it

Click **Disable Meshnet** in Nordmesh. The binary sensor turns off within a
minute and the notification arrives three minutes later. Enable Meshnet again
to get the "restored" message.

Turning Meshnet off on purpose triggers the alert too. That's expected.

### What alerts can't catch

Nordmesh reads Meshnet's state from the NordVPN app on the Pi. If the Pi's
internet connection drops while NordVPN still reports Meshnet as on, the
health check says `ok`.

---

## 4. Troubleshooting

Start with the `curl` check from [Before you start](#check-that-home-assistant-can-reach-the-pi).
Drop `-s` and add `-v` to see the error, then check the exit code with `echo $?`:

| Symptom | Cause | Fix |
|---|---|---|
| `curl` exit code `28` (timed out) | Meshnet's firewall on the Pi drops connections from your home network | On the Pi: `nordvpn set lan-discovery on`. Nordmesh 0.2.2+ turns this on when you enable Meshnet. |
| `curl` exit code `28`, LAN discovery already on | Wrong IP, or HA and the Pi are on different networks (guest Wi‑Fi, VLAN) | Compare with `hostname -I`; put both on the same network |
| `curl` exit code `7` (connection refused) | Wrong port: native installs listen on port 80, not 5000 | Use `http://<pi-ip>` without `:5000` |
| Panel shows **502: Bad Gateway** | Home Assistant can't reach the Pi | Same as the `curl` failures above |
| Panel shows **Can't Connect to NordVPN** right away, but `http://<pi-ip>` works at home | The Pi runs a Nordmesh version older than 0.2.1, which doesn't understand ingress | Update the Pi (`git pull` and restart), then hard-refresh the panel |
| Panel shows **Can't Connect to NordVPN**, and so does `http://<pi-ip>` | NordVPN itself is down on the Pi | Follow the steps on the error screen |
| Binary sensor stays **unavailable** | Same reachability problem, or `/api/health` missing (Nordmesh older than 0.2.4) | Check `curl http://<pi-ip>/api/health` from HA |
| Panel worked, stopped after a Pi reboot | The Pi got a new IP | Reserve its IP in your router and update `configuration.yaml` |

To check what Nordmesh sees, run this on the Pi:

```bash
cd ~/Documents/nordmesh-pi && git describe --tags         # installed version
curl -s -H "X-Ingress-Path: /api/ingress/nordmesh" http://localhost/ | grep "const BASE_PATH"
nordvpn settings | grep -i lan                            # LAN discovery
```

### Reaching Home Assistant through Meshnet

If you can't reach Home Assistant from outside yet, Meshnet can do it. Install
the NordVPN app on your phone, log in with the same account, and enable
Meshnet. In Nordmesh, find your phone under **Peers** and turn on **Local
Network**. Away from home, your phone can then open Home Assistant at its
usual address (e.g. `http://192.168.1.20:8123`) through the Pi.

This makes Meshnet the path you'd use to fix Meshnet. If it breaks while you're
away, you'll have to fix it from home.

### Restricting who may embed Nordmesh

By default any site may embed Nordmesh in an iframe. To limit that, set
`ALLOWED_FRAME_ANCESTORS` to your HA address, e.g. `http://192.168.1.20:8123`,
or `none` to forbid embedding. The ingress panel serves Nordmesh from Home
Assistant's own address, so this mainly matters for the Webpage dashboard.

---

## 5. Removing the integration

1. Delete the `ingress:` and `rest:` blocks from `configuration.yaml`.
2. Delete the two "Nordmesh" automations.
3. Restart Home Assistant. Optionally uninstall **Ingress** from HACS.

Nothing needs undoing on the Pi. LAN discovery can stay on; it's harmless
without Home Assistant. To turn it off: `nordvpn set lan-discovery off`.
