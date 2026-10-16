"""Chat models for Scanner Intelligence natural language queries."""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from ..database import Base, utcnow


class ChatThread(Base):
    """Conversation thread for scanner intelligence queries."""

    __tablename__ = "chat_threads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False, default="New Query")
    time_scope_preset = Column(String(50), nullable=False, default="today")
    start_time = Column(DateTime(timezone=True), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    talkgroups = Column(Text, nullable=True)  # JSON-encoded array of talkgroups
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, index=True)

    user = relationship("User")
    messages = relationship(
        "ChatMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    def __repr__(self):
        return f"<ChatThread(id={self.id}, user_id={self.user_id}, title='{self.title}')>"


class ChatMessage(Base):
    """Individual message in a scanner intelligence chat thread."""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(Integer, ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    cited_log_ids = Column(Text, nullable=True)  # JSON-encoded list of LogEntry IDs
    thought = Column(Text, nullable=True)  # Model reasoning trace (assistant messages only)
    tool_calls = Column(Text, nullable=True)  # JSON-encoded list of agent tool execution records
    created_at = Column(DateTime(timezone=True), default=utcnow, index=True)

    thread = relationship("ChatThread", back_populates="messages")

    def __repr__(self):
        return f"<ChatMessage(id={self.id}, thread_id={self.thread_id}, role='{self.role}')>"
