#!/usr/bin/env bash
# ==============================================================================
# ScanScribe Native Linux / macOS Installer
# ==============================================================================
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$HOME/scanscribe}"
INGEST_DIR="${INGEST_DIR:-$INSTALL_DIR/ingest}"
MODE="${MODE:-cpu}"
RAM="${RAM:-8}"
WORKERS="${WORKERS:-0}"
PORT="${PORT:-8000}"
MODEL="${MODEL:-}"
AUTOSTART="${AUTOSTART:-true}"
CUSTOM_MODEL_URL="${CUSTOM_MODEL_URL:-}"
BRANCH="${BRANCH:-snapshot}"

# Parse command line flags if passed
while [[ $# -gt 0 ]]; do
  case $1 in
    --install-dir) INSTALL_DIR="$2"; shift 2 ;;
    --ingest-dir) INGEST_DIR="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --ram) RAM="$2"; shift 2 ;;
    --workers) WORKERS="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --autostart) AUTOSTART="$2"; shift 2 ;;
    --custom-model-url) CUSTOM_MODEL_URL="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    *) shift ;;
  esac
done

echo ""
echo "============================================================"
echo "          ScanScribe Native Linux Station Installer         "
echo "        AI-Powered Public Safety Radio Transcription        "
echo "============================================================"
echo ""

# 1. Spec Auto-tuning
if [ -z "$MODEL" ]; then
  MODEL="whisper-small.en-police-radio"
fi

if [ "$WORKERS" -le 0 ]; then
  if [ "$RAM" -le 4 ]; then
    WORKERS=2
  else
    WORKERS=4
  fi
fi

echo "[-] Installation Profile:"
echo "    Install Directory : $INSTALL_DIR"
echo "    Ingest Directory  : $INGEST_DIR"
echo "    Compute Mode      : $MODE"
echo "    System RAM Profile: ${RAM}GB"
echo "    Whisper Model     : $MODEL"
echo "    Worker Threads    : $WORKERS"
echo "    Web Port          : $PORT"
echo ""

# 2. Directory Creation
echo "[1/7] Creating directories..."
mkdir -p "$INSTALL_DIR" "$INSTALL_DIR/bin" "$INSTALL_DIR/data" "$INSTALL_DIR/logs" "$INSTALL_DIR/models" "$INSTALL_DIR/audio_storage" "$INGEST_DIR"

