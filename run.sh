#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "Syncing dependencies..."
# Keep the Cloudflare Access verification dependency installed when Access is
# configured — a plain "uv sync" prunes extras, which would make the app refuse
# all Cloudflare traffic after a restart.
if [[ -n "${CF_ACCESS_TEAM_DOMAIN:-}" && -n "${CF_ACCESS_AUD:-}" ]]; then
    echo "Cloudflare Access configured — including the 'cloudflare' extra"
    uv sync --extra cloudflare
else
    uv sync
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-5000}"
echo "Starting NordVPN Meshnet Manager on http://${HOST}:${PORT}"
PYTHONPATH=src uv run gunicorn -w 2 -b "${HOST}:${PORT}" app:app
