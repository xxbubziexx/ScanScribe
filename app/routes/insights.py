"""Insights API routes."""
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, or_
from typing import Optional, List
from datetime import date, datetime, timedelta, time

from ..database import get_logs_db
from ..models.user import User
from ..models.log_entry import LogEntry
from ..models.hour_summary import HourSummary
from .auth import get_current_active_user
from ..services.summarization import generate_hour_summary

router = APIRouter(prefix="/api/insights", tags=["insights"])


class HourSummaryRequest(BaseModel):
    date: str = Field(..., min_length=10, max_length=10)  # YYYY-MM-DD
    hour: int = Field(..., ge=0, le=23)
    force: bool = False


@router.get("/live-cpm")
async def get_live_cpm(
    window: int = Query(5, ge=1, le=60, description="Rolling window in minutes"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db)
):
    """Live calls per minute (transcripts in last N minutes / N). For real-time dashboard polling."""
    return {
        "calls_per_minute": get_live_calls_per_minute(db, window_minutes=window),
        "window_minutes": window,
    }


@router.get("/stats")
async def get_insights_stats(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    view: str = Query("hourly", description="View type: hourly, daily, weekly"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db)
):
    """Get insights statistics for a given date and view type."""
    
    # Parse date or use today
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            target_date = datetime.now().date()
    else:
        target_date = datetime.now().date()
    
    # Get data based on view type
    if view == "hourly":
        activity = get_hourly_activity(db, target_date)
        summary = get_daily_summary(db, target_date)
    elif view == "daily":
        activity = get_daily_activity(db, target_date)
        summary = get_weekly_summary(db, target_date)
    else:  # weekly
        activity = get_weekly_activity(db, target_date)
        summary = get_monthly_summary(db, target_date)
    
    # Live calls per minute (rolling window, independent of selected date)
    summary["calls_per_minute"] = get_live_calls_per_minute(db, window_minutes=1)
    summary["calls_per_minute_window"] = 1
    
    # Get talkgroup breakdown
    talkgroups = get_talkgroup_breakdown(db, target_date, view)
    
    # Get recent activity
    recent = get_recent_activity(db, target_date, limit=50)
    
    # Get ALL talkgroups for filter dropdown (no limit)
    all_talkgroups = get_all_talkgroups(db, target_date, view)
    
    return {
        "summary": summary,
        "activity": activity,
        "talkgroups": talkgroups,
        "talkgroups_all": all_talkgroups,
        "recent": recent
    }


def get_hourly_activity(db: Session, target_date: date):
    """Get hourly activity for a specific day."""
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())
    
    # Query hourly counts
    results = db.query(
        extract('hour', LogEntry.timestamp).label('hour'),
        func.count(LogEntry.id).label('count')
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted == False
    ).group_by(
        extract('hour', LogEntry.timestamp)
    ).all()
    
    # Build 24-hour array with 12-hour labels
    hour_counts = {int(r.hour): r.count for r in results}
    activity = []
    for h in range(24):
        # Convert to 12-hour format
        hour12 = 12 if h == 0 or h == 12 else (h % 12)
        ampm = "AM" if h < 12 else "PM"
        label = f"{hour12} {ampm}"
        activity.append({"label": label, "count": hour_counts.get(h, 0), "hour": h})
    
    return activity


def get_daily_activity(db: Session, target_date: date):
    """Get daily activity for the week containing target_date."""
    # Find start of week (Monday)
    start_of_week = target_date - timedelta(days=target_date.weekday())
    
    activity = []
    for i in range(7):
        day = start_of_week + timedelta(days=i)
        start = datetime.combine(day, datetime.min.time())
        end = datetime.combine(day, datetime.max.time())
        
        count = db.query(func.count(LogEntry.id)).filter(
            LogEntry.timestamp >= start,
            LogEntry.timestamp <= end,
            LogEntry.is_deleted == False
        ).scalar() or 0
        
        activity.append({
            "label": day.strftime("%a"),
            "count": count
        })
    
    return activity


