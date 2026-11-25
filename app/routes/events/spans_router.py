"""Spans and entity observations sub-router."""
import csv
import io
import re
from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...database import get_events_db
from ...models.event import EntityObservation, Event, EventTranscriptLink, SpanStore
from ...models.user import User
from ...schemas.event import (
    EntityCsvExportRequest,
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


def _apply_entity_filters(
    qry,
    *,
    labels: List[str],
    ids: Optional[List[int]],
    monitor_id: Optional[int],
    talkgroup: Optional[str],
    log_entry_id: Optional[int],
    span_store_id: Optional[int],
    q: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
):
    """Apply shared entity observation filters cleanly across browse and export."""
    if ids:
        qry = qry.filter(EntityObservation.id.in_(ids))
    if labels:
        qry = qry.filter(EntityObservation.label.in_(labels))
    if monitor_id is not None:
        qry = qry.filter(EntityObservation.monitor_id == monitor_id)
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
    return qry


def _slug_for_labels(labels: List[str]) -> str:
    """Build a safe lowercase filename slug representing selected NER labels."""
    if not labels:
        return "all"
    joined = "_".join(re.sub(r"[^a-z0-9]+", "", lbl.lower()) for lbl in labels[:3] if lbl)
    if len(labels) > 3:
        joined = f"{joined}_plus"
    return joined or "all"


@router.post("/entities/export-csv")
def export_entities_csv(
    payload: EntityCsvExportRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_events_db),
):
    """Export raw NER entity values (with optional deduplication and context) as CSV."""
    labels = list(dict.fromkeys(lbl.strip().upper() for lbl in payload.labels if lbl and lbl.strip()))
    ids = list(dict.fromkeys(payload.ids)) if payload.ids else None
    single_label = len(labels) == 1

    buf = io.StringIO()
    writer = csv.writer(buf)
    row_count = 0

    if not payload.include_context and not payload.deduplicate:
        writer.writerow(["raw"] if single_label else ["label", "raw"])
        qry = _apply_entity_filters(
            db.query(EntityObservation.label, EntityObservation.raw),
            labels=labels,
            ids=ids,
            monitor_id=payload.monitor_id,
            talkgroup=payload.talkgroup,
            log_entry_id=payload.log_entry_id,
            span_store_id=payload.span_store_id,
            q=payload.q,
            date_from=payload.date_from,
            date_to=payload.date_to,
        )
        rows = qry.order_by(EntityObservation.id.desc()).limit(payload.limit).all()
        for lbl, raw in rows:
            writer.writerow([raw] if single_label else [lbl, raw])
            row_count += 1

    elif not payload.include_context and payload.deduplicate:
        header = (["raw", "count"] if payload.include_counts else ["raw"]) if single_label else (
            ["label", "raw", "count"] if payload.include_counts else ["label", "raw"]
        )
        writer.writerow(header)
        count_expr = func.count(EntityObservation.id)
        qry = _apply_entity_filters(
            db.query(EntityObservation.label, EntityObservation.raw, count_expr),
            labels=labels,
            ids=ids,
            monitor_id=payload.monitor_id,
            talkgroup=payload.talkgroup,
            log_entry_id=payload.log_entry_id,
            span_store_id=payload.span_store_id,
            q=payload.q,
            date_from=payload.date_from,
            date_to=payload.date_to,
        )
        rows = (
            qry.group_by(EntityObservation.label, EntityObservation.raw)
            .order_by(count_expr.desc(), EntityObservation.raw.asc())
            .limit(payload.limit)
            .all()
        )
        for lbl, raw, cnt in rows:
            if single_label:
                writer.writerow([raw, int(cnt)] if payload.include_counts else [raw])
            else:
                writer.writerow([lbl, raw, int(cnt)] if payload.include_counts else [lbl, raw])
            row_count += 1

    elif payload.include_context and not payload.deduplicate:
        writer.writerow([
            "id",
            "timestamp",
            "label",
            "raw",
            "canonical",
            "talkgroup",
            "monitor_id",
            "span_store_id",
            "log_entry_id",
            "transcript",
        ])
        qry = _apply_entity_filters(
            db.query(EntityObservation, SpanStore.transcript).outerjoin(
                SpanStore, EntityObservation.span_store_id == SpanStore.id
            ),
            labels=labels,
            ids=ids,
            monitor_id=payload.monitor_id,
            talkgroup=payload.talkgroup,
            log_entry_id=payload.log_entry_id,
            span_store_id=payload.span_store_id,
            q=payload.q,
            date_from=payload.date_from,
            date_to=payload.date_to,
        )
        rows = qry.order_by(EntityObservation.id.desc()).limit(payload.limit).all()
        for obs, transcript in rows:
            writer.writerow([
                obs.id,
                iso_utc(obs.ts, assume_utc=True) or "",
                obs.label,
                obs.raw,
                obs.canonical,
                obs.talkgroup or "",
                obs.monitor_id,
                obs.span_store_id,
                obs.log_entry_id if obs.log_entry_id is not None else "",
                transcript or "",
            ])
            row_count += 1

    else:
        writer.writerow(["label", "raw", "count", "talkgroups", "first_seen", "last_seen"])
        count_expr = func.count(EntityObservation.id)
        qry = _apply_entity_filters(
            db.query(
                EntityObservation.label,
                EntityObservation.raw,
                count_expr,
                func.group_concat(EntityObservation.talkgroup, "\x1f"),
                func.min(EntityObservation.ts),
                func.max(EntityObservation.ts),
            ),
            labels=labels,
            ids=ids,
            monitor_id=payload.monitor_id,
            talkgroup=payload.talkgroup,
            log_entry_id=payload.log_entry_id,
            span_store_id=payload.span_store_id,
            q=payload.q,
            date_from=payload.date_from,
            date_to=payload.date_to,
        )
        rows = (
            qry.group_by(EntityObservation.label, EntityObservation.raw)
            .order_by(count_expr.desc(), EntityObservation.raw.asc())
            .limit(payload.limit)
            .all()
        )
        for lbl, raw, cnt, tg_concat, first_ts, last_ts in rows:
            distinct_tgs = sorted({t.strip() for t in (tg_concat or "").split("\x1f") if t and t.strip()})
            writer.writerow([
                lbl,
                raw,
                int(cnt),
                " | ".join(distinct_tgs),
                iso_utc(first_ts, assume_utc=True) or "",
                iso_utc(last_ts, assume_utc=True) or "",
            ])
            row_count += 1

    buf.seek(0)
    filename = f"scanscribe_ner_{_slug_for_labels(labels)}_{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "X-Row-Count": str(row_count),
        },
    )
