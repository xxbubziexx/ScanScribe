"""Application configuration management."""
import os
import yaml
from pathlib import Path
from pydantic import BaseModel
from functools import lru_cache
from typing import List, Literal, Optional
import logging

logger = logging.getLogger(__name__)


class ModelConfig(BaseModel):
    """Model configuration."""
    name: str = "xxbubziexx-whisper-small-public-safety"
    path: str = "/app/models"
    workers: int = 3
    device: Literal["cpu", "cuda"] = "cpu"


class WatcherConfig(BaseModel):
    """Server watcher configuration (simplified - just monitors /ingest)."""
    auto_start: bool = True


class StorageConfig(BaseModel):
    """Storage configuration."""
    save_audio_for_playback: bool = True
    retention_days: int = 30
    cleanup_hour: int = 3


# Watchdog Client Configuration (used by scanscribe_client)
class ClientStabilityConfig(BaseModel):
    """Client stability check settings."""
    filesize_check_ms: int = 600
    stability_window_ms: int = 800


class ClientRejectionSizeConfig(BaseModel):
    """Client size rejection settings."""
    enabled: bool = False
    min_kb: int = 100


class ClientRejectionDurationConfig(BaseModel):
    """Client duration rejection settings."""
    enabled: bool = True
    min_seconds: float = 2.5


class ClientRejectionConfig(BaseModel):
    """Client rejection filters."""
    size: ClientRejectionSizeConfig = ClientRejectionSizeConfig()
    duration: ClientRejectionDurationConfig = ClientRejectionDurationConfig()


class WatchdogClientConfig(BaseModel):
    """Watchdog client configuration (fetched by scanscribe_client)."""
    stability: ClientStabilityConfig = ClientStabilityConfig()
    rejection: ClientRejectionConfig = ClientRejectionConfig()
    extensions: List[str] = [".wav", ".mp3"]
    delete_after_upload: bool = True


class TranscriptionConfig(BaseModel):
    """Transcription settings. English-only transcription."""
    beam_size: int = 5
    vad_enabled: bool = False
    vad_threshold: float = 0.5
    vad_speech_pad_ms: int = 150  # Silero: pad each segment by this many ms (reduces cut-off at boundaries)
    vad_min_speech_duration_ms: int = 100  # Silero: keep segments this short or longer (lower = keep more short utterances)
    vad_chunking_mode: Literal["speech", "silence"] = "speech"  # speech = VAD segments only; silence = remove only below noise floor
    vad_chunking_enabled: bool = True  # When true, trim audio (by speech or silence); when false, only use VAD as gate
    vad_save_speech_only: bool = False  # When true and chunking used, save speech-only WAV to storage instead of original
    vad_segment_pad_s: float = 0.2  # Padding (seconds) around each VAD segment after Silero (speech mode only)
    # Silence-removal mode (only cut out silence; keeps everything above noise floor)
    silence_threshold: float = 0.015  # RMS below this = silence (tune to your noise floor; 0.01–0.03 typical)
    min_silence_duration_s: float = 0.5  # Only remove silence gaps at least this long (seconds)
    silence_gap_s: float = 0.1  # Replace removed silence with this many seconds of gap


class QueueConfig(BaseModel):
    """Queue settings."""
    max_size: int = 0
    pause_on_full: bool = False
    fifo_order: bool = True


class GeminiConfig(BaseModel):
    """Gemini API configuration."""
    enabled: bool = False
    api_key: str = ""
    model: str = "gemini-1.5-flash"
    max_output_tokens: int = 8192  # For summaries; increase if responses are cut off


class SummariesConfig(BaseModel):
    """Hour summaries (Insights) configuration."""
    auto_generate_enabled: bool = False
    # How often to check for missing summaries (seconds)
    auto_generate_interval_seconds: int = 300
    # How many days back from today to fill (1 = today only)
    auto_generate_days: int = 1


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: Literal["simple", "detailed"] = "simple"
    max_size_mb: int = 100
    backup_count: int = 5


