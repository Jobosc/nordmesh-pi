#!/usr/bin/env bash
# Reverses everything setup.sh installed.
# The app directory itself is NOT removed — only installed system components.
# Usage: sudo ./teardown.sh
set -euo pipefail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
step()  { echo -e "\n${BOLD}==> $*${NC}"; }

# ---------------------------------------------------------------------------
# Must run as root (sudo)
# ---------------------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}[ERROR]${NC} Run this script with sudo: sudo $0" >&2
    exit 1
fi

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_USER="${SUDO_USER:-pi}"
SERVICE_NAME="nordvpn-meshnet"

echo -e "${BOLD}This will remove:${NC}"
echo "  - systemd service   : $SERVICE_NAME"
echo "  - Caddy             : package + apt repo + Caddyfile"
echo "  - NordVPN           : package + apt repo"
echo "  - nordvpn group     : $APP_USER removed from group"
echo "  - .venv             : $APP_DIR/.venv"
echo ""
echo -e "  ${YELLOW}The app directory ($APP_DIR) will NOT be deleted.${NC}"
echo ""
read -rp "Continue? [y/N] " CONFIRM
if [[ "${CONFIRM,,}" != "y" ]]; then
    echo "Aborted."
    exit 0
fi

# ---------------------------------------------------------------------------
# 1. Stop and disable the app service
# ---------------------------------------------------------------------------
step "Removing $SERVICE_NAME service"
if systemctl list-unit-files "${SERVICE_NAME}.service" &>/dev/null; then
    systemctl stop  "$SERVICE_NAME" 2>/dev/null || true
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    info "$SERVICE_NAME stopped and disabled"
else
    info "$SERVICE_NAME service not found — skipping"
fi
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
if [[ -f "$SERVICE_FILE" ]]; then
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload
    info "Service file removed"
fi

# ---------------------------------------------------------------------------
# 2. Remove Caddy
# ---------------------------------------------------------------------------
step "Removing Caddy"
if command -v caddy &>/dev/null; then
    systemctl stop caddy 2>/dev/null || true
    systemctl disable caddy 2>/dev/null || true
    apt-get purge -y -q caddy
    info "Caddy removed"
else
    info "Caddy not installed — skipping"
fi
# Remove apt source and keyring
rm -f /etc/apt/sources.list.d/caddy-stable.list
rm -f /usr/share/keyrings/caddy-stable-archive-keyring.gpg
# Remove Caddyfile and config directory if empty
rm -f /etc/caddy/Caddyfile
rmdir /etc/caddy 2>/dev/null || true
apt-get update -q

# ---------------------------------------------------------------------------
# 3. Remove NordVPN
# ---------------------------------------------------------------------------
step "Removing NordVPN"

# Remove user from nordvpn group before uninstalling (group is deleted with package)
if groups "$APP_USER" 2>/dev/null | grep -qw nordvpn; then
    gpasswd -d "$APP_USER" nordvpn 2>/dev/null || true
    info "$APP_USER removed from nordvpn group"
fi

if command -v nordvpn &>/dev/null; then
    systemctl stop nordvpnd 2>/dev/null || true
    systemctl disable nordvpnd 2>/dev/null || true
    apt-get purge -y -q nordvpn 2>/dev/null || true
    info "NordVPN removed"
else
    info "NordVPN not installed — skipping"
fi
# Remove NordVPN apt sources (installer adds these)
rm -f /etc/apt/sources.list.d/nordvpn.list
rm -f /usr/share/keyrings/nordvpn-archive-keyring.gpg
apt-get update -q

# ---------------------------------------------------------------------------
# 4. Remove Python virtual environment
# ---------------------------------------------------------------------------
step "Removing .venv"
VENV_DIR="$APP_DIR/.venv"
if [[ -d "$VENV_DIR" ]]; then
    rm -rf "$VENV_DIR"
    info ".venv removed"
else
    info ".venv not found — skipping"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo -e "${GREEN}${BOLD}Teardown complete.${NC}"
echo ""
echo "  uv was NOT removed (it may be used by other projects)."
echo "  To remove uv: rm -rf $APP_HOME/.local/bin/uv ~/.cargo/bin/uv"
echo "  The app directory $APP_DIR was NOT removed."
echo ""
