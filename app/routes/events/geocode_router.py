"""Geocoding utilities sub-router."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...database import get_events_db
from ...models.event import Monitor
from ...models.user import User
from ...services.geocoder_service import reverse_geocode_sync, search_address_candidates
from ..auth import get_current_active_user

router = APIRouter()


class ReverseGeocodeRequest(BaseModel):
    latitude: float
    longitude: float


@router.get("/geocoder/autocomplete")
async def autocomplete_address_endpoint(
    query: str = Query(..., min_length=2),
    monitor_id: Optional[int] = Query(None),
    limit: int = Query(5, ge=1, le=10),
    current_user: User = Depends(get_current_active_user),
    events_db: Session = Depends(get_events_db),
):
    """Get address candidate suggestions matching query, scoped to monitor's geo_region."""
    geo_region = None
    if monitor_id is not None:
        monitor = events_db.query(Monitor).filter(Monitor.id == monitor_id).first()
        if monitor:
            geo_region = monitor.geo_region

    candidates = search_address_candidates(query, geo_region=geo_region, limit=limit)
    return {"candidates": candidates}


@router.post("/geocoder/reverse")
async def reverse_geocode_endpoint(
    payload: ReverseGeocodeRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Reverse geocode coordinates to a structured address."""
    addr = reverse_geocode_sync(payload.latitude, payload.longitude)
    return {"resolved_address": addr}