class TimestampConfig(BaseModel):
    """Timestamp extraction configuration."""
    method: Literal["metadata", "title", "both"] = "metadata"  # both = try title first, fallback to metadata
    title_format_1: str = "YYYYMMDD_HHMMSS"  # Format: 20260125_123543
    title_format_2: str = "HH-MM-SS AM/PM"   # Format: 12-36-13 PM


class IncidentsOllamaConfig(BaseModel):
    """Ollama for Worker (cheap triage), Master (routing + tools, header fields, incident summaries)."""
    enabled: bool = False
    base_url: str = "http://localhost:11434"
    # Default when worker_model / master_model omitted (legacy single-model setups).
    model: str = "llama3.2:3b"
    # Small/cheap model: should this EVT_TYPE span open a new incident?
    worker_model: str = ""
    # Stronger model: Master routing (attach/skip/close) + event summaries.
    master_model: str = ""
    timeout_seconds: int = 60


def incidents_ollama_master_model(cfg: IncidentsOllamaConfig) -> str:
    m = (cfg.master_model or "").strip()
    return m if m else (cfg.model or "llama3.2:3b")


def incidents_ollama_worker_model(cfg: IncidentsOllamaConfig) -> str:
    w = (cfg.worker_model or "").strip()
    return w if w else (cfg.model or "llama3.2:3b")


class EventsPipelineConfig(BaseModel):
    """Events pipeline: NER → span_store; Worker (EVT_TYPE) opens incidents; Master routes until close."""
    enabled: bool = False
    # Path to NER model folder (contains model.safetensors, config.json, tokenizer)
    ner_model_path: str = ""
    # Run Ollama summary when attached spans reach this count; then after each new attach
    summary_trigger_spans: int = 5
    # Strip ASCII commas from span text before NER only. false = revert to raw transcript for NER
    ner_strip_commas: bool = True
    # Minimum per-span confidence score (0.0–1.0) to keep an NER entity. 0.0 = disabled.
    ner_confidence_threshold: float = 0.85
    # Master LLM routing (requires incidents_ollama + llm_routing). NER rule fallback removed.
    llm_routing: bool = False
    llm_routing_max_tool_rounds: int = 12
    # Log full Ollama JSON (per round) + final assistant text at INFO (noisy; for debugging)
    llm_routing_log_raw: bool = False
    # Use OpenAI-compatible POST {base_url}/v1/chat/completions (often better tool calling); false = native /api/chat
    llm_routing_openai_api: bool = True
    # Cap total generated tokens per routing HTTP call (thinking/reasoning + tool args + final JSON share this budget).
    # OpenAI path: max_tokens; native /api/chat: options.num_predict. None = Ollama default.
    llm_routing_max_tokens: Optional[int] = None
    # OpenAI-compatible path only (Ollama): none | low | medium | high — shorter reasoning on supported models. None = omit.
    llm_routing_reasoning_effort: Optional[str] = None
    # Master: if an open event's last span was attached more than this many seconds ago, lower attach confidence
    # (model is told to prefer skip unless the transcript is a strong semantic match). 0 = disable.
    master_llm_stale_seconds: int = 3600
    # Auto-close open events when no new span has been attached for this many seconds. 0 = disable.
    auto_close_stale_seconds: int = 0
    # How often (seconds) the background cleanup sweep runs. 0 = disable.
    cleanup_interval_seconds: int = 0
    # Run header normalizer every N total attached spans (1 = every attach, 5 = 1st/5th/10th…). 0 = every attach.
    normalize_every_n_spans: int = 5
    # Master LLM fills event_type, location, units, status_detail from transcripts (not raw NER in the header).
    # Requires incidents_ollama.enabled. false = legacy NER-built header + merge on attach.
    master_header_normalize: bool = True


