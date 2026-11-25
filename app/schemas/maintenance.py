"""Pydantic v2 schemas for maintenance endpoints."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class RetentionConfigResponse(BaseModel):
    """Retention configuration response."""
    model_config = ConfigDict(from_attributes=True)

    retention_days: int
    cleanup_hour: int


class DatabaseStatsResponse(BaseModel):
    """Database statistics response."""
    model_config = ConfigDict(from_attributes=True)

    total_entries: Optional[int] = 0
    oldest_date: Optional[str] = None
    newest_date: Optional[str] = None
    days_of_data: int = 0


class StorageHealthStats(BaseModel):
    """SQLite storage, WAL, and audio disk metrics."""
    model_config = ConfigDict(from_attributes=True)

    db_bytes: int = 0
    wal_bytes: int = 0
    shm_bytes: int = 0
    total_sqlite_bytes: int = 0
    journal_mode: str = "wal"
    page_size: int = 0
    page_count: int = 0
    freelist_count: int = 0
    reclaimable_bytes: int = 0
    audio_files_count: int = 0
    audio_bytes: int = 0
    audio_layout: str = "sharded"
    retention_days: int = 0


class TableInventoryItem(BaseModel):
    """Summary metrics for a browsable database table."""
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    route: str
    row_count: int = 0
    secondary_label: Optional[str] = None
    secondary_value: Optional[str] = None
    oldest: Optional[str] = None
    newest: Optional[str] = None


class EntityLabelStat(BaseModel):
    """Per-label count and unique raw value count from entity_observations."""
    model_config = ConfigDict(from_attributes=True)

    label: str
    total_count: int = 0
    unique_raw_count: int = 0
    pct_of_total: float = 0.0


class NerOverviewStats(BaseModel):
    """NER pipeline status, coverage, and per-label distribution."""
    model_config = ConfigDict(from_attributes=True)

    pipeline_enabled: bool = False
    ner_only: bool = False
    ner_loaded: bool = False
    ner_model_path: str = ""
    covered_logs: int = 0
    total_logs: int = 0
    coverage_pct: float = 0.0
    total_spans: int = 0
    total_observations: int = 0
    labels: List[EntityLabelStat] = []


class DailyVolumePoint(BaseModel):
    """Daily log count point for overview volume bar chart."""
    model_config = ConfigDict(from_attributes=True)

    date: str
    count: int = 0


class TalkgroupVolumeItem(BaseModel):
    """Talkgroup activity summary over the last 24 hours."""
    model_config = ConfigDict(from_attributes=True)

    talkgroup: str
    count: int = 0
    duration_seconds: float = 0.0


class DatabaseOverviewResponse(BaseModel):
    """Aggregated telemetry payload for the Database Explorer Overview dashboard."""
    model_config = ConfigDict(from_attributes=True)

    generated_at: str
    storage: StorageHealthStats
    tables: List[TableInventoryItem]
    ner: NerOverviewStats
    daily_volume: List[DailyVolumePoint]
    top_talkgroups_24h: List[TalkgroupVolumeItem]
    logs_last_24h: int = 0
    total_audio_duration_seconds: float = 0.0


class PurgeResponse(BaseModel):
    """Response returned upon purging historical entries."""
    model_config = ConfigDict(from_attributes=True)

    message: str
    deleted_count: int
    audio_files_deleted: int
    cutoff_date: Optional[str] = None


class RedactSsnResponse(BaseModel):
    """Response returned upon running SSN scrubbing."""
    model_config = ConfigDict(from_attributes=True)

    ok: bool
    stats: Dict[str, Any]
