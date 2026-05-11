#!/usr/bin/env bash
set -euo pipefail

# NordVPN daemon must be running before the CLI (and the web app) can work.
echo "[entrypoint] Starting nordvpnd..."
nordvpnd &

echo "[entrypoint] Waiting for nordvpnd to become ready..."
for i in $(seq 1 30); do
    if nordvpn status >/dev/null 2>&1; then
        echo "[entrypoint] nordvpnd ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "[entrypoint] Warning: nordvpnd did not respond after 30 s — proceeding anyway."
    fi
    sleep 1
done

echo "[entrypoint] Starting NordVPN Meshnet Manager on ${HOST:-0.0.0.0}:${PORT:-5000}..."
exec uv run gunicorn \
    --workers 2 \
    --bind "${HOST:-0.0.0.0}:${PORT:-5000}" \
    --access-logfile - \
    --error-logfile - \
    --pythonpath src \
    app:app
