"""Monitors (departments) CRUD sub-router."""
from datetime import datetime as dt
import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...database import get_events_db
from ...models.event import EntityObservation, Event, EventTranscriptLink, Monitor
from ...models.user import User
from ...schemas.monitor import MonitorCreate, MonitorResponse, MonitorUpdate
from ...services.events_common import parse_json_list
from ...services.events_worker import invalidate_monitor_index_cache
from ..auth import get_current_active_user
from .common import start_labels

router = APIRouter()


@router.get("/units/today")
async def get_units_today(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_events_db),
):
    """Get distinct UNIT canonical values logged today (for the config UI defaults)."""
    today_start = dt.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (
        db.query(EntityObservation.raw)
        .filter(
            EntityObservation.label == "UNIT",
            EntityObservation.ts >= today_start,
        )
        .distinct()
        .all()
    )
    units = [r[0] for r in rows if r[0]]
    units.sort()
    return {"units": units}


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
            start_event_labels=start_labels(m.keyword_config),
            geo_region=m.geo_region,
            known_units=m.known_units,
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
        known_units=(body.known_units or "").strip() or None,
        talkgroup_ids=json.dumps(body.talkgroup_ids),
        keyword_config=json.dumps(labels),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    invalidate_monitor_index_cache()
    return MonitorResponse(
        id=m.id,
        name=m.name,
        enabled=m.enabled,
        talkgroup_ids=body.talkgroup_ids,
        start_event_labels=labels,
        geo_region=m.geo_region,
        known_units=m.known_units,
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
    if body.known_units is not None:
        m.known_units = body.known_units.strip() or None
    if body.talkgroup_ids is not None:
        m.talkgroup_ids = json.dumps(body.talkgroup_ids)
    if body.start_event_labels is not None:
        m.keyword_config = json.dumps(body.start_event_labels)
    db.add(m)
    db.commit()
    db.refresh(m)
    invalidate_monitor_index_cache()
    return MonitorResponse(
        id=m.id,
        name=m.name,
        enabled=m.enabled,
        talkgroup_ids=parse_json_list(m.talkgroup_ids),
        start_event_labels=start_labels(m.keyword_config),
        geo_region=m.geo_region,
        known_units=m.known_units,
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
    invalidate_monitor_index_cache()
    return {"ok": True}
