"""Events pipeline API: monitors (departments) and events."""
import csv
import io
import json
from collections import defaultdict
from datetime import date, datetime as dt, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_events_db, get_logs_db
from ..models.event import Monitor, Event, EventTranscriptLink, SpanStore, EntityObservation
from ..models.log_entry import LogEntry
from ..models.user import User
from ..services.events_common import parse_json_list
from ..services.events_debug import clear_all as clear_debug_all, get_recent as get_debug_recent
from ..services.ner_service import ENTITY_LABELS
from .auth import get_current_active_user, get_current_admin_user


def _iso_utc(d: dt | None, assume_utc: bool = False) -> str | None:
    """Serialize datetime for the Events API / browser display.

    - Timezone-aware values are normalized to UTC with a Z suffix.
    - Naive values with assume_utc=True are treated as UTC (SQLite strips tzinfo on write
      even when stored via utcnow(); event model timestamps fall into this category).
    - Naive values with assume_utc=False (default) are treated as local wall-clock
      (e.g. LogEntry.timestamp derived from filenames) and emitted without Z so the
      browser does not double-shift them.
    """
    if d is None:
        return None
    if d.tzinfo is None:
        if assume_utc:
            d = d.replace(tzinfo=timezone.utc)
        else:
            return d.isoformat()
    u = d.astimezone(timezone.utc)
    s = u.isoformat().replace("+00:00", "Z")
    return s


def _start_labels(raw: Optional[str]) -> List[str]:
    labels = parse_json_list(raw)
    return labels if labels else ["EVT_TYPE"]


def _batch_event_link_aggregates(
    events_db: Session,
    logs_db: Session,
    event_ids: List[int],
) -> Tuple[Dict[int, int], Dict[int, str], Dict[int, Optional[dt]]]:
    """Spans per event, aggregated talkgroups, earliest linked log timestamp per event."""
    if not event_ids:
        return {}, {}, {}
    count_rows = (
        events_db.query(EventTranscriptLink.event_id, func.count(EventTranscriptLink.id))
        .filter(EventTranscriptLink.event_id.in_(event_ids))
        .group_by(EventTranscriptLink.event_id)
        .all()
    )
    link_counts = {eid: int(cnt or 0) for eid, cnt in count_rows}
    link_rows = (
        events_db.query(EventTranscriptLink.event_id, EventTranscriptLink.log_entry_id)
        .filter(EventTranscriptLink.event_id.in_(event_ids))
        .all()
    )
    log_ids = sorted({lid for _, lid in link_rows if lid is not None})
    talkgroup_by_log_id: Dict[int, str] = {}
    ts_by_log_id: Dict[int, dt] = {}
    if log_ids:
        for lid, tg, ts in logs_db.query(
            LogEntry.id, LogEntry.talkgroup, LogEntry.timestamp
        ).filter(LogEntry.id.in_(log_ids)).all():
            if tg:
                talkgroup_by_log_id[lid] = tg
            if ts is not None:
                ts_by_log_id[lid] = ts
    links_by_event: Dict[int, List[int]] = defaultdict(list)
    for ev_id, log_id in link_rows:
        if log_id is not None:
            links_by_event[ev_id].append(log_id)
    first_span_at_by_event: Dict[int, dt] = {}
    for ev_id, lids in links_by_event.items():
        tss = [ts_by_log_id[lid] for lid in lids if lid in ts_by_log_id]
        if tss:
            first_span_at_by_event[ev_id] = min(tss)
    talkgroups_by_event: Dict[int, set] = defaultdict(set)
    for ev_id, log_id in link_rows:
        tg = talkgroup_by_log_id.get(log_id)
        if tg:
            talkgroups_by_event[ev_id].add(tg)
    talkgroup_str = {
        eid: ", ".join(sorted(talkgroups_by_event[eid])) if talkgroups_by_event.get(eid) else ""
        for eid in event_ids
    }
    return link_counts, talkgroup_str, first_span_at_by_event


def _event_type_csv_display(event: Event) -> str:
    """Single column matching UI: BROADCAST subtype vs incident event_type."""
    bt = (getattr(event, "broadcast_type", None) or "").strip()
    if bt:
        return f"BROADCAST:{bt}"
    et = (event.event_type or "").strip()
    if et.upper() == "BROADCAST":
        return "BROADCAST"
    return et


