"""API endpoint for recent transcriptions."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from ..database import get_logs_db
from ..models.user import User
from ..models.log_entry import LogEntry
from ..schemas.transcription import RecentTranscriptionsResponse, TranscriptionCardItem
from .auth import get_current_active_user

router = APIRouter(prefix="/api/transcriptions", tags=["transcriptions"])


@router.get("/recent", response_model=RecentTranscriptionsResponse)
def get_recent_transcriptions(
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db)
) -> RecentTranscriptionsResponse:
    """Get recent transcriptions for dashboard display. Runs in threadpool to avoid blocking event loop."""
    # Query most recent transcriptions (exclude soft-deleted)
    logs = db.query(LogEntry).filter(
        LogEntry.is_deleted == False
    ).order_by(LogEntry.timestamp.desc()).limit(limit).all()
    
    # Format for dashboard cards
    transcriptions = [
        TranscriptionCardItem(
            id=log.id,
            filename=log.filename,
            transcript=log.transcript,
            talkgroup=log.talkgroup,
            timestamp=log.timestamp.isoformat(),
            confidence=log.confidence,
            audio_path=log.audio_path,
            duration=log.duration,
            file_size=log.file_size
        )
        for log in logs
    ]
    
    return RecentTranscriptionsResponse(transcriptions=transcriptions)

