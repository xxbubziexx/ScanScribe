#!/usr/bin/env bash
set -e

echo "============================================================"
echo "           ScanScribe Public Safety Ingest Node             "
echo "                 Container Initializing                     "
echo "============================================================"

# Ensure directories exist and have proper permissions
mkdir -p "${DATA_DIR:-/app/data}" "${LOG_DIR:-/app/logs}" "${INGEST_DIR:-/app/ingest}" "${OUTPUT_DIR:-/app/audio_storage}" "${MODEL_PATH:-/app/models}"

# Restore compiled React frontend if shadowed by a host volume mount (e.g. - ./app:/app/app)
if [ ! -f /app/app/frontend/dist/index.html ]; then
    echo "[*] Restoring pre-built React frontend assets to /app/app/frontend/dist..."
    mkdir -p /app/app/frontend/dist
    if [ -d /opt/frontend_dist ]; then
        cp -r /opt/frontend_dist/* /app/app/frontend/dist/
        echo "[✓] Frontend assets restored."
    else
        echo "[!] Warning: /opt/frontend_dist not found. Web UI might not be served."
    fi
fi

# Run database schema migrations automatically
echo "[*] Checking and applying database migrations (alembic upgrade head)..."
python -m alembic upgrade head || {
    echo "[!] Warning: Alembic migration encountered an error or was skipped. Proceeding with application startup..."
}

echo "[✓] Environment initialization complete. Starting ScanScribe service..."
echo "============================================================"

# Execute target command as PID 1 to ensure proper SIGTERM/SIGINT propagation
exec "$@"