router = APIRouter(prefix="/api/events", tags=["events"])


class MonitorCreate(BaseModel):
    name: str = Field(..., min_length=1)
    talkgroup_ids: List[str] = Field(default_factory=list)
    start_event_labels: List[str] = Field(default_factory=lambda: ["EVT_TYPE"])
    geo_region: Optional[str] = None


class MonitorUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    enabled: Optional[bool] = None
    talkgroup_ids: Optional[List[str]] = None
    start_event_labels: Optional[List[str]] = None
    geo_region: Optional[str] = None


class MonitorResponse(BaseModel):
    id: int
    name: str
    enabled: bool
    talkgroup_ids: List[str]
    start_event_labels: List[str]
    geo_region: Optional[str] = None


class SpanStoreItem(BaseModel):
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
    id: int
    event_id: str
    monitor_id: int
    status: str
    event_type: Optional[str]
    broadcast_type: Optional[str] = None
    location: Optional[str]
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    resolved_address: Optional[str] = None
    units: Optional[str]
    status_detail: Optional[str]
    original_transcription: Optional[str]
    summary: Optional[str]
    # System: when the event row was created (processing time).
    created_at: Optional[str]
    # Earliest linked span LogEntry.timestamp (from audio-derived time stored in logs DB).
    incident_at: Optional[str] = None
    closed_at: Optional[str]
    spans_attached: int = 0
    talkgroup: str = ""


@router.get("/monitors", response_model=List[MonitorResponse])
async def list_monitors(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_events_db),
):
    """List all monitors (departments)."""
    monitors = db.query(Monitor).order_by(Monitor.name).all()
    return [
        MonitorResponse(
            id=m.id,
            name=m.name,
            enabled=m.enabled,
            talkgroup_ids=parse_json_list(m.talkgroup_ids),
            start_event_labels=_start_labels(m.keyword_config),
            geo_region=m.geo_region,
        )
        for m in monitors
    ]


