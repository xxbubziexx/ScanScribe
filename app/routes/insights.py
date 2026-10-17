import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import extract, func, or_
from sqlalchemy.orm import Session

from ..database import get_events_db, get_logs_db
from ..models.event import SpanStore
from ..models.hour_summary import HourSummary
from ..models.log_entry import LogEntry
from ..models.user import User
from ..schemas.insights import (
    DeleteHourSummaryResponse,
    GenerateHourSummaryResponse,
    InsightsStatsResponse,
    ListHourSummariesResponse,
    LiveCpmResponse,
    SearchTranscriptionsResponse,
    SummaryHoursResponse,
)
from ..services.insights_engine import (
    build_trend,
    compute_insights_stats,
    get_all_talkgroups,
    get_attached_events_for_logs,
    get_daily_activity,
    get_daily_summary,
    get_hourly_activity,
    get_last_full_minute_transcription_count,
    get_last_full_minute_window,
    get_monthly_summary,
    get_recent_activity,
    get_summary_trends,
    get_talkgroup_breakdown,
    get_transcription_count_by_created_window,
    get_weekly_activity,
    get_weekly_summary,
)
from ..services.summarization import generate_hour_summary
from .auth import get_current_active_user

router = APIRouter(prefix="/api/insights", tags=["insights"])
logger = logging.getLogger(__name__)

def parse_date_param(param_name: str, val: Optional[str]) -> Optional[date]:
    """Parse YYYY-MM-DD date parameter or raise HTTP 422 if invalid."""
    if not val:
        return None
    try:
        return datetime.strptime(val.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid date format for '{param_name}': '{val}'. Expected YYYY-MM-DD."
        )


class HourSummaryRequest(BaseModel):
    date: str = Field(..., min_length=10, max_length=10)  # YYYY-MM-DD
    hour: int = Field(..., ge=0, le=23)
    force: bool = False


@router.get("/live-cpm", response_model=LiveCpmResponse)
def get_live_cpm(
    window: int = Query(1, ge=1, le=60, description="Deprecated. Metric is fixed to previous full minute."),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db),
):
    """Calls/min card value: count of transcriptions in the previous full minute."""
    minute_start, minute_end = get_last_full_minute_window()
    prev_start = minute_start - timedelta(minutes=1)
    prev_end = minute_start
    prev_count = get_transcription_count_by_created_window(db, prev_start, prev_end)
    curr_count = get_last_full_minute_transcription_count(db)
    return {
        "calls_per_minute": curr_count,
        "window_minutes": 1,
        "minute_start": minute_start.isoformat(),
        "minute_end": minute_end.isoformat(),
        "trend": build_trend(curr_count, prev_count, "vs previous minute"),
    }


@router.get("/stats", response_model=InsightsStatsResponse)
def get_insights_stats(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    date_from: Optional[str] = Query(None, description="Start date in YYYY-MM-DD format"),
    date_to: Optional[str] = Query(None, description="End date in YYYY-MM-DD format"),
    view: str = Query("hourly", description="View type: hourly, daily, weekly"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db),
    events_db: Session = Depends(get_events_db),
):
    """Get insights statistics for a given date or date range and view type."""
    parsed_date = parse_date_param("date", date)
    parsed_from = parse_date_param("date_from", date_from)
    parsed_to = parse_date_param("date_to", date_to)

    target_start = parsed_from or parsed_date or datetime.now().date()
    target_end = parsed_to or parsed_date or target_start

    return compute_insights_stats(db, target_start, view, date_to=target_end, events_db=events_db)