def get_weekly_activity(db: Session, target_date: date):
    """Get weekly activity for the last 8 weeks."""
    activity = []
    
    for i in range(7, -1, -1):
        week_start = target_date - timedelta(weeks=i, days=target_date.weekday())
        week_end = week_start + timedelta(days=6)
        
        start = datetime.combine(week_start, datetime.min.time())
        end = datetime.combine(week_end, datetime.max.time())
        
        count = db.query(func.count(LogEntry.id)).filter(
            LogEntry.timestamp >= start,
            LogEntry.timestamp <= end,
            LogEntry.is_deleted == False
        ).scalar() or 0
        
        activity.append({
            "label": week_start.strftime("%m/%d"),
            "count": count
        })
    
    return activity


def get_live_calls_per_minute(db: Session, window_minutes: int = 5) -> float:
    """Transcripts in last N minutes / N = live calls per minute."""
    if window_minutes <= 0:
        return 0.0
    cutoff = datetime.now() - timedelta(minutes=window_minutes)
    count = db.query(func.count(LogEntry.id)).filter(
        LogEntry.timestamp >= cutoff,
        LogEntry.is_deleted == False
    ).scalar() or 0
    return round(count / window_minutes, 2)


def get_daily_summary(db: Session, target_date: date):
    """Get summary stats for a specific day."""
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())
    
    # Total count
    total = db.query(func.count(LogEntry.id)).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted == False
    ).scalar() or 0
    
    # Unique talkgroups
    unique_tg = db.query(func.count(func.distinct(LogEntry.talkgroup))).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted == False
    ).scalar() or 0
    
    # Average duration
    avg_duration = db.query(func.avg(LogEntry.duration)).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted == False
    ).scalar() or 0
    
    # Peak hour
    peak_result = db.query(
        extract('hour', LogEntry.timestamp).label('hour'),
        func.count(LogEntry.id).label('count')
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted == False
    ).group_by(
        extract('hour', LogEntry.timestamp)
    ).order_by(
        func.count(LogEntry.id).desc()
    ).first()
    
    peak_hour = f"{int(peak_result.hour):02d}:00" if peak_result else "--"
    minutes_in_period = 24 * 60  # 1 day
    calls_per_minute = round(total / minutes_in_period, 2) if minutes_in_period else 0

    return {
        "total": total,
        "unique_talkgroups": unique_tg,
        "avg_duration": float(avg_duration) if avg_duration else 0,
        "peak_hour": peak_hour,
        "calls_per_minute": calls_per_minute
    }


def get_weekly_summary(db: Session, target_date: date):
    """Get summary stats for the week."""
    start_of_week = target_date - timedelta(days=target_date.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    start = datetime.combine(start_of_week, datetime.min.time())
    end = datetime.combine(end_of_week, datetime.max.time())
    
    total = db.query(func.count(LogEntry.id)).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted == False
    ).scalar() or 0
    
    unique_tg = db.query(func.count(func.distinct(LogEntry.talkgroup))).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted == False
    ).scalar() or 0
    
    avg_duration = db.query(func.avg(LogEntry.duration)).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted == False
    ).scalar() or 0
    
    minutes_in_period = 7 * 24 * 60  # 1 week
    calls_per_minute = round(total / minutes_in_period, 2) if minutes_in_period else 0

    return {
        "total": total,
        "unique_talkgroups": unique_tg,
        "avg_duration": float(avg_duration) if avg_duration else 0,
        "peak_hour": "Week View",
        "calls_per_minute": calls_per_minute
    }


def get_monthly_summary(db: Session, target_date: date):
    """Get summary stats for the month."""
    start_of_month = target_date.replace(day=1)
    if target_date.month == 12:
        end_of_month = target_date.replace(year=target_date.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end_of_month = target_date.replace(month=target_date.month + 1, day=1) - timedelta(days=1)
    
    start = datetime.combine(start_of_month, datetime.min.time())
    end = datetime.combine(end_of_month, datetime.max.time())
    
    total = db.query(func.count(LogEntry.id)).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted == False
    ).scalar() or 0
    
    unique_tg = db.query(func.count(func.distinct(LogEntry.talkgroup))).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted == False
    ).scalar() or 0
    
    avg_duration = db.query(func.avg(LogEntry.duration)).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted == False
    ).scalar() or 0
    
    days_in_month = (end_of_month - start_of_month).days + 1
    minutes_in_period = days_in_month * 24 * 60
    calls_per_minute = round(total / minutes_in_period, 2) if minutes_in_period else 0

    return {
        "total": total,
        "unique_talkgroups": unique_tg,
        "avg_duration": float(avg_duration) if avg_duration else 0,
        "peak_hour": "Month View",
        "calls_per_minute": calls_per_minute
    }


