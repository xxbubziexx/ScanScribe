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
    
    # Calculate cutoff date
    cutoff_date = (datetime.now() - timedelta(days=request.retention_days)).strftime('%Y-%m-%d')
    
    # Get entries to delete
    entries_to_delete = db.query(LogEntry).filter(
        LogEntry.log_date < cutoff_date
    ).all()
    
    deleted_count = len(entries_to_delete)
    audio_files_deleted = 0
    
    # Delete audio files and DB entries
    audio_dir = Path(settings.output_dir)
    for entry in entries_to_delete:
        try:
            if entry.audio_path and entry.audio_path != "file not saved":
                path = audio_dir / Path(entry.audio_path).name
                if not path.exists() and entry.filename:
                    path = audio_dir / entry.filename
                if path.exists():
                    path.unlink()
                    audio_files_deleted += 1
            elif entry.filename:
                path = audio_dir / entry.filename
                if path.exists():
                    path.unlink()
                    audio_files_deleted += 1
        except Exception as e:
            logger.warning(f"Error deleting audio file: {e}")
        
        # Delete DB entry
        db.delete(entry)
    
    db.commit()
    
    return PurgeResponse(
        message=f"Purged data older than {request.retention_days} days",
        deleted_count=deleted_count,
        audio_files_deleted=audio_files_deleted,
        cutoff_date=cutoff_date
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