@router.get("/search", response_model=SearchTranscriptionsResponse)
def search_transcriptions(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    date_from: Optional[str] = Query(None, description="Start date in YYYY-MM-DD format"),
    date_to: Optional[str] = Query(None, description="End date in YYYY-MM-DD format"),
    keyword: str = Query("", description="Keyword to search in transcripts"),
    talkgroup: Optional[List[str]] = Query(None, description="Filter by talkgroup (multiple allowed)"),
    hour: str = Query("", description="Filter by hour (0-23)"),
    sort: str = Query("newest", description="Sort: newest, oldest, largest, smallest, longest, shortest"),
    limit: int = Query(100, ge=1, le=10000, description="Max results"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db),
    events_db: Session = Depends(get_events_db),
):
    """Search and filter transcriptions across date or date range."""
    parsed_date = parse_date_param("date", date)
    parsed_from = parse_date_param("date_from", date_from)
    parsed_to = parse_date_param("date_to", date_to)

    target_start = parsed_from or parsed_date or datetime.now().date()
    target_end = parsed_to or parsed_date or target_start

    start = datetime.combine(min(target_start, target_end), datetime.min.time())
    end = datetime.combine(max(target_start, target_end), datetime.max.time())

    query = db.query(LogEntry).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False),
    )

    if keyword:
        query = query.filter(LogEntry.transcript.ilike(f"%{keyword}%"))

    if talkgroup and len(talkgroup) > 0:
        has_na = "N/A" in talkgroup
        others = [tg for tg in talkgroup if tg and tg != "N/A"]
        if has_na and not others:
            query = query.filter(
                or_(
                    LogEntry.talkgroup.is_(None),
                    LogEntry.talkgroup == "",
                    LogEntry.talkgroup == "N/A",
                )
            )
        elif others:
            if has_na:
                query = query.filter(
                    or_(
                        LogEntry.talkgroup.in_(others),
                        LogEntry.talkgroup.is_(None),
                        LogEntry.talkgroup == "",
                        LogEntry.talkgroup == "N/A",
                    )
                )
            else:
                query = query.filter(LogEntry.talkgroup.in_(others))

    if hour:
        try:
            hour_int = int(hour)
            if 0 <= hour_int <= 23:
                query = query.filter(extract("hour", LogEntry.timestamp) == hour_int)
        except ValueError:
            pass

    if sort == "oldest":
        query = query.order_by(LogEntry.timestamp.asc())
    elif sort == "largest":
        query = query.order_by(LogEntry.file_size.desc().nullslast())
    elif sort == "smallest":
        query = query.order_by(LogEntry.file_size.asc().nullsfirst())
    elif sort == "longest":
        query = query.order_by(LogEntry.duration.desc().nullslast())
    elif sort == "shortest":
        query = query.order_by(LogEntry.duration.asc().nullsfirst())
    else:
        query = query.order_by(LogEntry.timestamp.desc())

    total = query.count()
    results = query.limit(limit).all()
    log_ids = [r.id for r in results if r.id is not None]
    attached = get_attached_events_for_logs(events_db, log_ids)

    entities_map: Dict[int, Dict[str, List[str]]] = {}
    if log_ids:
        spans: List[SpanStore] = []
        for i in range(0, len(log_ids), 500):
            chunk = log_ids[i:i + 500]
            spans.extend(events_db.query(SpanStore).filter(SpanStore.log_entry_id.in_(chunk)).all())
        for span in spans:
            if not span.log_entry_id:
                continue

            def split_clean(val: Optional[str]) -> List[str]:
                if not val:
                    return []
                seen = set()
                out = []
                for item in val.split(","):
                    c = item.strip()
                    if c and c.lower() not in seen:
                        seen.add(c.lower())
                        out.append(c)
                return out

            units = split_clean(span.units)
            locs = split_clean(span.locations)
            addrs = split_clean(span.addresses)
            combined_locs = locs + [a for a in addrs if a.lower() not in {l.lower() for l in locs}]
            call_types = split_clean(span.evt_type)
            status_list = split_clean(span.status)

            entities_map[span.log_entry_id] = {
                "units": units,
                "locations": combined_locs,
                "call_types": call_types,
                "status": status_list,
            }

    return {
        "total": total,
        "results": [
            {
                "id": r.id,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "talkgroup": r.talkgroup,
                "transcript": r.transcript,
                "duration": r.duration,
                "file_size": r.file_size,
                "confidence": r.confidence,
                "audio_path": r.audio_path,
                "attached_events": attached.get(r.id, []),
                "entities": entities_map.get(
                    r.id,
                    {"units": [], "locations": [], "call_types": [], "status": []},
                ),
            }
            for r in results
        ],
    }


