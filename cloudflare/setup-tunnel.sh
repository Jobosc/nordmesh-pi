#!/usr/bin/env bash
# Expose the NordVPN Meshnet Manager over HTTPS via a Cloudflare Tunnel.
#
# The Pi dials out to Cloudflare — no router ports are opened and no
# certificates are managed locally. Cloudflare terminates TLS for your
# hostname and forwards requests to the app on localhost.
#
# Usage: sudo ./cloudflare/setup-tunnel.sh meshnet.example.com
#
# Prerequisites:
#   - A domain whose DNS is managed by Cloudflare (free plan is fine)
#   - The Meshnet Manager already installed (see ../setup.sh)
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
step()  { echo -e "\n${BOLD}==> $*${NC}"; }

# ---------------------------------------------------------------------------
# Arguments and preconditions
# ---------------------------------------------------------------------------
HOSTNAME_ARG="${1:-}"
if [[ -z "$HOSTNAME_ARG" ]]; then
    error "Usage: sudo $0 <hostname>     e.g. sudo $0 meshnet.example.com"
    exit 1
fi

if [[ $EUID -ne 0 ]]; then
    error "Run this script with sudo: sudo $0 $HOSTNAME_ARG"
    exit 1
fi

APP_PORT="${PORT:-5000}"
TUNNEL_NAME="${TUNNEL_NAME:-nordmesh}"
SERVICE_NAME="${SERVICE_NAME:-nordvpn-meshnet}"
# cloudflared runs as root via its systemd service, so keep credentials there.
CF_DIR="/root/.cloudflared"
CONFIG_DIR="/etc/cloudflared"

info "Hostname    : $HOSTNAME_ARG"
info "Tunnel name : $TUNNEL_NAME"
info "App port    : $APP_PORT"

# ---------------------------------------------------------------------------
# 1. Install cloudflared
# ---------------------------------------------------------------------------
step "Installing cloudflared"
if command -v cloudflared &>/dev/null; then
    info "cloudflared already installed ($(cloudflared --version 2>/dev/null | head -1)) — skipping"
else
    # Cloudflare's apt repo covers amd64/arm64/armhf on Debian-based systems.
    mkdir -p /usr/share/keyrings
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
        -o /usr/share/keyrings/cloudflare-main.gpg
    echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs 2>/dev/null || echo bookworm) main" \
        > /etc/apt/sources.list.d/cloudflared.list
    apt-get update -q

    if ! apt-get install -y -q cloudflared; then
        warn "apt install failed — falling back to a direct .deb download"
        case "$(dpkg --print-architecture)" in
            arm64)  CF_ARCH=arm64 ;;
            armhf)  CF_ARCH=arm ;;
            amd64)  CF_ARCH=amd64 ;;
            *)      error "Unsupported architecture: $(dpkg --print-architecture)"; exit 1 ;;
        esac
        TMP_DEB="$(mktemp /tmp/cloudflared.XXXXXX.deb)"
        curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}.deb" \
            -o "$TMP_DEB"
        dpkg -i "$TMP_DEB"
        rm -f "$TMP_DEB"
    fi
fi

# ---------------------------------------------------------------------------
# 2. Authenticate with Cloudflare (opens a browser link)
# ---------------------------------------------------------------------------
step "Authenticating with Cloudflare"
if [[ -f "$CF_DIR/cert.pem" ]]; then
    info "Already authenticated ($CF_DIR/cert.pem exists) — skipping"
else
    echo ""
    echo -e "${BOLD}A login URL will be printed below.${NC}"
    echo "Open it on any device, sign in, and pick the domain you want to use."
    echo ""
    cloudflared tunnel login
fi

if [[ ! -f "$CF_DIR/cert.pem" ]]; then
    error "Login did not complete — $CF_DIR/cert.pem is missing."
    exit 1
fi

# ---------------------------------------------------------------------------
# 3. Create the tunnel
# ---------------------------------------------------------------------------
step "Creating tunnel '$TUNNEL_NAME'"

# Parse the JSON rather than grepping it — cloudflared's spacing varies by version.
tunnel_id_by_name() {
    cloudflared tunnel list --output json 2>/dev/null \
        | python3 -c "import json,sys
try:
    tunnels = json.load(sys.stdin)
except Exception:
    tunnels = []
print(next((t['id'] for t in tunnels if t.get('name') == '${TUNNEL_NAME}' and not t.get('deleted_at')), ''))"
}

