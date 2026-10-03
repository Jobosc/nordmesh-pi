#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "Syncing dependencies..."
uv sync

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-5000}"
echo "Starting NordVPN Meshnet Manager on http://${HOST}:${PORT}"
PYTHONPATH=src uv run gunicorn -w 2 -b "${HOST}:${PORT}" app:app