@router.get("/summaries/hours", response_model=SummaryHoursResponse)
def get_summary_hours(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db),
):
    """Return only hours (0-23) that have activity for the selected day."""
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            target_date = datetime.now().date()
    else:
        target_date = datetime.now().date()

    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())

    results = (
        db.query(
            extract("hour", LogEntry.timestamp).label("hour"),
            func.count(LogEntry.id).label("count"),
        )
        .filter(
            LogEntry.timestamp >= start,
            LogEntry.timestamp <= end,
            LogEntry.is_deleted.is_(False),
        )
        .group_by(extract("hour", LogEntry.timestamp))
        .order_by(extract("hour", LogEntry.timestamp).asc())
        .all()
    )

    return {
        "date": target_date.isoformat(),
        "hours": [{"hour": int(r.hour), "count": int(r.count)} for r in results],
    }


@router.get("/summaries", response_model=ListHourSummariesResponse)
def list_hour_summaries(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db),
):
    """List stored hour summaries for a given day."""
    if date:
        date_str = date
    else:
        date_str = datetime.now().date().isoformat()

    summaries = (
        db.query(HourSummary)
        .filter(HourSummary.summary_date == date_str)
        .order_by(HourSummary.summary_hour.asc())
        .all()
    )

    out_summaries = []
    for s in summaries:
        out_summaries.append(
            {
                "id": s.id,
                "date": s.summary_date,
                "hour": s.summary_hour,
                "text": s.summary_text,
                "format": "markdown",
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                "created_by": s.created_by,
            }
        )

    return {
        "date": date_str,
        "format": "markdown",
        "summaries": out_summaries,
    }


@router.post("/summaries/generate", response_model=GenerateHourSummaryResponse)
def generate_hour_summary_endpoint(
    payload: HourSummaryRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db),
):
    """Generate (or return existing) hour summary for date/hour (global)."""
    try:
        target_date = datetime.strptime(payload.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format (expected YYYY-MM-DD)")

    date_str = target_date.isoformat()

    existing = (
        db.query(HourSummary)
        .filter(
            HourSummary.summary_date == date_str,
            HourSummary.summary_hour == payload.hour,
        )
        .first()
    )

    if existing and not payload.force:
        return {
            "created": False,
            "format": "markdown",
            "summary": {
                "id": existing.id,
                "date": existing.summary_date,
                "hour": existing.summary_hour,
                "text": existing.summary_text,
                "format": "markdown",
            },
        }

    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())

    rows = (
        db.query(LogEntry)
        .filter(
            LogEntry.timestamp >= start,
            LogEntry.timestamp <= end,
            LogEntry.is_deleted.is_(False),
            extract("hour", LogEntry.timestamp) == payload.hour,
        )
        .order_by(LogEntry.timestamp.asc())
        .all()
    )

    entries = []
    for r in rows:
        if not r.timestamp:
            continue

        transcript = r.corrected_transcript if getattr(r, "corrected_transcript", None) else r.transcript
        if transcript and "[VAD_REJECTED]" in transcript:
            continue

        entries.append(
            {
                "filename_id": r.filename,
                "talkgroup": r.talkgroup or "N/A",
                "time": r.timestamp.strftime("%H:%M:%S"),
                "transcript": transcript,
            }
        )

    try:
        result = generate_hour_summary(entries, date_str=date_str, hour=payload.hour)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    text = result["summary"]

    if existing:
        existing.summary_text = text
        existing.created_by = existing.created_by or current_user.username
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return {
            "created": False,
            "format": "markdown",
            "summary": {
                "id": existing.id,
                "date": existing.summary_date,
                "hour": existing.summary_hour,
                "text": existing.summary_text,
                "format": "markdown",
            },
        }

    created = HourSummary(
        summary_date=date_str,
        summary_hour=payload.hour,
        summary_text=text,
        created_by=current_user.username,
    )
    db.add(created)
    db.commit()
    db.refresh(created)

    return {
        "created": True,
        "format": "markdown",
        "summary": {
            "id": created.id,
            "date": created.summary_date,
            "hour": created.summary_hour,
            "text": created.summary_text,
            "format": "markdown",
        },
    }


@router.delete("/summaries", response_model=DeleteHourSummaryResponse)
def delete_hour_summary(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    hour: int = Query(..., ge=0, le=23),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db),
):
    """Delete stored hour summary for date/hour."""
    summary = (
        db.query(HourSummary)
        .filter(
            HourSummary.summary_date == date,
            HourSummary.summary_hour == hour,
        )
        .first()
    )

    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")

    db.delete(summary)
    db.commit()
    return {"success": True}
