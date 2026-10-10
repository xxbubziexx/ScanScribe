#!/usr/bin/env bash
# ==============================================================================
# ScanScribe Native Linux / macOS Uninstaller
# ==============================================================================
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
PURGE=false
YES=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --purge) PURGE=true; shift ;;
    -y|--yes) YES=true; shift ;;
    *) shift ;;
  esac
done

echo ""
echo "============================================================"
echo "          ScanScribe Linux / macOS Uninstaller              "
echo "============================================================"
echo "Target Directory: $INSTALL_DIR"
echo ""
echo "This will:"
echo "  1. Stop any running ScanScribe process"
echo "  2. Remove systemd user service (if registered)"
echo "  3. Clear all Python bytecode caches (__pycache__, *.pyc)"
echo "  4. Remove isolated virtual environment (.venv) & dependencies"
if [ "$PURGE" = true ]; then
  echo "  [!] PURGE: Will permanently delete database, audio recordings, models, and config!"
else
  echo "  [i] User database, audio recordings, models, and config will be PRESERVED."
fi
echo ""

if [ "$YES" = false ]; then
  read -r -p "Are you sure you want to proceed with uninstallation? (y/N): " confirm
  if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Uninstallation cancelled."
    exit 0
  fi
fi

# 1. Stop server
echo "[1/4] Stopping ScanScribe..."
if [ -f "$INSTALL_DIR/bin/scanscribe" ]; then
  "$INSTALL_DIR/bin/scanscribe" stop 2>/dev/null || true
fi

# 2. Remove systemd user service
echo "[2/4] Checking systemd user service..."
SERVICE_FILE="$HOME/.config/systemd/user/scanscribe.service"
if [ -f "$SERVICE_FILE" ]; then
  systemctl --user disable --now scanscribe 2>/dev/null || true
  rm -f "$SERVICE_FILE"
  systemctl --user daemon-reload 2>/dev/null || true
  echo "    [✓] Removed systemd service."
fi

# 3. Clear Python caches
echo "[3/4] Clearing Python bytecode caches..."
find "$INSTALL_DIR" -type d -name "__pycache__" -not -path "*/.git/*" -not -path "*/.venv/*" -exec rm -rf {} + 2>/dev/null || true
find "$INSTALL_DIR" -type f \( -name "*.pyc" -o -name "*.pyo" \) -not -path "*/.git/*" -not -path "*/.venv/*" -delete 2>/dev/null || true
echo "    [✓] Bytecode caches cleared."

# Optional Purge
if [ "$PURGE" = true ]; then
  echo "[-] Purging data, recordings, and config..."
  rm -rf "$INSTALL_DIR/data" "$INSTALL_DIR/audio_storage" "$INSTALL_DIR/models" "$INSTALL_DIR/logs"
  rm -f "$INSTALL_DIR/.env" "$INSTALL_DIR/config.yml"
  echo "    [✓] Database, audio storage, models, and config purged."
fi

# 4. Remove .venv
echo "[4/4] Removing virtual environment (.venv)..."
rm -rf "$INSTALL_DIR/.venv"
rm -f "$INSTALL_DIR/.scanscribe.pid"
echo "    [✓] Virtual environment removed."

echo ""
echo "============================================================"
echo "        ScanScribe has been uninstalled successfully.       "
echo "============================================================"
echo ""
