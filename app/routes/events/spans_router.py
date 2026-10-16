"""Spans and entity observations sub-router."""
from collections import defaultdict
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...database import get_events_db
from ...models.event import EntityObservation, Event, EventTranscriptLink, SpanStore
from ...models.user import User
from ...schemas.event import (
    EntityObservationItem,
    EntityObservationListResponse,
    SpanStoreItem,
    SpanStoreListResponse,
)
from ..auth import get_current_active_user
from .common import iso_utc

router = APIRouter()


@router.get("/span-store", response_model=SpanStoreListResponse)
@router.get("/spans", response_model=SpanStoreListResponse)
async def list_span_store(
    monitor_id: Optional[int] = Query(None, ge=1),
    talkgroup: Optional[str] = Query(None, max_length=255),
    log_entry_id: Optional[int] = Query(None, ge=1),
    q: Optional[str] = Query(None, max_length=500, description="Substring search in transcript"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD) inclusive"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD) inclusive"),
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
    if date_from and date_from.strip():
        qry = qry.filter(SpanStore.created_at >= f"{date_from.strip()} 00:00:00")
    if date_to and date_to.strip():
        qry = qry.filter(SpanStore.created_at <= f"{date_to.strip()} 23:59:59.999999")
    if q and q.strip():
        qry = qry.filter(SpanStore.transcript.ilike(f"%{q.strip()}%"))
    total = qry.count()

    col = getattr(SpanStore, sort_by or "id", SpanStore.id)
    if (sort_order or "desc").lower() == "asc":
        qry = qry.order_by(col.asc())
    else:
        qry = qry.order_by(col.desc())

    rows = qry.offset(offset).limit(limit).all()
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
                created_at=iso_utc(r.created_at, assume_utc=True),
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
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD) inclusive"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD) inclusive"),
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
    if date_from and date_from.strip():
        qry = qry.filter(EntityObservation.ts >= f"{date_from.strip()} 00:00:00")
    if date_to and date_to.strip():
        qry = qry.filter(EntityObservation.ts <= f"{date_to.strip()} 23:59:59.999999")
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
            ts=iso_utc(r.ts, assume_utc=True),
            label=r.label,
            canonical=r.canonical,
            raw=r.raw,
        )
        for r in rows
    ]
    return EntityObservationListResponse(items=items, total=total)
