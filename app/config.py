"""Application configuration management."""
import os
import yaml
from pathlib import Path
from pydantic import BaseModel, ConfigDict
from functools import lru_cache
from typing import Any, Dict, List, Literal, Optional
from pydantic import Field
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


class HourlySummariesApiConfig(BaseModel):
    """Hourly Summaries API (Insights hour summaries)."""
    enabled: bool = False
    # gemini = Google Generative Language API; openrouter = OpenAI-compatible cloud
    provider: Literal["gemini", "openrouter"] = "gemini"
    api_key: str = ""
    # Gemini: "gemini-2.5-flash". OpenRouter: e.g. "google/gemini-2.5-flash"
    model: str = "gemini-2.5-flash"
    # OpenRouter only. Empty → https://openrouter.ai/api
    base_url: str = ""
    max_output_tokens: int = 8192  # For summaries; increase if responses are cut off


class SummariesConfig(BaseModel):
    """Hour summaries (Insights) auto-generation schedule."""
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


class OpenRouterConfig(BaseModel):
    """OpenRouter / OpenAI-compatible API configuration for Events Pipeline single-pass router."""
    model_config = ConfigDict(protected_namespaces=())

    api_key: str = ""
    base_url: str = "https://openrouter.ai/api/v1"
    model_name: str = "google/gemini-2.5-flash"
    timeout_seconds: int = 30
    temperature: float = 0.0


# Backward compatibility alias / deprecation
IncidentsOllamaConfig = OpenRouterConfig


def openrouter_api_key(cfg: Optional[OpenRouterConfig] = None) -> str:
    """Provider-specific env key (OPENROUTER_API_KEY) wins over config.api_key."""
    env = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if env:
        return env
    if cfg is not None:
        return (getattr(cfg, "api_key", "") or "").strip()
    return ""


def openrouter_base_url(cfg: Optional[OpenRouterConfig] = None) -> str:
    """Effective base URL for OpenRouter/OpenAI API endpoint."""
    env = (os.getenv("OPENROUTER_BASE_URL") or "").strip()
    if env:
        return env.rstrip("/")
    if cfg is not None:
        raw = (getattr(cfg, "base_url", "") or "").strip()
        if raw:
            return raw.rstrip("/")
    return "https://openrouter.ai/api/v1"


def openrouter_model(cfg: Optional[OpenRouterConfig] = None) -> str:
    """Effective model name for OpenRouter. config.yml model_name wins over env defaults."""
    if cfg is not None:
        m = (
            getattr(cfg, "model_name", "")
            or getattr(cfg, "model", "")
            or getattr(cfg, "master_model", "")
            or getattr(cfg, "worker_model", "")
            or ""
        ).strip()
        if m:
            return m
    env = (os.getenv("OPENROUTER_MODEL") or "").strip()
    if env:
        return env
    return "google/gemini-2.5-flash"


# Deprecated helper aliases for backward compatibility
def incidents_ollama_master_model(cfg: Any) -> str:
    return openrouter_model(cfg)


def incidents_ollama_worker_model(cfg: Any) -> str:
    return openrouter_model(cfg)


def incidents_ollama_api_key(cfg: Any) -> str:
    return openrouter_api_key(cfg)


def incidents_ollama_base_url(cfg: Any) -> str:
    return openrouter_base_url(cfg)


def hourly_summaries_api_key(cfg: HourlySummariesApiConfig) -> str:
    """Provider-specific env key wins over config.api_key."""
    if cfg.provider == "openrouter":
        env = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    else:
        env = (os.getenv("GEMINI_API_KEY") or "").strip()
    if env:
        return env
    return (cfg.api_key or "").strip()


def hourly_summaries_base_url(cfg: HourlySummariesApiConfig) -> str:
    """Effective OpenRouter base URL (ignored for Gemini)."""
    raw = (cfg.base_url or "").strip().rstrip("/")
    if raw:
        return raw
    return "https://openrouter.ai/api"


class EventsPipelineConfig(BaseModel):
    """Events pipeline: NER entity extraction + Single-pass OpenRouter LLM router."""
    enabled: bool = False
    # Path to NER model folder (contains model.safetensors, config.json, tokenizer)
    ner_model_path: str = ""
    # Strip ASCII commas from span text before NER only. false = revert to raw transcript for NER
    ner_strip_commas: bool = True
    # Minimum per-span confidence score (0.0–1.0) to keep an NER entity. 0.0 = disabled.
    ner_confidence_threshold: float = 0.85
    # Auto-close open events when no new span has been attached for this many seconds. 0 = disable.
    auto_close_stale_seconds: int = 0
    # IANA timezone for naive LogEntry.timestamp values (e.g. America/Chicago). Queue ingest uses naive
    # local wall times; empty = host system local timezone.
    log_naive_timezone: str = ""
    # How often (seconds) the background cleanup sweep runs. 0 = disable.
    cleanup_interval_seconds: int = 0
    # Legacy / optional fields kept for backwards compatibility
    llm_routing_max_tool_rounds: Optional[int] = 12
    llm_routing_log_raw: Optional[bool] = False
    llm_routing_openai_api: Optional[bool] = True
    llm_routing_max_tokens: Optional[int] = None
    llm_routing_reasoning_effort: Optional[str] = None
    master_llm_stale_seconds: Optional[int] = 3600
    normalize_every_n_spans: Optional[int] = 5
    master_header_normalize: Optional[bool] = True


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
    hourly_summaries: HourlySummariesApiConfig = HourlySummariesApiConfig()
    summaries: SummariesConfig = SummariesConfig()
    events_pipeline: EventsPipelineConfig = EventsPipelineConfig()
    openrouter: OpenRouterConfig = OpenRouterConfig()
    incidents_ollama: Optional[OpenRouterConfig] = None
    logging: LoggingConfig = LoggingConfig()
    advanced: AdvancedConfig = AdvancedConfig()
    timestamp: TimestampConfig = TimestampConfig()
    landmarks: Dict[str, str] = Field(default_factory=dict)


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
            if self.config.incidents_ollama is not None:
                if not self.config.openrouter.api_key and self.config.incidents_ollama.api_key:
                    self.config.openrouter.api_key = self.config.incidents_ollama.api_key
                if (
                    self.config.openrouter.base_url == "https://openrouter.ai/api/v1"
                    and self.config.incidents_ollama.base_url
                    and self.config.incidents_ollama.base_url != "http://localhost:11434"
                ):
                    self.config.openrouter.base_url = self.config.incidents_ollama.base_url
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
        self.hourly_summaries_api_key = hourly_summaries_api_key(self.config.hourly_summaries)
        self.openrouter_api_key = openrouter_api_key(self.config.openrouter)


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
