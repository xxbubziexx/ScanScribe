"""Pydantic v2 schemas for Scanner Intelligence chat."""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ChatTimeScope(BaseModel):
    """Time scope definition for a query."""
    preset: str = Field(default="today", description="'1h', '4h', '12h', 'today', 'yesterday', or 'custom'")
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class ChatThreadCreate(BaseModel):
    """Schema for creating a new chat thread."""
    title: Optional[str] = "New Query"
    time_scope_preset: str = "today"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    talkgroups: Optional[List[str]] = None


class ChatThreadUpdate(BaseModel):
    """Schema for updating thread properties."""
    title: Optional[str] = None
    time_scope_preset: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    talkgroups: Optional[List[str]] = None


class ChatMessageOut(BaseModel):
    """Output schema for a chat message."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    thread_id: int
    role: str
    content: str
    cited_log_ids: Optional[List[int]] = None
    created_at: datetime


class ChatThreadOut(BaseModel):
    """Summary output schema for thread lists."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    time_scope_preset: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    talkgroups: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime
    message_count: Optional[int] = 0


class ChatThreadDetailOut(ChatThreadOut):
    """Detail output schema for a thread including its messages."""
    messages: List[ChatMessageOut] = []


class ChatPromptInput(BaseModel):
    """Incoming user query to execute against transcript logs."""
    prompt: str = Field(..., min_length=1, max_length=2000)
    time_scope: Optional[ChatTimeScope] = None
    talkgroups: Optional[List[str]] = None


class TransmissionLookupOut(BaseModel):
    """Transmission details for audio playback and grounding verification."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    timestamp: datetime
    log_date: Optional[str] = None
    duration: float = 0.0
    audio_path: Optional[str] = None
    transcript: str
    talkgroup: Optional[str] = None
    audio_url: str