TUNNEL_ID="$(tunnel_id_by_name)"
if [[ -n "$TUNNEL_ID" ]]; then
    info "Tunnel '$TUNNEL_NAME' already exists — reusing it"
else
    cloudflared tunnel create "$TUNNEL_NAME"
    TUNNEL_ID="$(tunnel_id_by_name)"
fi

if [[ -z "$TUNNEL_ID" ]]; then
    error "Could not determine the tunnel ID for '$TUNNEL_NAME'."
    exit 1
fi
info "Tunnel ID: $TUNNEL_ID"

CRED_FILE="$CF_DIR/${TUNNEL_ID}.json"
if [[ ! -f "$CRED_FILE" ]]; then
    error "Credentials file not found: $CRED_FILE"
    error "Delete the tunnel ('cloudflared tunnel delete $TUNNEL_NAME') and re-run this script."
    exit 1
fi

# ---------------------------------------------------------------------------
# 4. Route DNS
# ---------------------------------------------------------------------------
step "Pointing $HOSTNAME_ARG at the tunnel"
# Creates (or repoints) a proxied CNAME in your Cloudflare zone.
if cloudflared tunnel route dns "$TUNNEL_NAME" "$HOSTNAME_ARG"; then
    info "DNS record for $HOSTNAME_ARG is in place"
else
    warn "Could not create the DNS record automatically."
    warn "Add it by hand in the Cloudflare dashboard:"
    warn "  Type: CNAME   Name: $HOSTNAME_ARG   Target: ${TUNNEL_ID}.cfargotunnel.com   Proxy: on"
fi

# ---------------------------------------------------------------------------
# 5. Tunnel configuration
# ---------------------------------------------------------------------------
step "Writing $CONFIG_DIR/config.yml"
mkdir -p "$CONFIG_DIR"
cat > "$CONFIG_DIR/config.yml" <<EOF
# NordVPN Meshnet Manager — Cloudflare Tunnel
# Regenerate with: sudo ./cloudflare/setup-tunnel.sh $HOSTNAME_ARG
tunnel: ${TUNNEL_ID}
credentials-file: ${CRED_FILE}

ingress:
  - hostname: ${HOSTNAME_ARG}
    service: http://localhost:${APP_PORT}
  # Every tunnel config must end with a catch-all rule.
  - service: http_status:404
EOF
chmod 600 "$CONFIG_DIR/config.yml"
info "Config written"

# ---------------------------------------------------------------------------
# 6. Install and start the service
# ---------------------------------------------------------------------------
step "Installing the cloudflared service"
if systemctl list-unit-files | grep -q '^cloudflared\.service'; then
    info "Service already installed — restarting it"
else
    cloudflared service install
fi

systemctl enable cloudflared
systemctl restart cloudflared

sleep 3
if systemctl is-active --quiet cloudflared; then
    info "cloudflared is running"
else
    error "cloudflared failed to start — check: journalctl -u cloudflared -n 50"
    exit 1
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo -e "${GREEN}${BOLD}Tunnel is up:${NC} https://${HOSTNAME_ARG}"
echo ""
echo -e "${YELLOW}${BOLD}The UI has no login of its own — protect it before you use it.${NC}"
echo ""
echo "  1. Go to Cloudflare Zero Trust -> Access -> Applications -> Add an application"
echo "  2. Type 'Self-hosted', domain: ${HOSTNAME_ARG}"
echo "  3. Add a policy: Action 'Allow', Include -> Emails -> your email address"
echo "  4. Copy the Application Audience (AUD) tag from the app's Overview tab"
echo "  5. Have the Pi verify it too (defence in depth):"
echo ""
echo "       sudo systemctl edit ${SERVICE_NAME:-nordvpn-meshnet}"
echo ""
echo "     and add:"
echo "       [Service]"
echo "       Environment=CF_ACCESS_TEAM_DOMAIN=<your-team>.cloudflareaccess.com"
echo "       Environment=CF_ACCESS_AUD=<the-aud-tag>"
echo ""
echo "     then: cd $(dirname "$(dirname "$(readlink -f "$0")")") && uv sync --extra cloudflare"
echo "           sudo systemctl restart ${SERVICE_NAME:-nordvpn-meshnet}"
echo ""
echo "  Logs: journalctl -fu cloudflared"
echo ""
