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
NER_MODEL="${NER_MODEL:-xxbubziexx/incident_ner_v1}"
BRANCH="${BRANCH:-snapshot}"
NON_INTERACTIVE="${NON_INTERACTIVE:-false}"

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
    --ner-model) NER_MODEL="$2"; shift 2 ;;
    --autostart) AUTOSTART="$2"; shift 2 ;;
    --custom-model-url) CUSTOM_MODEL_URL="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --non-interactive|--silent|-y) NON_INTERACTIVE="true"; shift ;;
    *) shift ;;
  esac
done

echo ""
echo "============================================================"
echo "          ScanScribe Native Linux Station Installer         "
echo "        AI-Powered Public Safety Radio Transcription        "
echo "============================================================"
echo ""

# Hardware Auto-detection for intelligent recommendations
DETECTED_GPU="false"
if command -v nvidia-smi &>/dev/null; then
  DETECTED_GPU="true"
fi

DETECTED_CORES=$(nproc 2>/dev/null || getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)
RECOMMENDED_WORKERS=$(( DETECTED_CORES > 8 ? 8 : (DETECTED_CORES < 2 ? 2 : DETECTED_CORES) ))
RECOMMENDED_MODE=$([ "$DETECTED_GPU" = "true" ] && echo "cuda" || echo "cpu")

prompt_user() {
  local prompt_text="$1"
  local default_val="$2"
  local default_hint="${3:-}"
  local hint="$default_val"
  if [ -n "$default_hint" ]; then
    hint="$default_val ($default_hint)"
  fi
  echo -e "\033[1;37m$prompt_text\033[0m" >&2
  echo -e "   \033[0;90m[Default: $hint] -> Press ENTER to keep default\033[0m" >&2
  local user_val=""
  read -r -p "   Selection: " user_val
  if [ -z "$user_val" ]; then
    echo -e "   \033[0;32m-> Kept default: $default_val\033[0m" >&2
    echo "$default_val"
  else
    echo -e "   \033[0;36m-> Selected: $user_val\033[0m" >&2
    echo "$user_val"
  fi
}

if [ -t 0 ] && [ "$NON_INTERACTIVE" != "true" ]; then
  echo "============================================================"
  echo "               Interactive Installation Setup               "
  echo "============================================================"
  echo "  Tip: Press ENTER on any prompt to accept the recommended default."
  echo ""

  # 1. Install Directory
  INSTALL_DIR=$(prompt_user "1. Installation Directory" "$INSTALL_DIR")
  echo ""

  # 2. Ingest Directory
  DEFAULT_INGEST="${INGEST_DIR:-$INSTALL_DIR/ingest}"
  INGEST_DIR=$(prompt_user "2. Scanner Audio Ingest Directory (SDRTrunk/ProScan recordings)" "$DEFAULT_INGEST")
  echo ""

  # 3. Compute Mode
  DEFAULT_MODE="${MODE:-$RECOMMENDED_MODE}"
  MODE_HINT=$([ "$DETECTED_GPU" = "true" ] && echo "NVIDIA GPU detected" || echo "CPU mode detected")
  MODE_CHOICE=$(prompt_user "3. Hardware Acceleration Mode (cpu / cuda)" "$DEFAULT_MODE" "$MODE_HINT")
  MODE=$([ "$MODE_CHOICE" = "cuda" ] && echo "cuda" || echo "cpu")
  echo ""

  # 4. Whisper Model
  echo "4. Whisper Speech-to-Text Model:"
  echo "   [1] sepiaapps/whisper-small.en-police-radio            (CrimeRadar Police Radio - Recommended Default)"
  echo "   [2] xxbubziexx/whisper-small-public-safety-v2-FINAL   (ScanScribe Public Safety v2 Final)"
  echo "   [3] openai/whisper-base                               (Lightweight / Low-RAM)"
  echo "   [4] openai/whisper-small                              (Standard General English)"
  echo "   [5] openai/whisper-medium                             (High Accuracy / Requires 8GB+ VRAM)"
  echo "   [6] Custom Hugging Face model repository"
  MODEL_CHOICE=$(prompt_user "   Choose model [1-6] or enter Model ID" "1" "sepiaapps/whisper-small.en-police-radio")

  case "$MODEL_CHOICE" in
    1)
      MODEL="whisper-small.en-police-radio"
      CUSTOM_MODEL_URL="sepiaapps/whisper-small.en-police-radio"
      ;;
    2)
      MODEL="whisper-small-public-safety-v2-FINAL"
      CUSTOM_MODEL_URL="xxbubziexx/whisper-small-public-safety-v2-FINAL"
      ;;
    3)
      MODEL="whisper-base"
      CUSTOM_MODEL_URL="openai/whisper-base"
      ;;
    4)
      MODEL="whisper-small"
      CUSTOM_MODEL_URL="openai/whisper-small"
      ;;
    5)
      MODEL="whisper-medium"
      CUSTOM_MODEL_URL="openai/whisper-medium"
      ;;
    6)
      CUSTOM_INPUT=$(prompt_user "   Enter Hugging Face Model ID" "xxbubziexx/whisper-small-public-safety-v2-FINAL")
      CUSTOM_MODEL_URL="$CUSTOM_INPUT"
      MODEL=$(basename "$CUSTOM_INPUT")
      ;;
    *)
      if [[ "$MODEL_CHOICE" == *"/"* ]]; then
        CUSTOM_MODEL_URL="$MODEL_CHOICE"
        MODEL=$(basename "$MODEL_CHOICE")
      else
        MODEL="$MODEL_CHOICE"
      fi
      ;;
  esac
  echo ""

  # 5. Incident NER Model
  echo "5. Public Safety Incident Entity Extraction (NER):"
  echo "   [1] xxbubziexx/incident_ner_v1  (Recommended Default: Unit, Address, Call Type Extraction)"
  echo "   [2] Custom Hugging Face model ID or path"
  echo "   [3] None (Disable NER)"
  NER_CHOICE=$(prompt_user "   Choose NER option [1-3]" "1" "xxbubziexx/incident_ner_v1")

  case "$NER_CHOICE" in
    1)
      NER_MODEL="xxbubziexx/incident_ner_v1"
      ;;
    2)
      NER_MODEL=$(prompt_user "   Enter NER model repository ID or path" "xxbubziexx/incident_ner_v1")
      ;;
    3)
      NER_MODEL=""
      ;;
    *)
      NER_MODEL="$NER_CHOICE"
      ;;
  esac
  echo ""

  # 6. Worker Threads
  DEFAULT_WORKERS=$([ "$WORKERS" -gt 0 ] && echo "$WORKERS" || echo "$RECOMMENDED_WORKERS")
  WORKERS=$(prompt_user "6. Parallel Worker Threads (transcription concurrency)" "$DEFAULT_WORKERS" "Auto-detected $DETECTED_CORES CPU cores")
  echo ""

  # 7. Web Port
  DEFAULT_PORT=$([ "$PORT" -gt 0 ] && echo "$PORT" || echo "8000")
  PORT=$(prompt_user "7. Web Dashboard Port" "$DEFAULT_PORT")
  echo ""

  # Confirmation Summary
  echo ""
  echo "============================================================"
  echo "              Installation Profile Confirmation            "
  echo "============================================================"
  echo "  Install Directory : $INSTALL_DIR"
  echo "  Ingest Directory  : $INGEST_DIR"
  echo "  Compute Mode      : $MODE"
  echo "  Whisper Model     : $MODEL"
  echo "  Incident NER      : ${NER_MODEL:-Disabled}"
  echo "  Worker Threads    : $WORKERS"
  echo "  Web Port          : $PORT"
  echo "============================================================"
  CONFIRM=$(prompt_user "Proceed with installation? (Y/N)" "Y")
  if [[ "$CONFIRM" =~ ^[Nn] ]]; then
    echo "[-] Installation cancelled by user."
    exit 0
  fi
  echo ""
