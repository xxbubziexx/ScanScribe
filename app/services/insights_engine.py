"""Insights analytics and aggregation engine."""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import extract, func, or_
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.event import Event, EventTranscriptLink
from ..models.log_entry import LogEntry

logger = logging.getLogger(__name__)


def get_local_tz():
    """Resolve local timezone for log timestamp correlation."""
    try:
        pipe = getattr(get_settings().config, "events_pipeline", None)
        iana_tz = str(getattr(pipe, "log_naive_timezone", "") or "")
        if iana_tz:
            return ZoneInfo(iana_tz)
    except Exception:
        pass
    return datetime.now().astimezone().tzinfo or timezone.utc


def get_last_full_minute_window(now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """Return [start, end) for the previous complete minute in UTC wall-clock time."""
    now_utc = now or datetime.utcnow()
    end = now_utc.replace(second=0, microsecond=0)
    start = end - timedelta(minutes=1)
    return start, end


def get_last_full_hour_window(now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """Return [start, end) for the previous complete hour in UTC wall-clock time."""
    now_utc = now or datetime.utcnow()
    end = now_utc.replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=1)
    return start, end


def get_last_full_minute_transcription_count(db: Session) -> int:
    """Count transcriptions created in the previous full minute."""
    start, end = get_last_full_minute_window()
    return get_transcription_count_by_created_window(db, start, end)


def get_transcription_count_by_created_window(db: Session, start: datetime, end: datetime) -> int:
    """Count transcriptions by created_at for [start, end) in UTC naive datetimes."""
    return int(
        db.query(func.count(LogEntry.id)).filter(
            LogEntry.created_at >= start,
            LogEntry.created_at < end,
            LogEntry.is_deleted == False
        ).scalar() or 0
    )


def get_unique_talkgroups_by_created_window(db: Session, start: datetime, end: datetime) -> int:
    """Count distinct talkgroups by created_at for [start, end)."""
    return int(
        db.query(func.count(func.distinct(LogEntry.talkgroup))).filter(
            LogEntry.created_at >= start,
            LogEntry.created_at < end,
            LogEntry.is_deleted == False
        ).scalar() or 0
    )


def build_trend(current: int, previous: int, basis: str) -> Dict[str, object]:
    delta = int(current or 0) - int(previous or 0)
    direction = "up" if delta > 0 else ("down" if delta < 0 else "flat")
    return {
        "current": int(current or 0),
        "previous": int(previous or 0),
        "delta": delta,
        "direction": direction,
        "basis": basis,
    }


def get_summary_trends(db: Session, calls_last_minute: int) -> Dict[str, Dict[str, object]]:
    """Trend payload for stat cards with requested comparison windows."""
    hour_start, hour_end = get_last_full_hour_window()
    prev_hour_start = hour_start - timedelta(hours=1)
    prev_hour_end = hour_start
    total_hour = get_transcription_count_by_created_window(db, hour_start, hour_end)
    total_prev_hour = get_transcription_count_by_created_window(db, prev_hour_start, prev_hour_end)

    min_start, _ = get_last_full_minute_window()
    prev_min_start = min_start - timedelta(minutes=1)
    prev_min_end = min_start
    calls_prev_minute = get_transcription_count_by_created_window(db, prev_min_start, prev_min_end)

    day_end = datetime.utcnow()
    day_start = day_end - timedelta(days=1)
    prev_day_start = day_start - timedelta(days=1)
    prev_day_end = day_start
    tg_last_day = get_unique_talkgroups_by_created_window(db, day_start, day_end)
    tg_prev_day = get_unique_talkgroups_by_created_window(db, prev_day_start, prev_day_end)

    return {
        "total_transcriptions": build_trend(total_hour, total_prev_hour, "vs previous hour"),
        "calls_last_minute": build_trend(calls_last_minute, calls_prev_minute, "vs previous minute"),
        "unique_talkgroups": build_trend(tg_last_day, tg_prev_day, "vs previous 24h"),
    }


def get_event_hourly_counts(events_db: Optional[Session], target_date: date, tz) -> Dict[int, int]:
    """Return count of events created per hour for target_date in local wall time."""
    if not events_db:
        return {}
    try:
        start_local = datetime.combine(target_date, datetime.min.time(), tzinfo=tz)
        end_local = datetime.combine(target_date, datetime.max.time(), tzinfo=tz)
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)
        start_naive = start_utc.replace(tzinfo=None)
        end_naive = end_utc.replace(tzinfo=None)

        evs = events_db.query(Event.created_at).filter(
            or_(
                Event.created_at.between(start_utc, end_utc),
                Event.created_at.between(start_naive, end_naive),
            )
        ).all()
        hour_counts: Dict[int, int] = {}
        for (cat,) in evs:
            if cat:
                dt_val = cat if cat.tzinfo else cat.replace(tzinfo=timezone.utc)
                dt_loc = dt_val.astimezone(tz)
                if dt_loc.date() == target_date:
                    hour_counts[dt_loc.hour] = hour_counts.get(dt_loc.hour, 0) + 1
        return hour_counts
    except Exception as exc:
        logger.debug("Failed to query hourly events: %s", exc)
        return {}