# 3. Source Code Setup
echo "[2/7] Fetching application code..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/app/main.py" ] && [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
  cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/"
elif [ ! -f "$INSTALL_DIR/app/main.py" ]; then
  if command -v git &>/dev/null; then
    git clone -b "$BRANCH" https://github.com/xxbubziexx/scanscribe.git "$INSTALL_DIR"
  else
    curl -fsSL "https://github.com/xxbubziexx/scanscribe/archive/refs/heads/$BRANCH.tar.gz" | tar -xz -C "$INSTALL_DIR" --strip-components=1
  fi
fi

cd "$INSTALL_DIR"

# 4. Bootstrap UV
echo "[3/7] Setting up isolated Python runtime with uv..."
BIN_DIR="$INSTALL_DIR/bin"
UV_EXE="$BIN_DIR/uv"

if ! command -v uv &>/dev/null && [ ! -f "$UV_EXE" ]; then
  echo "    Downloading standalone uv..."
  curl -fsSL https://astral.sh/uv/install.sh | env CARGO_DIST_FORCE_INSTALL_DIR="$BIN_DIR" sh
fi

if command -v uv &>/dev/null; then
  UV_CMD="uv"
else
  UV_CMD="$UV_EXE"
fi

"$UV_CMD" python install 3.11 --quiet
"$UV_CMD" venv "$INSTALL_DIR/.venv" --python 3.11 --quiet
VENV_PY="$INSTALL_DIR/.venv/bin/python"

# 5. Install PyTorch & Dependencies
echo "[4/7] Installing AI transcription dependencies..."
if [ "$MODE" = "cuda" ]; then
  echo "    Installing CUDA 12.4 PyTorch..."
  "$UV_CMD" pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124 --python "$VENV_PY"
else
  echo "    Installing CPU PyTorch..."
  "$UV_CMD" pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu --python "$VENV_PY"
fi

if [ -f "$INSTALL_DIR/requirements.txt" ]; then
  echo "    Installing application packages..."
  "$UV_CMD" pip install -r "$INSTALL_DIR/requirements.txt" --python "$VENV_PY"
fi

# 6. Check FFmpeg
echo "[5/7] Verifying FFmpeg..."
if ! command -v ffmpeg &>/dev/null; then
  echo "    Notice: FFmpeg not detected in PATH. On Ubuntu/Debian run: sudo apt install -y ffmpeg"
fi

# 7. Model Pre-download
echo "[6/7] Pre-loading Whisper model ($MODEL)..."
MODEL_DIR="$INSTALL_DIR/models/$MODEL"
if [ ! -d "$MODEL_DIR" ] || [ -z "$(ls -A "$MODEL_DIR" 2>/dev/null)" ]; then
  if [ -n "$CUSTOM_MODEL_URL" ]; then
    HF_REPO="$CUSTOM_MODEL_URL"
  elif [ "$MODEL" = "whisper-small.en-police-radio" ]; then
    HF_REPO="sepiaapps/whisper-small.en-police-radio"
  elif [[ "$MODEL" == *"/"* ]]; then
    HF_REPO="$MODEL"
  else
    HF_REPO="openai/$MODEL"
  fi
  "$VENV_PY" - <<EOF
import sys
from huggingface_hub import snapshot_download
print("[*] Downloading $HF_REPO...")
try:
    snapshot_download(repo_id="$HF_REPO", local_dir="$MODEL_DIR", ignore_patterns=['*.msgpack', '*.h5', '*.ot', '*.onnx'], local_dir_use_symlinks=False)
    print("[+] Model download complete!")
except Exception as e:
    print(f"[!] Model download warning: {e}", file=sys.stderr)
EOF
fi

# Pre-load Incident NER model (xxbubziexx/incident_ner_v1)
echo "    Pre-loading Incident NER model (xxbubziexx/incident_ner_v1)..."
NER_DIR="$INSTALL_DIR/models/incident_ner_v1"
if [ ! -d "$NER_DIR" ] || [ -z "$(ls -A "$NER_DIR" 2>/dev/null)" ]; then
  "$VENV_PY" - <<EOF
import sys
from huggingface_hub import snapshot_download
print("[*] Downloading xxbubziexx/incident_ner_v1...")
try:
    snapshot_download(repo_id="xxbubziexx/incident_ner_v1", local_dir="$NER_DIR", ignore_patterns=['*.msgpack', '*.h5', '*.ot'], local_dir_use_symlinks=False)
    print("[+] Incident NER model download complete!")
except Exception as e:
    print(f"[!] Incident NER model download warning: {e}", file=sys.stderr)
EOF
fi

# 8. Configuration & Secrets
echo "[7/7] Generating station configuration and secrets..."
SECRET_KEY="$("$VENV_PY" -c "import secrets; print(secrets.token_hex(32))")"
cat <<EOF > "$INSTALL_DIR/.env"
SECRET_KEY=$SECRET_KEY
PORT=$PORT
INGEST_DIR=$INGEST_DIR
OUTPUT_DIR=$INSTALL_DIR/audio_storage
LOG_DIR=$INSTALL_DIR/logs
DB_PATH=$INSTALL_DIR/data/scanscribe.db
CONFIG_PATH=$INSTALL_DIR/config.yml
EOF

if [ ! -f "$INSTALL_DIR/config.yml" ] && [ -f "$INSTALL_DIR/config.yml.example" ]; then
  cp "$INSTALL_DIR/config.yml.example" "$INSTALL_DIR/config.yml"
fi

"$VENV_PY" - <<EOF
import yaml
config_file = "$INSTALL_DIR/config.yml"
try:
    with open(config_file, "r") as f:
        data = yaml.safe_load(f) or {}
except Exception:
    data = {}
if "model" not in data:
    data["model"] = {}
data["model"]["name"] = "$MODEL"
data["model"]["path"] = "$INSTALL_DIR/models"
data["model"]["device"] = "$MODE"
data["model"]["workers"] = $WORKERS
if "events_pipeline" not in data:
    data["events_pipeline"] = {}
data["events_pipeline"]["ner_model_path"] = "$INSTALL_DIR/models/incident_ner_v1"
with open(config_file, "w") as f:
    yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
EOF

chmod +x "$BIN_DIR/scanscribe"

# PATH export suggestion
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$HOME/.bashrc"
  export PATH="$BIN_DIR:$PATH"
fi

echo ""
echo "============================================================"
echo "               Installation Complete!                       "
echo "============================================================"
echo ""

"$BIN_DIR/scanscribe" start --port "$PORT"

echo ""
echo "Commands:"
echo "  scanscribe status    - Check health and status"
echo "  scanscribe logs      - Live stream logs"
echo "  scanscribe stop      - Stop the background server"
echo "  scanscribe start     - Start the background server"
echo ""
