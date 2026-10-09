"""Pydantic schemas for Event and Span entities."""
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class SpanStoreItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    monitor_id: int
    talkgroup: Optional[str] = None
    log_entry_id: Optional[int] = None
    transcript: Optional[str] = None
    evt_type: Optional[str] = None
    units: Optional[str] = None
    locations: Optional[str] = None
    addresses: Optional[str] = None
    status: Optional[str] = None
    time_mentions: Optional[str] = None
    created_at: Optional[str] = None
    attached_event_ids: List[str] = Field(default_factory=list)


class SpanStoreListResponse(BaseModel):
    items: List[SpanStoreItem]
    total: int


class EntityObservationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    span_store_id: int
    monitor_id: int
    talkgroup: Optional[str] = None
    log_entry_id: Optional[int] = None
    ts: Optional[str] = None
    label: str
    canonical: str
    raw: str


class EntityObservationListResponse(BaseModel):
    items: List[EntityObservationItem]
    total: int


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: str
    monitor_id: int
    status: str
    event_type: Optional[str] = None
    broadcast_type: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    resolved_address: Optional[str] = None
    units: Optional[str] = None
    status_detail: Optional[str] = None
    original_transcription: Optional[str] = None
    summary: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    incident_at: Optional[str] = None
    last_span_at: Optional[str] = None
    closed_at: Optional[str] = None
    spans_attached: int = 0
    talkgroup: str = ""
    audio_path: Optional[str] = None