def get_event_daily_counts(events_db: Optional[Session], start_of_week: date, tz) -> Dict[date, int]:
    """Return count of events created per day for the week starting start_of_week."""
    if not events_db:
        return {}
    try:
        start_week_local = datetime.combine(start_of_week, datetime.min.time(), tzinfo=tz)
        end_week_local = datetime.combine(start_of_week + timedelta(days=6), datetime.max.time(), tzinfo=tz)
        start_utc = start_week_local.astimezone(timezone.utc)
        end_utc = end_week_local.astimezone(timezone.utc)
        start_naive = start_utc.replace(tzinfo=None)
        end_naive = end_utc.replace(tzinfo=None)

        evs = events_db.query(Event.created_at).filter(
            or_(
                Event.created_at.between(start_utc, end_utc),
                Event.created_at.between(start_naive, end_naive),
            )
        ).all()
        day_counts: Dict[date, int] = {}
        for (cat,) in evs:
            if cat:
                dt_val = cat if cat.tzinfo else cat.replace(tzinfo=timezone.utc)
                d_val = dt_val.astimezone(tz).date()
                day_counts[d_val] = day_counts.get(d_val, 0) + 1
        return day_counts
    except Exception as exc:
        logger.debug("Failed to query daily events: %s", exc)
        return {}


def get_event_weekly_counts(events_db: Optional[Session], earliest_week_start: date, latest_week_end: date, tz) -> Dict[date, int]:
    """Return count of events created per week for the given 8-week span."""
    if not events_db:
        return {}
    try:
        start_utc = datetime.combine(earliest_week_start, datetime.min.time(), tzinfo=tz).astimezone(timezone.utc)
        end_utc = datetime.combine(latest_week_end, datetime.max.time(), tzinfo=tz).astimezone(timezone.utc)
        start_naive = start_utc.replace(tzinfo=None)
        end_naive = end_utc.replace(tzinfo=None)

        evs = events_db.query(Event.created_at).filter(
            or_(
                Event.created_at.between(start_utc, end_utc),
                Event.created_at.between(start_naive, end_naive),
            )
        ).all()
        week_counts: Dict[date, int] = {}
        for (cat,) in evs:
            if cat:
                dt_val = cat if cat.tzinfo else cat.replace(tzinfo=timezone.utc)
                d_val = dt_val.astimezone(tz).date()
                w_start = d_val - timedelta(days=d_val.weekday())
                week_counts[w_start] = week_counts.get(w_start, 0) + 1
        return week_counts
    except Exception as exc:
        logger.debug("Failed to query weekly events: %s", exc)
        return {}


def get_hourly_activity(db: Session, target_date: date, events_db: Optional[Session] = None) -> List[Dict[str, Any]]:
    """Get hourly activity for a specific day."""
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())
    tz = get_local_tz()

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

    hour_counts = {int(r.hour): r.count for r in results}
    events_hour_counts = get_event_hourly_counts(events_db, target_date, tz)

    activity = []
    for h in range(24):
        hour12 = 12 if h == 0 or h == 12 else (h % 12)
        ampm = "AM" if h < 12 else "PM"
        activity.append({
            "label": f"{hour12} {ampm}",
            "count": hour_counts.get(h, 0),
            "events_count": events_hour_counts.get(h, 0),
            "hour": h,
        })
    return activity


def get_daily_activity(db: Session, target_date: date, events_db: Optional[Session] = None) -> List[Dict[str, Any]]:
    """Get daily activity for the week containing target_date."""
    start_of_week = target_date - timedelta(days=target_date.weekday())
    tz = get_local_tz()
    events_day_counts = get_event_daily_counts(events_db, start_of_week, tz)

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
            "count": count,
            "events_count": events_day_counts.get(day, 0),
        })
    return activity