class AdvancedConfig(BaseModel):
    """Advanced configuration."""
    archive_directory: str = "/app/audio_storage"
    debug_mode: bool = False
    max_file_size_mb: int = 0
    transcription_timeout: int = 0
    chunk_length_s: int = 30  # Whisper's native chunk size
    chunk_stride_s: int = 5   # Overlap between chunks


class Config(BaseModel):
    """Main configuration."""
    model: ModelConfig = ModelConfig()
    watcher: WatcherConfig = WatcherConfig()
    watchdog_client: WatchdogClientConfig = WatchdogClientConfig()
    storage: StorageConfig = StorageConfig()
    transcription: TranscriptionConfig = TranscriptionConfig()
    queue: QueueConfig = QueueConfig()
    gemini: GeminiConfig = GeminiConfig()
    summaries: SummariesConfig = SummariesConfig()
    events_pipeline: EventsPipelineConfig = EventsPipelineConfig()
    incidents_ollama: IncidentsOllamaConfig = IncidentsOllamaConfig()
    logging: LoggingConfig = LoggingConfig()
    advanced: AdvancedConfig = AdvancedConfig()
    timestamp: TimestampConfig = TimestampConfig()


class Settings:
    """Application settings with environment variable overrides."""
    
    def __init__(self):
        # Load config.yml
        config_path = os.getenv("CONFIG_PATH", "/app/config.yml")
        self.config_path = config_path
        
        try:
            with open(config_path) as f:
                config_data = yaml.safe_load(f) or {}
            self.config = Config(**config_data)
        except FileNotFoundError:
            logger.warning(f"Config file not found at {config_path}, using defaults")
            self.config = Config()
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            raise
        
        # Security settings from environment variables (not in config.yml)
        # Bootstrap admin (empty DB only): SCANSCRIBE_DEFAULT_ADMIN_PASSWORD,
        # SCANSCRIBE_DEFAULT_ADMIN_USERNAME (default admin), SCANSCRIBE_DEFAULT_ADMIN_EMAIL (default admin@localhost)
        self.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
        self.access_token_expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
        self.algorithm = "HS256"
        
        # Directory paths from environment variables
        self.ingest_dir = Path(os.getenv("INGEST_DIR", "/app/ingest"))
        self.output_dir = Path(os.getenv("OUTPUT_DIR", "/app/audio_storage"))
        self.log_dir = Path(os.getenv("LOG_DIR", "/app/logs"))
        self.db_path = Path(os.getenv("DB_PATH", "/app/data/scanscribe.db"))
        
        # Aliases for easier access (commonly used settings)
        self.model_name = self.config.model.name
        self.model_path = Path(self.config.model.path)
        self.num_workers = self.config.model.workers
        self.retention_days = self.config.storage.retention_days
        self.save_audio_for_playback = self.config.storage.save_audio_for_playback
        self.gemini_api_key = os.getenv("GEMINI_API_KEY") or self.config.gemini.api_key


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def reload_settings():
    """Reload settings by clearing the cache."""
    get_settings.cache_clear()
    return get_settings()


def save_config(config_dict: dict, config_path: str = None) -> bool:
    """Save configuration to YAML file."""
    if config_path is None:
        config_path = os.getenv("CONFIG_PATH", "/app/config.yml")
    
    try:
        # Direct write (atomic rename doesn't work well with Docker bind mounts)
        with open(config_path, 'w') as f:
            yaml.safe_dump(config_dict, f, default_flow_style=False, sort_keys=False)
        
        # Reload settings
        reload_settings()
        
        logger.info(f"Configuration saved to {config_path}")
        return True
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return False


# Ensure directories exist
def init_directories():
    """Create required directories if they don't exist."""
    settings = get_settings()
    for directory in [
        settings.ingest_dir,
        settings.output_dir,
        settings.log_dir,
        settings.db_path.parent,
        settings.model_path,
    ]:
        directory.mkdir(parents=True, exist_ok=True)
