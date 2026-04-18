"""Log entry model for transcription logs."""
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Index, Boolean
from ..database import LogsBase as Base, utcnow


class LogEntry(Base):
    """Transcription log entry model."""
    
    __tablename__ = "log_entries"
    
    # Primary identification
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False, index=True)  # Original filename (always stored)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)  # Actual datetime
    log_date = Column(String(10), index=True)  # YYYY-MM-DD format for easy querying
    
    # Audio metadata
    duration = Column(Float, default=0.0)  # Duration in seconds
    file_size = Column(Integer, default=0)  # Size in bytes
    audio_path = Column(String(500), default="file not saved")  # Path to saved audio or "file not saved"
    
    # Transcription data
    transcript = Column(Text, nullable=False)  # Full transcription text
    language = Column(String(10), default="en")  # Detected/specified language
    confidence = Column(Float, default=0.0)  # Average confidence score (0-1)
    
    # Processing metadata
    model_used = Column(String(100), default="whisper-small")  # Which model processed this
    processing_time = Column(Float, default=0.0)  # Time taken to transcribe (seconds)
    uploaded_by = Column(String(100), nullable=True)  # Username if uploaded via client
    
    # Optional metadata (for scanner audio)
    talkgroup = Column(String(50), default="N/A")  # Scanner talkgroup/channel
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=utcnow)
    
    # Soft delete for retention policy
    is_deleted = Column(Boolean, default=False, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Create indexes for performance
    __table_args__ = (
        Index('idx_log_entries_search', 'transcript', 'filename', 'talkgroup'),  # Full-text-ish search
        Index('idx_log_date_deleted', 'log_date', 'is_deleted'),  # For retention cleanup
        Index('idx_timestamp', 'timestamp'),  # Time-based queries
    )
    
    def __repr__(self):
        return f"<LogEntry(filename='{self.filename}', timestamp='{self.timestamp}')>"