def get_talkgroup_breakdown(db: Session, target_date: date, view: str):
    """Get talkgroup activity breakdown."""
    if view == "hourly":
        start = datetime.combine(target_date, datetime.min.time())
        end = datetime.combine(target_date, datetime.max.time())
    elif view == "daily":
        start_of_week = target_date - timedelta(days=target_date.weekday())
        start = datetime.combine(start_of_week, datetime.min.time())
        end = datetime.combine(start_of_week + timedelta(days=6), datetime.max.time())
    else:
        start = datetime.combine(target_date - timedelta(weeks=4), datetime.min.time())
        end = datetime.combine(target_date, datetime.max.time())
    
    results = db.query(
        LogEntry.talkgroup,
        func.count(LogEntry.id).label('count')
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted == False,
        LogEntry.talkgroup.isnot(None),
        LogEntry.talkgroup != 'N/A'
    ).group_by(
        LogEntry.talkgroup
    ).order_by(
        func.count(LogEntry.id).desc()
    ).limit(10).all()
    
    return [{"talkgroup": r.talkgroup, "count": r.count} for r in results]


def get_all_talkgroups(db: Session, target_date: date, view: str):
    """Pull all distinct talkgroups from DB for the period (includes null/empty as N/A)."""
    if view == "hourly":
        start = datetime.combine(target_date, datetime.min.time())
        end = datetime.combine(target_date, datetime.max.time())
    elif view == "daily":
        start_of_week = target_date - timedelta(days=target_date.weekday())
        start = datetime.combine(start_of_week, datetime.min.time())
        end = datetime.combine(start_of_week + timedelta(days=6), datetime.max.time())
    else:
        start = datetime.combine(target_date - timedelta(weeks=4), datetime.min.time())
        end = datetime.combine(target_date, datetime.max.time())
    
    results = db.query(
        LogEntry.talkgroup,
        func.count(LogEntry.id).label('count')
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted == False
    ).group_by(
        LogEntry.talkgroup
    ).order_by(
        func.count(LogEntry.id).desc()
    ).all()
    
    # Normalize for display: null/empty -> "N/A" so filter can target unknowns
    out = []
    for r in results:
        tg = r.talkgroup if (r.talkgroup and str(r.talkgroup).strip()) else "N/A"
        # Merge counts for rows that normalized to same label
        existing = next((x for x in out if x["talkgroup"] == tg), None)
        if existing:
            existing["count"] += r.count
        else:
            out.append({"talkgroup": tg, "count": r.count})
    return out


def get_recent_activity(db: Session, target_date: date, limit: int = 20):
    """Get recent transcriptions for the day."""
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())
    
    results = db.query(LogEntry).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted == False
    ).order_by(
        LogEntry.timestamp.desc()
    ).limit(limit).all()
    
    return [{
        "id": r.id,
        "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        "talkgroup": r.talkgroup,
        "transcript": r.transcript,
        "duration": r.duration
    } for r in results]


