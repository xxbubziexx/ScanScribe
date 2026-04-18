"""Maintenance routes for database cleanup and stats."""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from datetime import datetime, timedelta
from pathlib import Path

from ..database import get_logs_db
from ..models.user import User
from ..models.log_entry import LogEntry
from .auth import get_current_active_user
from ..config import get_settings

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])
logger = logging.getLogger(__name__)
settings = get_settings()


@router.get("/retention-config")
async def get_retention_config(
    current_user: User = Depends(get_current_active_user)
):
    """Return retention_days and cleanup_hour from config for manual cleanup UI."""
    s = get_settings()
    return {
        "retention_days": s.config.storage.retention_days,
        "cleanup_hour": s.config.storage.cleanup_hour,
    }


class PurgeRequest(BaseModel):
    """Request to purge old data."""
    retention_days: int


@router.get("/stats")
async def get_database_stats(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db)
):
    """Get database statistics."""
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
    
    return {
        "total_entries": total,
        "oldest_date": oldest[0] if oldest else None,
        "newest_date": newest[0] if newest else None,
        "days_of_data": days_of_data
    }


@router.post("/purge")
async def purge_old_data(
    request: PurgeRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db)
):
    """Purge data older than retention period."""
    # Check if user is admin (optional, for now allow all authenticated users)
    # if not current_user.is_admin:
    #     raise HTTPException(status_code=403, detail="Admin access required")
    
    if request.retention_days == 0:
        return {
            "message": "Retention set to never delete",
            "deleted_count": 0,
            "audio_files_deleted": 0
        }
    
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
                # audio_path is e.g. "audio_storage/filename.mp3"
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
    
    return {
        "message": f"Purged data older than {request.retention_days} days",
        "deleted_count": deleted_count,
        "audio_files_deleted": audio_files_deleted,
        "cutoff_date": cutoff_date
    }
