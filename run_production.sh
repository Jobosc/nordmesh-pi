#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Check if uv is available
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Sync dependencies
echo "Syncing dependencies..."
uv sync

# Run with gunicorn for production
echo "Starting NordVPN Meshnet Manager (production) on http://127.0.0.1:5000"
uv run gunicorn -w 2 -b 127.0.0.1:5000 app:app