@router.post("/monitors", response_model=MonitorResponse)
async def create_monitor(
    body: MonitorCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_events_db),
):
    """Create a monitor (department)."""
    labels = body.start_event_labels or ["EVT_TYPE"]
    m = Monitor(
        name=body.name,
        enabled=True,
        geo_region=(body.geo_region or "").strip() or None,
        talkgroup_ids=json.dumps(body.talkgroup_ids),
        keyword_config=json.dumps(labels),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return MonitorResponse(
        id=m.id,
        name=m.name,
        enabled=m.enabled,
        talkgroup_ids=body.talkgroup_ids,
        start_event_labels=labels,
        geo_region=m.geo_region,
    )


@router.patch("/monitors/{monitor_id}", response_model=MonitorResponse)
async def update_monitor(
    monitor_id: int,
    body: MonitorUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_events_db),
):
    """Update a monitor (name, enabled, talkgroup_ids, start_event_labels, geo_region)."""
    m = db.query(Monitor).filter(Monitor.id == monitor_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Monitor not found")
    if body.name is not None:
        m.name = body.name
    if body.enabled is not None:
        m.enabled = body.enabled
    if body.geo_region is not None:
        m.geo_region = body.geo_region.strip() or None
    if body.talkgroup_ids is not None:
        m.talkgroup_ids = json.dumps(body.talkgroup_ids)
    if body.start_event_labels is not None:
        m.keyword_config = json.dumps(body.start_event_labels)
    db.add(m)
    db.commit()
    db.refresh(m)
    return MonitorResponse(
        id=m.id,
        name=m.name,
        enabled=m.enabled,
        talkgroup_ids=parse_json_list(m.talkgroup_ids),
        start_event_labels=_start_labels(m.keyword_config),
        geo_region=m.geo_region,
    )


@router.delete("/monitors/{monitor_id}")
async def delete_monitor(
    monitor_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_events_db),
):
    """Delete a monitor and its events + transcript links."""
    m = db.query(Monitor).filter(Monitor.id == monitor_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Monitor not found")
    for ev in db.query(Event).filter(Event.monitor_id == monitor_id).all():
        db.query(EventTranscriptLink).filter(EventTranscriptLink.event_id == ev.id).delete()
    db.query(Event).filter(Event.monitor_id == monitor_id).delete()
    db.delete(m)
    db.commit()
    return {"ok": True}


@router.get("/span-store", response_model=SpanStoreListResponse)
@router.get("/spans", response_model=SpanStoreListResponse)
async def list_span_store(
    monitor_id: Optional[int] = Query(None, ge=1),
    talkgroup: Optional[str] = Query(None, max_length=255),
    log_entry_id: Optional[int] = Query(None, ge=1),
    q: Optional[str] = Query(None, max_length=500, description="Substring search in transcript"),
    sort_by: Optional[str] = Query("id", pattern="^(id|created_at|talkgroup|log_entry_id|status|evt_type)$"),
    sort_order: Optional[str] = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_events_db),
):
    """Browse span_store rows (NER + transcript per ingest)."""
    qry = db.query(SpanStore)
    if monitor_id is not None:
        qry = qry.filter(SpanStore.monitor_id == monitor_id)
    if talkgroup and talkgroup.strip():
        qry = qry.filter(SpanStore.talkgroup.ilike(f"%{talkgroup.strip()}%"))
    if log_entry_id is not None:
        qry = qry.filter(SpanStore.log_entry_id == log_entry_id)
    if q and q.strip():
        qry = qry.filter(SpanStore.transcript.ilike(f"%{q.strip()}%"))
    total = qry.count()

    col = getattr(SpanStore, sort_by or "id", SpanStore.id)
    if (sort_order or "desc").lower() == "asc":
        qry = qry.order_by(col.asc())
    else:
        qry = qry.order_by(col.desc())

    rows = (
        qry.offset(offset)
        .limit(limit)
        .all()
    )
    log_ids = sorted({r.log_entry_id for r in rows if r.log_entry_id is not None})
    attached_by_log: Dict[int, List[str]] = defaultdict(list)
    if log_ids:
        for lid, eid in (
            db.query(EventTranscriptLink.log_entry_id, Event.event_id)
            .join(Event, Event.id == EventTranscriptLink.event_id)
            .filter(EventTranscriptLink.log_entry_id.in_(log_ids))
            .all()
        ):
            if lid is not None and eid:
                attached_by_log[int(lid)].append(eid)
    items: List[SpanStoreItem] = []
    for r in rows:
        lid = r.log_entry_id
        items.append(
            SpanStoreItem(
                id=r.id,
                monitor_id=r.monitor_id,
                talkgroup=r.talkgroup,
                log_entry_id=lid,
                transcript=r.transcript,
                evt_type=r.evt_type,
                units=r.units,
                locations=r.locations,
                addresses=r.addresses,
                status=r.status,
                time_mentions=r.time_mentions,
                created_at=_iso_utc(r.created_at, assume_utc=True),
                attached_event_ids=sorted(set(attached_by_log.get(lid, []))) if lid else [],
            )
        )
    return SpanStoreListResponse(items=items, total=total)


@router.get("/entities", response_model=EntityObservationListResponse)
async def list_entities(
    monitor_id: Optional[int] = Query(None, ge=1),
    label: Optional[str] = Query(None, max_length=32),
    talkgroup: Optional[str] = Query(None, max_length=255),
    log_entry_id: Optional[int] = Query(None, ge=1),
    span_store_id: Optional[int] = Query(None, ge=1),
    q: Optional[str] = Query(None, max_length=500, description="Search canonical or raw text"),
    sort_by: Optional[str] = Query("id", pattern="^(id|ts|label|canonical|raw|talkgroup|log_entry_id|span_store_id)$"),
    sort_order: Optional[str] = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_events_db),
):
    """Browse entity_observations rows with filtering, sorting, and pagination."""
    qry = db.query(EntityObservation)
    if monitor_id is not None:
        qry = qry.filter(EntityObservation.monitor_id == monitor_id)
    if label and label.strip():
        qry = qry.filter(EntityObservation.label == label.strip().upper())
    if talkgroup and talkgroup.strip():
        qry = qry.filter(EntityObservation.talkgroup.ilike(f"%{talkgroup.strip()}%"))
    if log_entry_id is not None:
        qry = qry.filter(EntityObservation.log_entry_id == log_entry_id)
    if span_store_id is not None:
        qry = qry.filter(EntityObservation.span_store_id == span_store_id)
    if q and q.strip():
        term = f"%{q.strip()}%"
        qry = qry.filter(
            (EntityObservation.canonical.ilike(term)) | (EntityObservation.raw.ilike(term))
        )
    total = qry.count()

    col = getattr(EntityObservation, sort_by or "id", EntityObservation.id)
    if (sort_order or "desc").lower() == "asc":
        qry = qry.order_by(col.asc())
    else:
        qry = qry.order_by(col.desc())

    rows = qry.offset(offset).limit(limit).all()
    items = [
        EntityObservationItem(
            id=r.id,
            span_store_id=r.span_store_id,
            monitor_id=r.monitor_id,
            talkgroup=r.talkgroup,
            log_entry_id=r.log_entry_id,
            ts=_iso_utc(r.ts, assume_utc=True),
            label=r.label,
            canonical=r.canonical,
            raw=r.raw,
        )
        for r in rows
    ]
    return EntityObservationListResponse(items=items, total=total)


