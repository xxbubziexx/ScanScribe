"""Events pipeline API router package."""
from fastapi import APIRouter

from .admin_router import router as admin_router
from .common import (
    batch_event_link_aggregates,
    event_type_csv_display,
    iso_utc,
    start_labels,
)
from .geocode_router import router as geocode_router
from .incidents_router import router as incidents_router
from .monitors_router import router as monitors_router
from .spans_router import router as spans_router

router = APIRouter(prefix="/api/events", tags=["events"])

# Mount all domain sub-routers
router.include_router(monitors_router)
router.include_router(spans_router)
router.include_router(incidents_router)
router.include_router(geocode_router)
router.include_router(admin_router)

__all__ = [
    "router",
    "iso_utc",
    "start_labels",
    "batch_event_link_aggregates",
    "event_type_csv_display",
]
