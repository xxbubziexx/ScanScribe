"""Pydantic v2 schemas for maintenance endpoints."""
from typing import Any, Dict, Optional
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