@router.get("/search")
async def search_transcriptions(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    keyword: str = Query("", description="Keyword to search in transcripts"),
    talkgroup: Optional[List[str]] = Query(None, description="Filter by talkgroup (multiple allowed)"),
    hour: str = Query("", description="Filter by hour (0-23)"),
    sort: str = Query("newest", description="Sort: newest, oldest, largest, smallest, longest, shortest"),
    limit: int = Query(100, ge=1, le=10000, description="Max results (use higher value when filtering by hour to get all)"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db)
):
    """Search and filter transcriptions."""
    
    # Parse date
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            target_date = datetime.now().date()
    else:
        target_date = datetime.now().date()
    
    # Base query
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())
    
    query = db.query(LogEntry).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted == False
    )
    
    # Apply keyword filter
    if keyword:
        query = query.filter(LogEntry.transcript.ilike(f"%{keyword}%"))
    
    # Apply talkgroup filter (multiple allowed)
    if talkgroup and len(talkgroup) > 0:
        # Normalize: single "N/A" or list containing "N/A" + others
        has_na = "N/A" in talkgroup
        others = [tg for tg in talkgroup if tg and tg != "N/A"]
        if has_na and not others:
            query = query.filter(
                or_(
                    LogEntry.talkgroup.is_(None),
                    LogEntry.talkgroup == "",
                    LogEntry.talkgroup == "N/A"
                )
            )
        elif others:
            if has_na:
                query = query.filter(
                    or_(
                        LogEntry.talkgroup.in_(others),
                        LogEntry.talkgroup.is_(None),
                        LogEntry.talkgroup == "",
                        LogEntry.talkgroup == "N/A"
                    )
                )
            else:
                query = query.filter(LogEntry.talkgroup.in_(others))
    
    # Apply hour filter
    if hour:
        try:
            hour_int = int(hour)
            if 0 <= hour_int <= 23:
                query = query.filter(extract('hour', LogEntry.timestamp) == hour_int)
        except ValueError:
            pass
    
    # Apply sorting
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
    else:  # newest (default)
        query = query.order_by(LogEntry.timestamp.desc())
    
    # Get total count before limit
    total = query.count()
    
    # Apply limit
    results = query.limit(limit).all()
    
    return {
        "total": total,
        "results": [{
            "id": r.id,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "talkgroup": r.talkgroup,
            "transcript": r.transcript,
            "duration": r.duration,
            "file_size": r.file_size,
            "confidence": r.confidence,
            "audio_path": r.audio_path
        } for r in results]
    }


@router.get("/summaries/hours")
async def get_summary_hours(
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

    results = db.query(
        extract("hour", LogEntry.timestamp).label("hour"),
        func.count(LogEntry.id).label("count"),
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted == False,
    ).group_by(
        extract("hour", LogEntry.timestamp)
    ).order_by(
        extract("hour", LogEntry.timestamp).asc()
    ).all()

    return {
        "date": target_date.isoformat(),
        "hours": [{"hour": int(r.hour), "count": int(r.count)} for r in results],
    }


@router.get("/summaries")
async def list_hour_summaries(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db),
):
    """List stored hour summaries for a given day."""
    if date:
        date_str = date
    else:
        date_str = datetime.now().date().isoformat()

    summaries = db.query(HourSummary).filter(
        HourSummary.summary_date == date_str
    ).order_by(
        HourSummary.summary_hour.asc()
    ).all()

    out_summaries = []
    for s in summaries:
        out_summaries.append({
            "id": s.id,
            "date": s.summary_date,
            "hour": s.summary_hour,
            "text": s.summary_text,
            "format": "markdown",
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            "created_by": s.created_by,
        })

    return {
        "date": date_str,
        "format": "markdown",
        "summaries": out_summaries,
    }


@router.post("/summaries/generate")
async def generate_hour_summary_endpoint(
    payload: HourSummaryRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db),
):
    """Generate (or return existing) hour summary for date/hour (global)."""
    # Validate date format
    try:
        target_date = datetime.strptime(payload.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format (expected YYYY-MM-DD)")

    date_str = target_date.isoformat()

    existing = db.query(HourSummary).filter(
        HourSummary.summary_date == date_str,
        HourSummary.summary_hour == payload.hour,
    ).first()

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

    # Fetch all entries for that hour
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())

    rows = db.query(LogEntry).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted == False,
        extract("hour", LogEntry.timestamp) == payload.hour,
    ).order_by(LogEntry.timestamp.asc()).all()

    entries = []
    for r in rows:
        if not r.timestamp:
            continue
        entries.append(
            {
                "filename_id": r.filename,
                "talkgroup": r.talkgroup or "N/A",
                "time": r.timestamp.strftime("%H:%M:%S"),
                "transcript": r.transcript,
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


@router.delete("/summaries")
async def delete_hour_summary(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    hour: int = Query(..., ge=0, le=23),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db),
):
    """Delete stored hour summary for date/hour."""
    summary = db.query(HourSummary).filter(
        HourSummary.summary_date == date,
        HourSummary.summary_hour == hour,
    ).first()

    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")

    db.delete(summary)
    db.commit()
    return {"success": True}
