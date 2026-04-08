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

# Run the app
echo "Starting NordVPN Meshnet Manager on http://0.0.0.0:5000"
uv run python app.py
