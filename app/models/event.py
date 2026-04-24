"""Events pipeline models (Worker/Master LLM per monitor)."""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Index

from ..database import EventsBase, utcnow


class Monitor(EventsBase):
    """One department/monitor: talkgroups for NER events pipeline."""
    __tablename__ = "monitors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    enabled = Column(Boolean, default=True, index=True)
    # JSON list of talkgroup names (strip + case-insensitive match to log_entry.talkgroup)
    talkgroup_ids = Column(Text, nullable=False, default="[]")
    # JSON list of NER labels that trigger event creation (e.g. ["EVT_TYPE"]). Stored in keyword_config.
    keyword_config = Column(Text, nullable=False, default='["EVT_TYPE"]')
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Event(EventsBase):
    """One event: draft header from Worker, enriched by Master. Closed when Master decides."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(64), nullable=False, unique=True, index=True)  # Unique ID for Worker/Master
    monitor_id = Column(Integer, ForeignKey("monitors.id"), nullable=False, index=True)
    status = Column(String(20), default="open", index=True)  # open, closed
    # EVENT HEADER (Worker draft, Master updates)
    event_type = Column(String(255), nullable=True)
    # Worker tool classify_broadcast: storm_warning | cni_drivers | road_debris | attempt_to_locate
    broadcast_type = Column(String(64), nullable=True)
    location = Column(String(500), nullable=True)
    units = Column(Text, nullable=True)  # JSON array or comma-separated
    status_detail = Column(String(255), nullable=True)  # e.g. "en route", "on scene"
    original_transcription = Column(Text, nullable=True)  # Trigger transcript (always set by Worker)
    summary = Column(Text, nullable=True)
    close_recommendation = Column(Boolean, nullable=True)  # Ollama suggests close; human/rule does actual close
    created_at = Column(DateTime(timezone=True), default=utcnow)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    # Master run: last time Master updated this event (for min_transcripts trigger)
    master_last_run_at = Column(DateTime(timezone=True), nullable=True)


class EventTranscriptLink(EventsBase):
    """Link a log_entry (transcript) to an event. Worker attaches on trigger/dedupe."""
    __tablename__ = "event_transcript_links"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False, index=True)
    log_entry_id = Column(Integer, nullable=False, index=True)  # ID in logs DB log_entries
    entities_json = Column(Text, nullable=True)  # NER output: {"EVT_TYPE": [...], "UNIT": [...], ...}
    # Routing / pipeline note: LLM reason, auto_attach, etc. (optional)
    llm_reason = Column(Text, nullable=True)
    linked_at = Column(DateTime(timezone=True), default=utcnow)


class PipelineDebugLog(EventsBase):
    """Append-only debug rows for Events UI (NER / LLM routing). Shared across API workers via SQLite."""

    __tablename__ = "pipeline_debug_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, index=True)
    payload_json = Column(Text, nullable=False)


class SpanStore(EventsBase):
    """Per-span NER extract + transcript; Worker reads rows with evt_type for triage; Master uses recent rows for context."""

    __tablename__ = "span_store"

    id = Column(Integer, primary_key=True, index=True)
    monitor_id = Column(Integer, ForeignKey("monitors.id"), nullable=False, index=True)
    talkgroup = Column(String(255), nullable=True, index=True)
    transcript = Column(Text, nullable=True)
    evt_type = Column(Text, nullable=True)
    units = Column(Text, nullable=True)
    locations = Column(Text, nullable=True)
    addresses = Column(Text, nullable=True)
    cross_streets = Column(Text, nullable=True)
    persons = Column(Text, nullable=True)
    vehicles = Column(Text, nullable=True)
    plates = Column(Text, nullable=True)
    time_mentions = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    log_entry_id = Column(Integer, nullable=True, index=True)
