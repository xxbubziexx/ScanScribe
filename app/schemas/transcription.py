"""Pydantic v2 schemas for transcriptions."""
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class TranscriptionCardItem(BaseModel):
    """Single transcription card model for dashboard feeds."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    transcript: Optional[str] = None
    talkgroup: Optional[str] = None
    timestamp: str
    confidence: Optional[float] = None
    audio_path: Optional[str] = None
    duration: Optional[float] = None
    file_size: Optional[int] = None


class RecentTranscriptionsResponse(BaseModel):
    """Response model for recent transcriptions endpoint."""
    transcriptions: List[TranscriptionCardItem]
