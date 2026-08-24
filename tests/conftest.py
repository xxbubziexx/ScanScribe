"""Pytest configuration and global fixtures."""
import os
import sys
import tempfile
import yaml
from unittest.mock import MagicMock

# Mock ML modules that are container-only
for mod in [
    'torch', 'torchaudio', 'transformers', 'accelerate',
    'soundfile', 'librosa', 'audioread', 'silero_vad', 'openai'
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

test_dir = tempfile.mkdtemp(prefix="scanscribe_test_")
config_file = os.path.join(test_dir, "config.yml")
ingest_dir = os.path.join(test_dir, "ingest")
output_dir = os.path.join(test_dir, "audio_storage")
log_dir = os.path.join(test_dir, "logs")
db_path = os.path.join(test_dir, "scanscribe.db")
models_dir = os.path.join(test_dir, "models")

for d in [ingest_dir, output_dir, log_dir, models_dir]:
    os.makedirs(d, exist_ok=True)

with open(config_file, "w") as f:
    yaml.dump({
        "model": {"name": "test-model", "path": models_dir, "workers": 1, "device": "cpu"},
        "watcher": {"auto_start": False},
        "storage": {"save_audio_for_playback": True, "retention_days": 30, "cleanup_hour": 3},
        "events_pipeline": {"enabled": False},
    }, f)

os.environ["CONFIG_PATH"] = config_file
os.environ["INGEST_DIR"] = ingest_dir
os.environ["OUTPUT_DIR"] = output_dir
os.environ["LOG_DIR"] = log_dir
os.environ["DB_PATH"] = db_path
os.environ["SECRET_KEY"] = "test-secret-key-12345"

try:
    from app.config import get_settings
    get_settings.cache_clear()
except ImportError:
    pass