@router.get("/events")
async def list_events(
    monitor_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None, max_length=500, description="Search in summary, location, units, transcript"),
    sort_by: Optional[str] = Query("created_at", pattern="^(id|event_id|created_at|closed_at|status|event_type|location)$"),
    sort_order: Optional[str] = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    events_db: Session = Depends(get_events_db),
    logs_db: Session = Depends(get_logs_db),
) -> Dict[str, Any]:
    """List events with pagination and search. Returns {items: [...], total: N}."""
    query = events_db.query(Event)
    if monitor_id is not None:
        query = query.filter(Event.monitor_id == monitor_id)
    if status:
        query = query.filter(Event.status == status)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            (Event.event_id.ilike(term))
            | (Event.event_type.ilike(term))
            | (Event.broadcast_type.ilike(term))
            | (Event.location.ilike(term))
            | (Event.resolved_address.ilike(term))
            | (Event.units.ilike(term))
            | (Event.summary.ilike(term))
            | (Event.original_transcription.ilike(term))
        )
    total: int = query.count()

    col = getattr(Event, sort_by or "created_at", Event.created_at)
    if (sort_order or "desc").lower() == "asc":
        query = query.order_by(col.asc())
    else:
        query = query.order_by(col.desc())

    events = query.offset(offset).limit(limit).all()
    event_ids = [e.id for e in events]
    link_counts, talkgroup_str_map, first_span_at_by_event = _batch_event_link_aggregates(
        events_db, logs_db, event_ids
    )
    out = []
    for e in events:
        spans_attached = link_counts.get(e.id, 0)
        talkgroup_str = talkgroup_str_map.get(e.id, "")
        incident_at = first_span_at_by_event.get(e.id)
        out.append(EventResponse(
            id=e.id,
            event_id=e.event_id,
            monitor_id=e.monitor_id,
            status=e.status,
            event_type=e.event_type,
            broadcast_type=getattr(e, "broadcast_type", None),
            location=e.location,
            latitude=e.latitude,
            longitude=e.longitude,
            resolved_address=e.resolved_address,
            units=e.units,
            status_detail=e.status_detail,
            original_transcription=e.original_transcription,
            summary=e.summary,
            created_at=_iso_utc(e.created_at, assume_utc=True),
            incident_at=_iso_utc(incident_at) if incident_at else None,
            closed_at=_iso_utc(e.closed_at, assume_utc=True),
            spans_attached=spans_attached,
            talkgroup=talkgroup_str,
        ))
    return {"items": out, "total": total}


