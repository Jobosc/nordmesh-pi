#!/usr/bin/env bash
# Setup script for NordVPN Meshnet Manager on Raspberry Pi (Raspberry Pi OS / Debian)
# Usage: sudo ./setup.sh
set -euo pipefail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
step()  { echo -e "\n${BOLD}==> $*${NC}"; }

# ---------------------------------------------------------------------------
# Must run as root (sudo)
# ---------------------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
    error "Run this script with sudo: sudo $0"
    exit 1
fi

# ---------------------------------------------------------------------------
# Config — override via env vars before calling sudo if needed
# ---------------------------------------------------------------------------
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_USER="${SUDO_USER:-pi}"
APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"
APP_PORT="${PORT:-5000}"
SERVICE_NAME="nordvpn-meshnet"

info "App directory : $APP_DIR"
info "Running as    : $APP_USER (home: $APP_HOME)"
info "App port      : $APP_PORT"

# ---------------------------------------------------------------------------
# 1. System packages
# ---------------------------------------------------------------------------
step "Updating system packages"
apt-get update -q
apt-get install -y -q curl ca-certificates gpg apt-transport-https \
    debian-keyring debian-archive-keyring

# ---------------------------------------------------------------------------
# 2. uv (Python package manager)
# ---------------------------------------------------------------------------
step "Installing uv"
UV_BIN="$APP_HOME/.local/bin/uv"
if command -v uv &>/dev/null || [[ -x "$UV_BIN" ]]; then
    info "uv already installed — skipping"
else
    sudo -u "$APP_USER" bash -c \
        'curl -LsSf https://astral.sh/uv/install.sh | sh'
fi

# ---------------------------------------------------------------------------
# 3. NordVPN
# ---------------------------------------------------------------------------
step "Installing NordVPN"
if command -v nordvpn &>/dev/null; then
    info "NordVPN already installed — skipping"
else
    # Download to a temp file to avoid bash process substitution issues
    TMP_INSTALLER="$(mktemp /tmp/nordvpn-install.XXXXXX.sh)"
    curl -sSf https://downloads.nordcdn.com/apps/linux/install.sh -o "$TMP_INSTALLER"
    chmod +x "$TMP_INSTALLER"
    bash "$TMP_INSTALLER" --nordaccount
    rm -f "$TMP_INSTALLER"
fi

# Add app user to the nordvpn group (required to run nordvpn CLI)
if groups "$APP_USER" | grep -qw nordvpn; then
    info "$APP_USER is already in the nordvpn group"
else
    usermod -aG nordvpn "$APP_USER"
    warn "$APP_USER added to the nordvpn group — a re-login (or reboot) is required for this to take effect"
fi

# ---------------------------------------------------------------------------
# 4. Caddy (reverse proxy)
# ---------------------------------------------------------------------------
step "Installing Caddy"
if command -v caddy &>/dev/null; then
    info "Caddy already installed — skipping"
else
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | tee /etc/apt/sources.list.d/caddy-stable.list > /dev/null
    apt-get update -q
    apt-get install -y -q caddy
fi

# ---------------------------------------------------------------------------
# 5. Caddy configuration
# ---------------------------------------------------------------------------
step "Configuring Caddy"
# Caddy acts as a reverse proxy on port 80.
# The app itself listens on localhost only — Caddy is the public entry point.
cat > /etc/caddy/Caddyfile <<EOF
# NordVPN Meshnet Manager — reverse proxy
# Replace ":80" with your domain (e.g. "meshnet.example.com") to get
# automatic HTTPS via Let's Encrypt.
:80 {
    reverse_proxy localhost:${APP_PORT}
}
EOF
info "Caddyfile written to /etc/caddy/Caddyfile"

# ---------------------------------------------------------------------------
# 6. App dependencies
# ---------------------------------------------------------------------------
step "Syncing app dependencies"
sudo -u "$APP_USER" bash -c "cd '$APP_DIR' && '$UV_BIN' sync"

# ---------------------------------------------------------------------------
# 7. Systemd service for the app
# ---------------------------------------------------------------------------
step "Installing systemd service ($SERVICE_NAME)"
# The app listens on localhost — Caddy handles external traffic.
cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=NordVPN Meshnet Manager
After=network.target nordvpnd.service
Wants=nordvpnd.service

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment=HOST=127.0.0.1
Environment=PORT=${APP_PORT}
ExecStart=${APP_DIR}/run_production.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

# ---------------------------------------------------------------------------
# 8. Enable and start services
# ---------------------------------------------------------------------------
step "Enabling services on boot"

systemctl enable nordvpnd
systemctl start nordvpnd && info "nordvpnd started" || warn "nordvpnd failed to start — may need a reboot"

systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME" && info "$SERVICE_NAME started" || warn "$SERVICE_NAME failed to start — check: journalctl -u $SERVICE_NAME"

systemctl enable caddy
systemctl restart caddy && info "caddy started" || warn "caddy failed to start — check: journalctl -u caddy"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
PI_IP="$(hostname -I | awk '{print $1}')"
echo ""
echo -e "${GREEN}${BOLD}Setup complete!${NC}"
echo ""
echo "  Web UI   : http://${PI_IP}"
echo "  App logs : journalctl -fu ${SERVICE_NAME}"
echo "  Caddy    : journalctl -fu caddy"
echo ""
if groups "$APP_USER" | grep -qw nordvpn; then
    : # group already active
else
    warn "Remember to log out and back in (or reboot) for the nordvpn group to take effect before logging in via the UI."
fi
