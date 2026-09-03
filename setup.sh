#!/usr/bin/env bash
# ==============================================================================
# ScanScribe First-Time Setup Launcher (Linux / macOS / Git Bash)
# ==============================================================================

set -e

# Change to the script's directory
cd "$(dirname "$0")"

# Check for Python 3
if command -v python3 &>/dev/null; then
    exec python3 setup.py "$@"
elif command -v python &>/dev/null; then
    exec python setup.py "$@"
else
    echo "Error: Python 3 is required to run the ScanScribe setup wizard."
    echo "Please install Python 3 or follow manual setup steps in README.md."
    exit 1
fi