@router.get("/events/export-headers")
async def export_events_normalized_headers(
    monitor_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(10000, ge=1, le=50000),
    current_user: User = Depends(get_current_active_user),
    events_db: Session = Depends(get_events_db),
    logs_db: Session = Depends(get_logs_db),
):
    """Download CSV of pipeline-normalized headers: event type, location, units, times (Master/worker fields on Event)."""
    q = events_db.query(Event).order_by(Event.created_at.desc())
    if monitor_id is not None:
        q = q.filter(Event.monitor_id == monitor_id)
    if status:
        q = q.filter(Event.status == status)
    rows = q.limit(limit).all()
    event_ids = [e.id for e in rows]
    monitors = {m.id: m.name for m in events_db.query(Monitor).all()}
    link_counts, talkgroup_str_map, first_span_at_by_event = _batch_event_link_aggregates(
        events_db, logs_db, event_ids
    )

    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    writer.writerow(
        [
            "event_id",
            "monitor_id",
            "monitor_name",
            "status",
            "event_type",
            "broadcast_type",
            "type_display",
            "location",
            "latitude",
            "longitude",
            "resolved_address",
            "units",
            "status_detail",
            "summary",
            "spans_attached",
            "talkgroups",
            "incident_at_iso",
            "created_at_iso",
            "closed_at_iso",
        ]
    )
    for e in rows:
        mid = e.monitor_id
        writer.writerow(
            [
                e.event_id,
                mid,
                monitors.get(mid, ""),
                e.status or "",
                (e.event_type or "").strip(),
                (getattr(e, "broadcast_type", None) or "").strip(),
                _event_type_csv_display(e),
                (e.location or "").strip(),
                e.latitude if e.latitude is not None else "",
                e.longitude if e.longitude is not None else "",
                (e.resolved_address or "").strip(),
                (e.units or "").strip(),
                (e.status_detail or "").strip(),
                (e.summary or "").replace("\r\n", " ").replace("\n", " ").strip(),
                link_counts.get(e.id, 0),
                talkgroup_str_map.get(e.id, ""),
                _iso_utc(first_span_at_by_event.get(e.id)) if first_span_at_by_event.get(e.id) else "",
                _iso_utc(e.created_at, assume_utc=True) or "",
                _iso_utc(e.closed_at, assume_utc=True) or "",
            ]
        )

    payload = "\ufeff" + buf.getvalue()
    fn = f"scanscribe_events_headers_{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([payload.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.get("/events/{event_id}")
async def get_event_detail(
    event_id: str,
    current_user: User = Depends(get_current_active_user),
    events_db: Session = Depends(get_events_db),
    logs_db: Session = Depends(get_logs_db),
):
    """Get one event by event_id (string) with header and linked transcripts from logs DB."""
    event = events_db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    monitor = events_db.query(Monitor).filter(Monitor.id == event.monitor_id).first()
    monitor_name = monitor.name if monitor else ""
    links = (
        events_db.query(EventTranscriptLink)
        .filter(EventTranscriptLink.event_id == event.id)
        .order_by(EventTranscriptLink.linked_at.asc())
        .all()
    )
    log_ids = [l.log_entry_id for l in links if l.log_entry_id is not None]
    log_entries = {}
    if log_ids:
        rows = logs_db.query(LogEntry).filter(LogEntry.id.in_(log_ids)).all()
        log_entries = {r.id: r for r in rows}
    transcripts = []
    for link in links:
        log_entry = log_entries.get(link.log_entry_id)
        if log_entry:
            has_playback = bool(log_entry.audio_path and log_entry.audio_path != "file not saved")
            t_text = log_entry.transcript or ""
            entities = None
            if link.entities_json:
                try:
                    entities = json.loads(link.entities_json)
                except (json.JSONDecodeError, TypeError):
                    pass
            transcripts.append({
                "log_entry_id": log_entry.id,
                "timestamp": log_entry.timestamp.isoformat() if log_entry.timestamp else None,
                "talkgroup": log_entry.talkgroup or "N/A",
                "transcript": t_text,
                "entities": entities,
                "audio_path": log_entry.audio_path or "",
                "has_playback": has_playback,
                "is_trigger": t_text.strip() == (event.original_transcription or "").strip(),
                "llm_reason": (getattr(link, "llm_reason", None) or "").strip(),
            })
    span_times = [le.timestamp for le in log_entries.values() if le and le.timestamp]
    incident_at = min(span_times) if span_times else None
    return {
        "event": {
            "event_id": event.event_id,
            "monitor_id": event.monitor_id,
            "monitor_name": monitor_name,
            "status": event.status,
            "event_type": event.event_type,
            "broadcast_type": getattr(event, "broadcast_type", None),
            "location": event.location,
            "latitude": event.latitude,
            "longitude": event.longitude,
            "resolved_address": event.resolved_address,
            "units": event.units,
            "status_detail": event.status_detail,
            "original_transcription": event.original_transcription,
            "summary": event.summary,
            "created_at": _iso_utc(event.created_at, assume_utc=True),
            "incident_at": _iso_utc(incident_at) if incident_at else None,
            "closed_at": _iso_utc(event.closed_at, assume_utc=True),
        },
        "transcripts": transcripts,
    }


