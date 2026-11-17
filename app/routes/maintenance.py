"""Maintenance routes for database cleanup and stats."""
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_logs_db
from ..models.log_entry import LogEntry
from ..models.user import User
from ..services.retention import run_retention
from ..schemas.maintenance import (
    DatabaseStatsResponse,
    PurgeResponse,
    RedactSsnResponse,
    RetentionConfigResponse,
)
from .auth import get_current_active_user

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])
logger = logging.getLogger(__name__)
settings = get_settings()


@router.get("/retention-config", response_model=RetentionConfigResponse)
def get_retention_config(
    current_user: User = Depends(get_current_active_user)
) -> RetentionConfigResponse:
    """Return retention_days and cleanup_hour from config for manual cleanup UI."""
    s = get_settings()
    return RetentionConfigResponse(
        retention_days=s.config.storage.retention_days,
        cleanup_hour=s.config.storage.cleanup_hour,
    )


class PurgeRequest(BaseModel):
    """Request to purge old data."""
    retention_days: int


@router.get("/stats", response_model=DatabaseStatsResponse)
def get_database_stats(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db)
) -> DatabaseStatsResponse:
    """Get database statistics. Runs in threadpool to prevent blocking the event loop."""
    # Get oldest and newest entries
    oldest = db.query(LogEntry.log_date).filter(LogEntry.log_date.isnot(None)).order_by(LogEntry.log_date.asc()).first()
    newest = db.query(LogEntry.log_date).filter(LogEntry.log_date.isnot(None)).order_by(LogEntry.log_date.desc()).first()
    total = db.query(func.count(LogEntry.id)).scalar()
    
    # Calculate days of data
    days_of_data = 0
    if oldest and newest and oldest[0] and newest[0]:
        try:
            oldest_date = datetime.strptime(oldest[0], '%Y-%m-%d')
            newest_date = datetime.strptime(newest[0], '%Y-%m-%d')
            days_of_data = (newest_date - oldest_date).days + 1
        except (ValueError, TypeError):
            pass
    
    return DatabaseStatsResponse(
        total_entries=total or 0,
        oldest_date=oldest[0] if oldest else None,
        newest_date=newest[0] if newest else None,
        days_of_data=days_of_data
    )


@router.post("/purge", response_model=PurgeResponse)
def purge_old_data(
    request: PurgeRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db)
) -> PurgeResponse:
    """Purge data older than retention period. Runs in threadpool to avoid event loop stalling."""
    if request.retention_days == 0:
        return PurgeResponse(
            message="Retention set to never delete",
            deleted_count=0,
            audio_files_deleted=0,
            cutoff_date=None
        )
    
    # Delegate to the date-driven retention service. The old implementation walked ORM
    # rows, deleted the row even when the file could not be removed (creating orphans no
    # later run can see), let the FK SET NULL rules blank dependents instead of removing
    # them, and reported counters derived from row count only.
    report = run_retention(request.retention_days, dry_run=False, session=db)

    logger.info(
        "retention purge by %s: transmissions=%d audio=%d (%.1f MB) orphans=%d "
        "span_store=%d observations=%d links=%d events=%d summaries=%d cutoff=%s",
        current_user.username,
        report.log_entries,
        report.audio_files_deleted,
        report.audio_bytes_freed / 1e6,
        report.orphan_files_deleted,
        report.span_store,
        report.entity_observations,
        report.event_links,
        report.events,
        report.hour_summaries,
        report.cutoff_date,
    )

    return PurgeResponse(
        message=(
            f"Purged {report.log_entries} transmissions, {report.events} events and "
            f"{report.hour_summaries} hour summaries older than "
            f"{request.retention_days} days (cutoff {report.cutoff_date})"
        ),
        deleted_count=report.log_entries + report.events + report.hour_summaries,
        audio_files_deleted=report.audio_files_deleted + report.orphan_files_deleted,
        cutoff_date=report.cutoff_date,
    )


class RedactSsnRequest(BaseModel):
    replacement: Optional[str] = None
    dry_run: bool = False


@router.post("/redact-ssn", response_model=RedactSsnResponse)
async def trigger_ssn_redaction(
    request: RedactSsnRequest = RedactSsnRequest(),
    current_user: User = Depends(get_current_active_user),
) -> RedactSsnResponse:
    """Scan and redact historical SSNs from all database tables asynchronously. Admin only."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    from ..services.redaction_service import scrub_database_ssn
    try:
        stats = await asyncio.to_thread(
            scrub_database_ssn,
            replacement=request.replacement,
            dry_run=request.dry_run
        )
        return RedactSsnResponse(ok=True, stats=stats)
    except Exception as exc:
        logger.exception("SSN scrub failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