else
  # Non-interactive defaults
  [ -z "$MODEL" ] && MODEL="whisper-small.en-police-radio"
  [ -z "$CUSTOM_MODEL_URL" ] && [ "$MODEL" = "whisper-small.en-police-radio" ] && CUSTOM_MODEL_URL="sepiaapps/whisper-small.en-police-radio"
  [ "$WORKERS" -le 0 ] && WORKERS=$RECOMMENDED_WORKERS
  [ -z "$INGEST_DIR" ] && INGEST_DIR="$INSTALL_DIR/ingest"
fi

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
  echo "    Installing application packages from requirements.txt..."
  "$UV_CMD" pip install -r "$INSTALL_DIR/requirements.txt" --python "$VENV_PY"
fi

if [ -f "$INSTALL_DIR/pyproject.toml" ]; then
  echo "    Registering ScanScribe package in virtual environment..."
  "$UV_CMD" pip install -e "$INSTALL_DIR" --python "$VENV_PY"
fi

# Explicit safety guarantee: Ensure core web runtime is present
echo "    Verifying core runtime dependencies (uvicorn, fastapi, slowapi, alembic, httpx)..."
"$UV_CMD" pip install "uvicorn[standard]>=0.30.0" "fastapi>=0.115.0" "slowapi>=0.1.9" "alembic>=1.13.3" "httpx>=0.27.2" "huggingface-hub>=0.23.0" "pyyaml>=6.0" --python "$VENV_PY" --quiet



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
  elif [ "$MODEL" = "whisper-small-public-safety-v2-FINAL" ]; then
    HF_REPO="xxbubziexx/whisper-small-public-safety-v2-FINAL"
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

# Pre-load Incident NER model
if [ -n "$NER_MODEL" ]; then
  echo "    Pre-loading Incident NER model ($NER_MODEL)..."
  NER_DIR_NAME=$(basename "$NER_MODEL")
  NER_DIR="$INSTALL_DIR/models/$NER_DIR_NAME"
  if [ ! -d "$NER_DIR" ] || [ -z "$(ls -A "$NER_DIR" 2>/dev/null)" ]; then
    "$VENV_PY" - <<EOF
import sys
from huggingface_hub import snapshot_download
print("[*] Downloading $NER_MODEL...")
try:
    snapshot_download(repo_id="$NER_MODEL", local_dir="$NER_DIR", ignore_patterns=['*.msgpack', '*.h5', '*.ot'], local_dir_use_symlinks=False)
    print("[+] Incident NER model download complete!")
except Exception as e:
    print(f"[!] Incident NER model download warning: {e}", file=sys.stderr)
EOF
  fi
else
  NER_DIR_NAME=""
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
if "$NER_DIR_NAME":
    data["events_pipeline"]["ner_model_path"] = "$INSTALL_DIR/models/$NER_DIR_NAME"
    data["events_pipeline"]["enabled"] = True
else:
    data["events_pipeline"]["enabled"] = False
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