@router.post("/events/{event_id}/geocode")
async def geocode_event(
    event_id: str,
    current_user: User = Depends(get_current_active_user),
    events_db: Session = Depends(get_events_db),
):
    """Manually trigger / refresh geocoding for an event."""
    event = events_db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not event.location or not event.location.strip() or event.location.strip() == "N/A":
        return {"ok": False, "message": "Event has no valid location"}

    monitor = events_db.query(Monitor).filter(Monitor.id == event.monitor_id).first()
    geo_region = monitor.geo_region if monitor else None

    from ..services.geocoder_service import resolve_address_sync
    res = resolve_address_sync(event.location, geo_region)
    if not res:
        return {"ok": False, "message": "Address could not be geocoded"}

    event.latitude = res.latitude
    event.longitude = res.longitude
    event.resolved_address = res.resolved_address
    events_db.commit()

    from ..services.websocket import websocket_manager
    websocket_manager.broadcast_sync({
        "type": "event_geocoded",
        "data": {
            "event_id": event_id,
            "monitor_id": event.monitor_id,
            "location": event.location,
            "latitude": res.latitude,
            "longitude": res.longitude,
            "resolved_address": res.resolved_address,
        }
    })

    return {
        "ok": True,
        "latitude": res.latitude,
        "longitude": res.longitude,
        "resolved_address": res.resolved_address,
    }


@router.post("/events/{event_id}/close")
async def close_event(
    event_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_events_db),
):
    """
    Mark event closed: status=closed, closed_at=now.
    Pipeline ignores closed events (no new attach/dedupe). Transcripts and links stay.
    Idempotent if already closed.
    """
    event = db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.status != "closed":
        event.status = "closed"
        event.closed_at = dt.now(timezone.utc)
        db.commit()
    return {"ok": True, "status": "closed"}


@router.post("/events/{event_id}/reopen")
async def reopen_event(
    event_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_events_db),
):
    """Reopen a closed event: status=open, closed_at=None. Idempotent if already open."""
    event = db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.status != "open":
        event.status = "open"
        event.closed_at = None
        db.commit()
    return {"ok": True, "status": "open"}


@router.delete("/events/{event_id}")
async def delete_event(
    event_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_events_db),
):
    """Delete an event and its transcript links."""
    event = db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    db.query(EventTranscriptLink).filter(EventTranscriptLink.event_id == event.id).delete()
    db.delete(event)
    db.commit()
    return {"ok": True}


@router.get("/ner-labels")
async def ner_labels(
    current_user: User = Depends(get_current_active_user),
):
    """Supported NER labels for Start event by label."""
    return {"labels": sorted(ENTITY_LABELS)}


@router.get("/debug")
async def events_debug(
    limit: Optional[int] = Query(80, ge=1, le=200),
    current_user: User = Depends(get_current_admin_user),
):
    """Recent NER pipeline debug entries (newest first). In-memory only."""
    return get_debug_recent(limit)


@router.delete("/debug")
async def clear_events_debug(
    current_user: User = Depends(get_current_admin_user),
):
    """Clear all NER pipeline debug entries."""
    removed = clear_debug_all()
    return {"ok": True, "removed": removed}


@router.get("/llm-status")
async def events_llm_status(
    current_user: User = Depends(get_current_active_user),
):
    """NER model status for Events pipeline."""
    from ..services.ner_service import is_loaded
    settings = get_settings()
    cfg = getattr(settings.config, "events_pipeline", None)
    if not cfg or not cfg.enabled or not cfg.ner_model_path:
        return {"enabled": False, "ner_model_path": "", "status": "disabled", "message": "Events pipeline disabled"}
    if is_loaded():
        return {"enabled": True, "ner_model_path": cfg.ner_model_path, "status": "ok"}
    return {"enabled": True, "ner_model_path": cfg.ner_model_path, "status": "unreachable", "message": "NER model not loaded"}