def get_weekly_activity(db: Session, target_date: date, events_db: Optional[Session] = None) -> List[Dict[str, Any]]:
    """Get weekly activity for the last 8 weeks."""
    tz = get_local_tz()
    earliest_week_start = target_date - timedelta(weeks=7, days=target_date.weekday())
    latest_week_end = target_date - timedelta(weeks=0, days=target_date.weekday()) + timedelta(days=6)
    events_week_counts = get_event_weekly_counts(events_db, earliest_week_start, latest_week_end, tz)

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
            "count": count,
            "events_count": events_week_counts.get(week_start, 0),
        })
    return activity


def get_daily_summary(db: Session, target_date: date) -> Dict[str, Any]:
    """Get summary stats for a specific day."""
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())

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
    minutes_in_period = 24 * 60
    calls_per_minute = round(total / minutes_in_period, 2) if minutes_in_period else 0

    return {
        "total": total,
        "unique_talkgroups": unique_tg,
        "avg_duration": float(avg_duration) if avg_duration else 0,
        "peak_hour": peak_hour,
        "calls_per_minute": calls_per_minute
    }


def get_weekly_summary(db: Session, target_date: date) -> Dict[str, Any]:
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

    minutes_in_period = 7 * 24 * 60
    calls_per_minute = round(total / minutes_in_period, 2) if minutes_in_period else 0

    return {
        "total": total,
        "unique_talkgroups": unique_tg,
        "avg_duration": float(avg_duration) if avg_duration else 0,
        "peak_hour": "Week View",
        "calls_per_minute": calls_per_minute
    }


def get_monthly_summary(db: Session, target_date: date) -> Dict[str, Any]:
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


def get_talkgroup_breakdown(db: Session, target_date: date, view: str) -> List[Dict[str, Any]]:
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


def get_all_talkgroups(db: Session, target_date: date, view: str) -> List[Dict[str, Any]]:
    """Pull all distinct talkgroups from DB for the period."""
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

    out = []
    for r in results:
        tg = r.talkgroup if (r.talkgroup and str(r.talkgroup).strip()) else "N/A"
        existing = next((x for x in out if x["talkgroup"] == tg), None)
        if existing:
            existing["count"] += r.count
        else:
            out.append({"talkgroup": tg, "count": r.count})
    return out


def get_attached_events_for_logs(events_db: Optional[Session], log_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    """Query attached events from scanscribe database for a list of log entry IDs."""
    if not events_db or not log_ids:
        return {}
    try:
        links = (
            events_db.query(
                EventTranscriptLink.log_entry_id,
                Event.id,
                Event.event_id,
                Event.status,
                Event.event_type,
            )
            .join(Event, Event.id == EventTranscriptLink.event_id)
            .filter(EventTranscriptLink.log_entry_id.in_(log_ids))
            .all()
        )
        grouped = defaultdict(list)
        for lid, eid, event_id_str, status, event_type in links:
            if lid is not None:
                grouped[int(lid)].append({
                    "id": eid,
                    "event_id": event_id_str,
                    "status": status,
                    "event_type": event_type,
                })
        return dict(grouped)
    except Exception as exc:
        logger.debug("Failed to query attached events for logs: %s", exc)
        return {}


def get_recent_activity(db: Session, target_date: date, limit: int = 20, events_db: Optional[Session] = None) -> List[Dict[str, Any]]:
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

    attached = get_attached_events_for_logs(events_db, [r.id for r in results if r.id is not None])
    return [{
        "id": r.id,
        "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        "talkgroup": r.talkgroup,
        "transcript": r.transcript,
        "duration": r.duration,
        "attached_events": attached.get(r.id, []),
    } for r in results]


def compute_insights_stats(db: Session, target_date: date, view: str, events_db: Optional[Session] = None) -> Dict[str, Any]:
    """Compute complete insights stats payload for the given target date and view."""
    if view == "hourly":
        summary = get_daily_summary(db, target_date)
        activity = get_hourly_activity(db, target_date, events_db=events_db)
    elif view == "daily":
        summary = get_weekly_summary(db, target_date)
        activity = get_daily_activity(db, target_date, events_db=events_db)
    else:  # weekly
        summary = get_monthly_summary(db, target_date)
        activity = get_weekly_activity(db, target_date, events_db=events_db)

    calls_last_minute = get_last_full_minute_transcription_count(db)
    summary["calls_last_minute"] = calls_last_minute
    summary["calls_per_minute_window"] = 1
    summary["trends"] = get_summary_trends(db, calls_last_minute)

    talkgroups = get_talkgroup_breakdown(db, target_date, view)
    recent = get_recent_activity(db, target_date, limit=50, events_db=events_db)
    all_talkgroups = get_all_talkgroups(db, target_date, view)

    return {
        "summary": summary,
        "activity": activity,
        "talkgroups": talkgroups,
        "talkgroups_all": all_talkgroups,
        "recent": recent
    }
