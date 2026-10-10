"""Event lifecycle, editing, detail querying, and export sub-router."""
import csv
from datetime import date, datetime as dt, timezone
import io
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...database import get_events_db, get_logs_db
from ...models.event import Event, EventTranscriptLink, Monitor
from ...models.log_entry import LogEntry
from ...models.user import User
from ...schemas.event import EventResponse
from ...services.events_router_engine import OpenRouterRateLimitManager
from ...services.events_worker import (
    dispatch_geocoding_for_event,
    summarize_event_attachments,
)
from ...services.geocoder_service import resolve_address_sync, reverse_geocode_sync
from ...services.websocket import websocket_manager
from ..auth import get_current_active_user
from .common import batch_event_link_aggregates, event_type_csv_display, iso_utc

router = APIRouter()


class SetCoordinatesRequest(BaseModel):
    latitude: float
    longitude: float
    resolved_address: Optional[str] = None
    reverse_lookup: bool = False


class EventUpdateRequest(BaseModel):
    location: Optional[str] = None
    event_type: Optional[str] = None
    status_detail: Optional[str] = None
    units: Optional[str] = None


@router.get("/events")
async def list_events(
    monitor_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None, max_length=500, description="Search in summary, location, units, transcript"),
    sort_by: Optional[str] = Query("updated_at", pattern="^(id|event_id|created_at|updated_at|closed_at|status|event_type|location)$"),
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

    if sort_by == "updated_at":
        sort_col = func.coalesce(Event.updated_at, Event.created_at)
        if (sort_order or "desc").lower() == "asc":
            query = query.order_by(sort_col.asc(), Event.id.asc())
        else:
            query = query.order_by(sort_col.desc(), Event.id.desc())
    else:
        col = getattr(Event, sort_by or "updated_at", Event.updated_at)
        if (sort_order or "desc").lower() == "asc":
            query = query.order_by(col.asc(), Event.id.asc())
        else:
            query = query.order_by(col.desc(), Event.id.desc())

    events = query.offset(offset).limit(limit).all()
    event_ids = [e.id for e in events]
    (
        link_counts,
        talkgroup_str_map,
        first_span_at_by_event,
        last_span_at_by_event,
        audio_path_by_event,
    ) = batch_event_link_aggregates(events_db, logs_db, event_ids)

    out = []
    for e in events:
        spans_attached = link_counts.get(e.id, 0)
        talkgroup_str = talkgroup_str_map.get(e.id, "")
        incident_at = first_span_at_by_event.get(e.id)
        last_span_at = last_span_at_by_event.get(e.id)
        out.append(
            EventResponse(
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
                created_at=iso_utc(e.created_at, assume_utc=True),
                updated_at=iso_utc(e.updated_at, assume_utc=True),
                incident_at=iso_utc(incident_at) if incident_at else None,
                last_span_at=iso_utc(last_span_at) if last_span_at else None,
                closed_at=iso_utc(e.closed_at, assume_utc=True),
                spans_attached=spans_attached,
                talkgroup=talkgroup_str,
                audio_path=audio_path_by_event.get(e.id),
            )
        )
    return {"items": out, "total": total, "rate_limit": OpenRouterRateLimitManager.get_status()}


@router.get("/events/export-headers")
async def export_events_normalized_headers(
    monitor_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(10000, ge=1, le=50000),
    current_user: User = Depends(get_current_active_user),
    events_db: Session = Depends(get_events_db),
    logs_db: Session = Depends(get_logs_db),
):
    """Download CSV of pipeline-normalized headers."""
    q = events_db.query(Event).order_by(Event.created_at.desc())
    if monitor_id is not None:
        q = q.filter(Event.monitor_id == monitor_id)
    if status:
        q = q.filter(Event.status == status)
    rows = q.limit(limit).all()
    event_ids = [e.id for e in rows]
    monitors = {m.id: m.name for m in events_db.query(Monitor).all()}
    link_counts, talkgroup_str_map, first_span_at_by_event, _, _ = batch_event_link_aggregates(
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
                event_type_csv_display(e),
                (e.location or "").strip(),
                e.latitude if e.latitude is not None else "",
                e.longitude if e.longitude is not None else "",
                (e.resolved_address or "").strip(),
                (e.units or "").strip(),
                (e.status_detail or "").strip(),
                (e.summary or "").replace("\r\n", " ").replace("\n", " ").strip(),
                link_counts.get(e.id, 0),
                talkgroup_str_map.get(e.id, ""),
                iso_utc(first_span_at_by_event.get(e.id)) if first_span_at_by_event.get(e.id) else "",
                iso_utc(e.created_at, assume_utc=True) or "",
                iso_utc(e.closed_at, assume_utc=True) or "",
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
    """Get one event by event_id with header and linked transcripts."""
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
            transcripts.append(
                {
                    "log_entry_id": log_entry.id,
                    "timestamp": log_entry.timestamp.isoformat() if log_entry.timestamp else None,
                    "talkgroup": log_entry.talkgroup or "N/A",
                    "transcript": t_text,
                    "entities": entities,
                    "audio_path": log_entry.audio_path or "",
                    "has_playback": has_playback,
                    "is_trigger": t_text.strip() == (event.original_transcription or "").strip(),
                    "llm_reason": (getattr(link, "llm_reason", None) or "").strip(),
                }
            )
    span_times = [le.timestamp for le in log_entries.values() if le and le.timestamp]
    incident_at = min(span_times) if span_times else None
    last_span_at = max(span_times) if span_times else None
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
            "created_at": iso_utc(event.created_at, assume_utc=True),
            "updated_at": iso_utc(event.updated_at, assume_utc=True),
            "incident_at": iso_utc(incident_at) if incident_at else None,
            "last_span_at": iso_utc(last_span_at) if last_span_at else None,
            "closed_at": iso_utc(event.closed_at, assume_utc=True),
        },
        "transcripts": transcripts,
    }


