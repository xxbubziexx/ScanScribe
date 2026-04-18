"""Hour summary model for Insights summaries."""

from sqlalchemy import Column, Integer, String, Text, DateTime, Index, UniqueConstraint

from ..database import LogsBase as Base, utcnow


class HourSummary(Base):
    """Stored global hour summary for a given date/hour."""

    __tablename__ = "hour_summaries"

    id = Column(Integer, primary_key=True, index=True)

    # Partition key
    summary_date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    summary_hour = Column(Integer, nullable=False, index=True)  # 0-23

    # Content
    summary_text = Column(Text, nullable=False)
    # JSON array of cited filename_id strings (for playback)
    cited_filename_ids = Column(Text, nullable=True)

    # Optional metadata
    created_by = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=utcnow, nullable=True)

    __table_args__ = (
        UniqueConstraint("summary_date", "summary_hour", name="uq_hour_summaries_date_hour"),
        Index("idx_hour_summaries_date_hour", "summary_date", "summary_hour"),
    )

