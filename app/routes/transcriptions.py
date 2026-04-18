"""API endpoint for recent transcriptions."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from ..database import get_logs_db
from ..models.user import User
from ..models.log_entry import LogEntry
from .auth import get_current_active_user

router = APIRouter(prefix="/api/transcriptions", tags=["transcriptions"])


@router.get("/recent")
async def get_recent_transcriptions(
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db)
):
    """Get recent transcriptions for dashboard display."""
    # Query most recent transcriptions (exclude soft-deleted)
    logs = db.query(LogEntry).filter(
        LogEntry.is_deleted == False
    ).order_by(LogEntry.timestamp.desc()).limit(limit).all()
    
    # Format for dashboard cards
    transcriptions = []
    for log in logs:
        transcriptions.append({
            "id": log.id,
            "filename": log.filename,
            "transcript": log.transcript,
            "talkgroup": log.talkgroup,
            "timestamp": log.timestamp.isoformat(),
            "confidence": log.confidence,
            "audio_path": log.audio_path,
            "duration": log.duration,
            "file_size": log.file_size
        })
    
    return {"transcriptions": transcriptions}