@router.post("/events/{event_id}/remove-geocode")
async def remove_geocode(
    event_id: str,
    current_user: User = Depends(get_current_active_user),
    events_db: Session = Depends(get_events_db),
):
    event = events_db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    event.latitude = None
    event.longitude = None
    event.resolved_address = None
    events_db.commit()

    websocket_manager.broadcast_sync(
        {
            "type": "event_geocoded",
            "data": {
                "event_id": event_id,
                "monitor_id": event.monitor_id,
                "location": event.location,
                "latitude": None,
                "longitude": None,
                "resolved_address": None,
            },
        }
    )
    return {"ok": True, "message": "Pin removed"}


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

    res = resolve_address_sync(event.location, geo_region)
    if not res:
        return {"ok": False, "message": "Address could not be geocoded"}

    event.latitude = res.latitude
    event.longitude = res.longitude
    event.resolved_address = res.resolved_address
    events_db.commit()

    websocket_manager.broadcast_sync(
        {
            "type": "event_geocoded",
            "data": {
                "event_id": event_id,
                "monitor_id": event.monitor_id,
                "location": event.location,
                "latitude": res.latitude,
                "longitude": res.longitude,
                "resolved_address": res.resolved_address,
            },
        }
    )

    return {
        "ok": True,
        "latitude": res.latitude,
        "longitude": res.longitude,
        "resolved_address": res.resolved_address,
    }


@router.post("/events/{event_id}/set-coordinates")
async def set_event_coordinates(
    event_id: str,
    payload: SetCoordinatesRequest,
    current_user: User = Depends(get_current_active_user),
    events_db: Session = Depends(get_events_db),
):
    """Set custom coordinates for an event."""
    event = events_db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    event.latitude = payload.latitude
    event.longitude = payload.longitude

    address = payload.resolved_address
    if payload.reverse_lookup or not address:
        rev = reverse_geocode_sync(payload.latitude, payload.longitude)
        if rev:
            address = rev

    if address:
        event.resolved_address = address
        event.location = address

    events_db.commit()

    websocket_manager.broadcast_sync(
        {
            "type": "event_geocoded",
            "data": {
                "event_id": event_id,
                "monitor_id": event.monitor_id,
                "location": event.location,
                "latitude": event.latitude,
                "longitude": event.longitude,
                "resolved_address": event.resolved_address,
            },
        }
    )
    websocket_manager.broadcast_sync(
        {
            "type": "event_update",
            "action": "update",
            "data": {
                "id": event.id,
                "event_id": event.event_id,
                "monitor_id": event.monitor_id,
                "status": event.status,
                "event_type": event.event_type,
                "location": event.location,
                "resolved_address": event.resolved_address,
                "latitude": event.latitude,
                "longitude": event.longitude,
                "units": event.units,
                "status_detail": event.status_detail,
            },
        }
    )
    return {
        "ok": True,
        "latitude": event.latitude,
        "longitude": event.longitude,
        "resolved_address": event.resolved_address,
        "location": event.location,
    }


@router.post("/events/{event_id}/close")
async def close_event(
    event_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_events_db),
):
    """Mark event closed."""
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
    """Reopen a closed event."""
    event = db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.status != "open":
        event.status = "open"
        event.closed_at = None
        db.commit()
    return {"ok": True, "status": "open"}


@router.patch("/events/{event_id}")
async def update_event_details(
    event_id: str,
    payload: EventUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    events_db: Session = Depends(get_events_db),
):
    """Update canonical fields of an event."""
    event = events_db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    loc_changed = False
    if payload.location is not None:
        new_loc = payload.location.strip() or None
        if new_loc != event.location:
            event.location = new_loc
            loc_changed = True

    if payload.event_type is not None:
        event.event_type = payload.event_type.strip() or event.event_type

    if payload.status_detail is not None:
        event.status_detail = payload.status_detail.strip() or None

    if payload.units is not None:
        event.units = payload.units.strip() or None

    events_db.commit()

    if loc_changed and event.location:
        dispatch_geocoding_for_event(event.event_id, event.location, event.monitor_id)

    websocket_manager.broadcast_sync(
        {
            "type": "event_update",
            "action": "update",
            "data": {
                "id": event.id,
                "event_id": event.event_id,
                "monitor_id": event.monitor_id,
                "status": event.status,
                "event_type": event.event_type,
                "location": event.location,
                "resolved_address": event.resolved_address,
                "units": event.units,
                "status_detail": event.status_detail,
            },
        }
    )

    return {
        "ok": True,
        "event_id": event.event_id,
        "location": event.location,
        "event_type": event.event_type,
        "units": event.units,
        "status_detail": event.status_detail,
    }


@router.post("/events/{event_id}/summarize")
@router.post("/{event_id}/summarize")
async def summarize_event_endpoint(
    event_id: str,
    current_user: User = Depends(get_current_active_user),
    events_db: Session = Depends(get_events_db),
    logs_db: Session = Depends(get_logs_db),
):
    """Generate or refresh the event header summary based on linked attachments."""
    event = events_db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    summary = summarize_event_attachments(event, events_db, logs_db, force=True)

    websocket_manager.broadcast_sync(
        {
            "type": "event_update",
            "action": "attach",
            "data": {
                "id": event.id,
                "event_id": event.event_id,
                "monitor_id": event.monitor_id,
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
                "talkgroup": "",
            },
        }
    )

    return {"ok": True, "event_id": event.event_id, "summary": summary}


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
