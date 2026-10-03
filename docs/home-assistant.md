# Opening the UI in Home Assistant

The Meshnet Manager has no login of its own, so keep it on your local network
and let Home Assistant be the way in. Pick one of the two setups below.

| | Ingress panel (recommended) | Webpage dashboard |
|---|---|---|
| Works away from home | Yes — wherever Home Assistant works | No |
| Works when HA is opened over HTTPS | Yes | No (browsers block the http iframe) |
| Protected by your HA login | Yes | Only at home, where the Pi is reachable anyway |
| Extra software | [hass_ingress](https://github.com/lovelylain/hass_ingress) (HACS) | None |

## Ingress panel (recommended)

The [hass_ingress](https://github.com/lovelylain/hass_ingress) integration makes
Home Assistant proxy the UI, just like it does for add-ons. Your browser only
ever talks to Home Assistant, so the panel works through whatever remote access
you already use for HA (Nabu Casa, your own HTTPS domain, a VPN) and inherits
its HTTPS and login. The Pi itself never has to be reachable from the internet.

1. In **HACS**, search for **Ingress** and download it (or follow the manual
   install in its README).
2. Add this to `configuration.yaml`, using the Pi's LAN address:

   ```yaml
   ingress:
     nordmesh:
       title: Meshnet
       icon: mdi:vpn
       url: http://192.168.1.50:5000
       require_admin: true
   ```

3. Restart Home Assistant. **Meshnet** appears in the sidebar.

Later edits can be applied from **Developer Tools → YAML → Ingress** without a
restart.

The UI detects the `X-Ingress-Path` header that Home Assistant sends and keeps
its API calls under the panel's path, so nothing needs configuring on the Pi.

`require_admin: true` hides the panel from non-admin HA users. Drop it if
everyone in your household should be able to manage Meshnet.

## Webpage dashboard (home network only)

**Settings → Dashboards → Add Dashboard → Webpage**, URL
`http://192.168.1.50:5000`.

The page loads in your browser, not on the HA server, so this only works when
your device can reach the Pi directly — and only if you opened Home Assistant
over plain `http://`. On an `https://` HA page the browser blocks the embedded
`http://` page as mixed content.

## No remote access to Home Assistant yet?

You already have a VPN: Meshnet. Install the NordVPN app on your phone, log in
with the same account, and enable Meshnet. In this UI, open the phone's peer
entry and turn on **Allow local network access**. Away from home, your phone
can then open Home Assistant at its usual LAN address (e.g.
`http://192.168.1.20:8123`) through the Pi, and either setup above works.

Keep in mind that this makes Meshnet the path you would use to repair Meshnet.
If it breaks while you're away, you'll have to fix it from home.

## Restricting who may embed the UI

The UI allows embedding from any origin by default. To narrow it, set
`ALLOWED_FRAME_ANCESTORS` to your HA origin, e.g. `http://192.168.1.20:8123`,
or `none` to forbid embedding. With the ingress panel the UI is served from
Home Assistant's own origin, so this setting rarely matters there.
