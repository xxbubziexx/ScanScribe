"""Insights analytics and aggregation engine."""
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
import logging
import math
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import extract, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.event import EntityObservation, Event, EventTranscriptLink, SpanStore
from ..models.log_entry import LogEntry

logger = logging.getLogger(__name__)


def get_local_tz():
    """Resolve local timezone for log timestamp correlation."""
    try:
        pipe = getattr(get_settings().config, "events_pipeline", None)
        iana_tz = str(getattr(pipe, "log_naive_timezone", "") or "")
        if iana_tz:
            return ZoneInfo(iana_tz)
    except (ValueError, AttributeError, Exception) as exc:
        logger.debug("Failed resolving local timezone '%s': %s", locals().get("iana_tz"), exc)
    return datetime.now().astimezone().tzinfo or timezone.utc


def local_date_range_to_utc(start_date: date, end_date: date) -> Tuple[datetime, datetime]:
    """Convert local date range [start_date, end_date] into UTC datetime boundaries [start_utc, end_utc]."""
    tz = get_local_tz()
    start_local = datetime.combine(start_date, time.min, tzinfo=tz)
    end_local = datetime.combine(end_date, time.max, tzinfo=tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


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
            LogEntry.is_deleted.is_(False)
        ).scalar() or 0
    )


def get_unique_talkgroups_by_created_window(db: Session, start: datetime, end: datetime) -> int:
    """Count distinct talkgroups by created_at for [start, end)."""
    return int(
        db.query(func.count(func.distinct(LogEntry.talkgroup))).filter(
            LogEntry.created_at >= start,
            LogEntry.created_at < end,
            LogEntry.is_deleted.is_(False)
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
    except SQLAlchemyError as exc:
        logger.warning("Failed to query hourly events: %s", exc, exc_info=True)
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
    except SQLAlchemyError as exc:
        logger.warning("Failed to query daily events: %s", exc, exc_info=True)
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
    except SQLAlchemyError as exc:
        logger.warning("Failed to query weekly events: %s", exc, exc_info=True)
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
        LogEntry.is_deleted.is_(False)
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
            LogEntry.is_deleted.is_(False)
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
            LogEntry.is_deleted.is_(False)
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
        LogEntry.is_deleted.is_(False)
    ).scalar() or 0

    unique_tg = db.query(func.count(func.distinct(LogEntry.talkgroup))).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False)
    ).scalar() or 0

    avg_duration = db.query(func.avg(LogEntry.duration)).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False)
    ).scalar() or 0

    peak_result = db.query(
        extract('hour', LogEntry.timestamp).label('hour'),
        func.count(LogEntry.id).label('count')
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False)
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
        LogEntry.is_deleted.is_(False)
    ).scalar() or 0

    unique_tg = db.query(func.count(func.distinct(LogEntry.talkgroup))).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False)
    ).scalar() or 0

    avg_duration = db.query(func.avg(LogEntry.duration)).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False)
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
        LogEntry.is_deleted.is_(False)
    ).scalar() or 0

    unique_tg = db.query(func.count(func.distinct(LogEntry.talkgroup))).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False)
    ).scalar() or 0

    avg_duration = db.query(func.avg(LogEntry.duration)).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False)
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
        func.count(LogEntry.id).label('count'),
        func.sum(LogEntry.duration).label('duration'),
        func.avg(LogEntry.duration).label('avg_duration')
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False),
        LogEntry.talkgroup.isnot(None),
        LogEntry.talkgroup != 'N/A'
    ).group_by(
        LogEntry.talkgroup
    ).order_by(
        func.count(LogEntry.id).desc()
    ).limit(10).all()

    total_airtime = sum(float(r.duration or 0) for r in results)
    out = []
    for r in results:
        dur = round(float(r.duration or 0), 1)
        pct = round((dur / max(total_airtime, 0.001)) * 100, 1)
        out.append({
            "talkgroup": r.talkgroup,
            "count": int(r.count),
            "duration": dur,
            "avg_duration": round(float(r.avg_duration or 0), 1),
            "percentage": pct,
        })
    return out


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
        LogEntry.is_deleted.is_(False)
    ).group_by(
        LogEntry.talkgroup
    ).order_by(
        func.count(LogEntry.id).desc()
    ).all()

    merged: Dict[str, int] = defaultdict(int)
    for r in results:
        tg = r.talkgroup if (r.talkgroup and str(r.talkgroup).strip()) else "N/A"
        merged[tg] += int(r.count or 0)
    return [{"talkgroup": tg, "count": cnt} for tg, cnt in merged.items()]


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
        logger.warning("Failed to query attached events for logs: %s", exc, exc_info=True)
        return {}


def get_recent_activity(db: Session, target_date: date, limit: int = 20, events_db: Optional[Session] = None) -> List[Dict[str, Any]]:
    """Get recent transcriptions for the day."""
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())

    results = db.query(LogEntry).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False)
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


def get_event_daily_range_counts(events_db: Optional[Session], start_date: date, end_date: date, tz) -> Dict[date, int]:
    """Return count of events created per day for range [start_date, end_date]."""
    if not events_db:
        return {}
    try:
        start_local = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_local = datetime.combine(end_date, datetime.max.time(), tzinfo=tz)
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
        day_counts: Dict[date, int] = {}
        for (cat,) in evs:
            if cat:
                dt_val = cat if cat.tzinfo else cat.replace(tzinfo=timezone.utc)
                d_val = dt_val.astimezone(tz).date()
                day_counts[d_val] = day_counts.get(d_val, 0) + 1
        return day_counts
    except SQLAlchemyError as exc:
        logger.warning("Failed to query range daily events: %s", exc, exc_info=True)
        return {}


def get_range_summary(db: Session, start_date: date, end_date: date) -> Dict[str, Any]:
    """Get summary statistics across an arbitrary date range."""
    start = datetime.combine(start_date, datetime.min.time())
    end = datetime.combine(end_date, datetime.max.time())

    total = db.query(func.count(LogEntry.id)).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False)
    ).scalar() or 0

    unique_tg = db.query(func.count(func.distinct(LogEntry.talkgroup))).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False)
    ).scalar() or 0

    avg_duration = db.query(func.avg(LogEntry.duration)).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False)
    ).scalar() or 0

    # Determine peak day in range
    peak_row = db.query(
        func.date(LogEntry.timestamp).label('day'),
        func.count(LogEntry.id).label('cnt')
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False)
    ).group_by(
        func.date(LogEntry.timestamp)
    ).order_by(
        func.count(LogEntry.id).desc()
    ).first()

    days = max(1, (end_date - start_date).days + 1)
    if peak_row and peak_row.day:
        try:
            peak_label = datetime.strptime(str(peak_row.day), "%Y-%m-%d").strftime("%b %d")
        except Exception:
            peak_label = str(peak_row.day)
    else:
        peak_label = "--"

    minutes_in_period = max(1, days * 24 * 60)
    calls_per_minute = round(total / minutes_in_period, 2) if minutes_in_period else 0

    return {
        "total": total,
        "unique_talkgroups": unique_tg,
        "avg_duration": float(avg_duration) if avg_duration else 0,
        "peak_hour": peak_label,
        "calls_per_minute": calls_per_minute,
        "range_days": days,
    }


def get_range_activity(
    db: Session,
    start_date: date,
    end_date: date,
    events_db: Optional[Session] = None,
    view: str = "daily"
) -> List[Dict[str, Any]]:
    """Generate activity points adapting to the selected date range."""
    num_days = max(1, (end_date - start_date).days + 1)
    tz = get_local_tz()
    start = datetime.combine(start_date, datetime.min.time())
    end = datetime.combine(end_date, datetime.max.time())

    if view == "weekly" or (num_days > 35 and view != "daily"):
        # Weekly buckets
        week_start = start_date - timedelta(days=start_date.weekday())
        activity = []
        cur_w = week_start
        while cur_w <= end_date:
            cur_end = cur_w + timedelta(days=6)
            w_start_dt = datetime.combine(cur_w, datetime.min.time())
            w_end_dt = datetime.combine(cur_end, datetime.max.time())
            count = db.query(func.count(LogEntry.id)).filter(
                LogEntry.timestamp >= w_start_dt,
                LogEntry.timestamp <= w_end_dt,
                LogEntry.is_deleted.is_(False)
            ).scalar() or 0

            ev_count = 0
            if events_db:
                ev_counts = get_event_weekly_counts(events_db, cur_w, cur_end, tz)
                ev_count = ev_counts.get(cur_w, 0)

            activity.append({
                "label": cur_w.strftime("%m/%d"),
                "count": count,
                "events_count": ev_count,
            })
            cur_w += timedelta(days=7)
        return activity

    # Daily buckets across range
    results = db.query(
        func.date(LogEntry.timestamp).label('day_str'),
        func.count(LogEntry.id).label('count')
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False)
    ).group_by(
        func.date(LogEntry.timestamp)
    ).all()
    day_counts = {str(r.day_str): r.count for r in results}
    events_day_counts = get_event_daily_range_counts(events_db, start_date, end_date, tz)

    activity = []
    for i in range(num_days):
        d = start_date + timedelta(days=i)
        d_str = d.isoformat()
        if num_days <= 7:
            label = d.strftime("%a %m/%d")
        else:
            label = d.strftime("%m/%d")
        activity.append({
            "label": label,
            "count": day_counts.get(d_str, 0),
            "events_count": events_day_counts.get(d, 0),
            "date": d_str,
        })
    return activity


def get_range_talkgroup_breakdown(db: Session, start_date: date, end_date: date, limit: int = 10) -> List[Dict[str, Any]]:
    """Get talkgroup activity breakdown across date range."""
    start = datetime.combine(start_date, datetime.min.time())
    end = datetime.combine(end_date, datetime.max.time())
    results = db.query(
        LogEntry.talkgroup,
        func.count(LogEntry.id).label('count'),
        func.sum(LogEntry.duration).label('duration'),
        func.avg(LogEntry.duration).label('avg_duration')
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False),
        LogEntry.talkgroup.isnot(None),
        LogEntry.talkgroup != 'N/A'
    ).group_by(
        LogEntry.talkgroup
    ).order_by(
        func.count(LogEntry.id).desc()
    ).limit(limit).all()

    total_airtime = sum(float(r.duration or 0) for r in results)
    out = []
    for r in results:
        dur = round(float(r.duration or 0), 1)
        pct = round((dur / max(total_airtime, 0.001)) * 100, 1)
        out.append({
            "talkgroup": r.talkgroup,
            "count": int(r.count),
            "duration": dur,
            "avg_duration": round(float(r.avg_duration or 0), 1),
            "percentage": pct,
        })
    return out


def get_all_range_talkgroups(db: Session, start_date: date, end_date: date) -> List[Dict[str, Any]]:
    """Pull all distinct talkgroups across date range."""
    start = datetime.combine(start_date, datetime.min.time())
    end = datetime.combine(end_date, datetime.max.time())
    results = db.query(
        LogEntry.talkgroup,
        func.count(LogEntry.id).label('count')
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False)
    ).group_by(
        LogEntry.talkgroup
    ).order_by(
        func.count(LogEntry.id).desc()
    ).all()
    merged: Dict[str, int] = defaultdict(int)
    for r in results:
        tg = r.talkgroup if (r.talkgroup and str(r.talkgroup).strip()) else "N/A"
        merged[tg] += int(r.count or 0)
    return [{"talkgroup": tg, "count": cnt} for tg, cnt in merged.items()]


def get_range_recent_activity(db: Session, start_date: date, end_date: date, limit: int = 50, events_db: Optional[Session] = None) -> List[Dict[str, Any]]:
    """Get recent transcriptions within date range."""
    start = datetime.combine(start_date, datetime.min.time())
    end = datetime.combine(end_date, datetime.max.time())
    results = db.query(LogEntry).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False)
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


def get_diurnal_heatmap(
    db: Session,
    start_date: date,
    end_date: date,
) -> Dict[str, Any]:
    """
    Generate a 7x24 matrix (day of week x hour of day) of call volume.
    If start_date == end_date, window expands to trailing 7 days so a full weekly
    diurnal pattern is rendered.
    """
    if start_date == end_date:
        query_start = start_date - timedelta(days=6)
        query_end = end_date
    else:
        query_start = min(start_date, end_date)
        query_end = max(start_date, end_date)

    start_dt = datetime.combine(query_start, datetime.min.time())
    end_dt = datetime.combine(query_end, datetime.max.time())

    rows = db.query(
        extract('dow', LogEntry.timestamp).label('dow'),
        extract('hour', LogEntry.timestamp).label('hour'),
        func.count(LogEntry.id).label('count'),
        func.sum(LogEntry.duration).label('duration'),
    ).filter(
        LogEntry.timestamp >= start_dt,
        LogEntry.timestamp <= end_dt,
        LogEntry.is_deleted.is_(False)
    ).group_by(
        extract('dow', LogEntry.timestamp),
        extract('hour', LogEntry.timestamp),
    ).all()

    # dow: 0=Sun, 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat
    DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    data_map: Dict[Tuple[int, int], Tuple[int, float]] = {}
    max_count = 0
    total_calls = 0
    total_airtime = 0.0

    for r in rows:
        if r.dow is not None and r.hour is not None:
            d = int(r.dow)
            h = int(r.hour)
            cnt = int(r.count or 0)
            dur = float(r.duration or 0.0)
            data_map[(d, h)] = (cnt, dur)
            if cnt > max_count:
                max_count = cnt
            total_calls += cnt
            total_airtime += dur

    matrix = []
    day_totals = [0] * 7
    hour_totals = [0] * 24

    for d_idx, d_name in enumerate(DAYS):
        hours = []
        for h in range(24):
            cnt, dur = data_map.get((d_idx, h), (0, 0.0))
            h12 = 12 if (h == 0 or h == 12) else (h % 12)
            ampm = "AM" if h < 12 else "PM"
            hours.append({
                "hour": h,
                "label": f"{h12} {ampm}",
                "count": cnt,
                "duration": round(dur, 1),
            })
            day_totals[d_idx] += cnt
            hour_totals[h] += cnt

        matrix.append({
            "day": d_idx,
            "day_label": d_name,
            "hours": hours,
            "day_total": day_totals[d_idx],
        })

    peak_day_idx = max(range(7), key=lambda i: day_totals[i]) if total_calls > 0 else 0
    peak_hour_idx = max(range(24), key=lambda i: hour_totals[i]) if total_calls > 0 else 0
    peak_h12 = 12 if (peak_hour_idx == 0 or peak_hour_idx == 12) else (peak_hour_idx % 12)
    peak_ampm = "AM" if peak_hour_idx < 12 else "PM"

    return {
        "matrix": matrix,
        "max_count": max_count,
        "total_calls": total_calls,
        "total_airtime": round(total_airtime, 1),
        "peak_day": DAYS[peak_day_idx] if total_calls > 0 else "--",
        "peak_hour": f"{peak_h12} {peak_ampm}" if total_calls > 0 else "--",
        "range_start": query_start.isoformat(),
        "range_end": query_end.isoformat(),
    }


def _get_rtf_status(rtf: float) -> str:
    """Classify Real-Time Factor into operator status."""
    if rtf <= 0.35:
        return "nominal"
    elif rtf <= 0.75:
        return "moderate"
    elif rtf <= 1.0:
        return "saturated"
    return "backlog"


def get_rtf_telemetry(db: Session, start_date: date, end_date: date) -> Dict[str, Any]:
    """Calculate Real-Time Factor (RTF) and ingestion throughput performance."""
    start = datetime.combine(start_date, datetime.min.time())
    end = datetime.combine(end_date, datetime.max.time())

    agg = db.query(
        func.count(LogEntry.id).label("total_tx"),
        func.sum(LogEntry.duration).label("sum_dur"),
        func.sum(LogEntry.processing_time).label("sum_proc"),
        func.avg(LogEntry.duration).label("avg_dur"),
        func.avg(LogEntry.processing_time).label("avg_proc"),
        func.avg(LogEntry.confidence).label("avg_conf"),
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False)
    ).first()

    total_tx = int(agg.total_tx or 0) if agg else 0
    sum_dur = float(agg.sum_dur or 0.0) if agg else 0.0
    sum_proc = float(agg.sum_proc or 0.0) if agg else 0.0

    # Discover last model used from DB or config default
    last_model_row = db.query(LogEntry.model_used).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False),
        LogEntry.model_used.isnot(None),
        LogEntry.model_used != ""
    ).order_by(LogEntry.timestamp.desc()).first()
    configured_model = getattr(getattr(get_settings().config, "model", None), "name", None)
    model_name = last_model_row[0] if (last_model_row and last_model_row[0]) else (configured_model or "unknown")

    # Query hourly timeline
    hourly_rows = db.query(
        extract('hour', LogEntry.timestamp).label('hour'),
        func.count(LogEntry.id).label('count'),
        func.sum(LogEntry.duration).label('audio_s'),
        func.sum(LogEntry.processing_time).label('proc_s'),
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False)
    ).group_by(
        extract('hour', LogEntry.timestamp)
    ).all()

    hourly_map = {int(r.hour): r for r in hourly_rows}

    # If real data with processing time exists
    if total_tx > 0 and sum_dur > 0 and sum_proc > 0:
        rtf = round(sum_proc / sum_dur, 3)
        speedup = round(sum_dur / max(sum_proc, 0.001), 1)
        avg_latency_ms = round(float(agg.avg_proc or 0.0) * 1000, 1)
        avg_dur_s = round(float(agg.avg_dur or 0.0), 1)
        raw_conf = float(agg.avg_conf or 0.85)
        avg_conf = round(raw_conf * 100 if raw_conf <= 1.0 else raw_conf, 1)

        timeline = []
        for h in range(24):
            h12 = 12 if (h == 0 or h == 12) else (h % 12)
            ampm = "AM" if h < 12 else "PM"
            r = hourly_map.get(h)
            h_cnt = int(r.count) if r else 0
            h_audio = float(r.audio_s or 0.0) if r else 0.0
            h_proc = float(r.proc_s or 0.0) if r else 0.0
            h_rtf = round(h_proc / h_audio, 3) if h_audio > 0 else 0.0
            timeline.append({
                "hour": h,
                "label": f"{h12} {ampm}",
                "count": h_cnt,
                "audio_s": round(h_audio, 1),
                "proc_s": round(h_proc, 1),
                "rtf": h_rtf,
            })

        return {
            "rtf": rtf,
            "speedup": speedup,
            "total_audio_s": round(sum_dur, 1),
            "total_proc_s": round(sum_proc, 1),
            "avg_latency_ms": avg_latency_ms,
            "avg_duration_s": avg_dur_s,
            "avg_confidence": avg_conf,
            "model_used": model_name,
            "status": _get_rtf_status(rtf),
            "insufficient_data": False,
            "timeline": timeline,
        }

    # No transcriptions with measurable processing time in range
    timeline = []
    for h in range(24):
        r = hourly_map.get(h)
        timeline.append({
            "hour": h,
            "label": hour_label(h),
            "count": int(r.count) if r else 0,
            "audio_s": round(float(r.audio_s or 0.0), 1) if r else 0.0,
            "proc_s": round(float(r.proc_s or 0.0), 1) if r else 0.0,
            "rtf": 0.0,
        })

    return {
        "rtf": 0.0,
        "speedup": 0.0,
        "total_audio_s": round(sum_dur, 1),
        "total_proc_s": round(sum_proc, 1),
        "avg_latency_ms": 0.0,
        "avg_duration_s": round(float(agg.avg_dur or 0.0), 1) if agg else 0.0,
        "avg_confidence": 0.0,
        "model_used": model_name,
        "status": "nominal",
        "insufficient_data": True,
        "timeline": timeline,
    }


def get_ner_tactical_summary(
    events_db: Optional[Session],
    start_date: date,
    end_date: date,
    limit: int = 50
) -> Dict[str, Any]:
    """Aggregate top detected entities across categories from EntityObservation."""
    start = datetime.combine(start_date, datetime.min.time())
    end = datetime.combine(end_date, datetime.max.time())

    items: List[Dict[str, Any]] = []

    if events_db:
        try:
            rows = events_db.query(
                EntityObservation.canonical,
                EntityObservation.label,
                func.count(EntityObservation.id).label("freq"),
                func.min(EntityObservation.ts).label("first_seen"),
                func.max(EntityObservation.ts).label("last_seen"),
                func.max(EntityObservation.log_entry_id).label("sample_tx_id"),
            ).filter(
                EntityObservation.ts >= start,
                EntityObservation.ts <= end
            ).group_by(
                EntityObservation.canonical,
                EntityObservation.label
            ).order_by(
                func.count(EntityObservation.id).desc()
            ).limit(limit).all()

            for r in rows:
                if not r.canonical or not str(r.canonical).strip():
                    continue
                items.append({
                    "canonical": str(r.canonical).strip(),
                    "label": str(r.label).upper() if r.label else "UNKNOWN",
                    "freq": int(r.freq),
                    "first_seen": r.first_seen.isoformat() if r.first_seen else None,
                    "last_seen": r.last_seen.isoformat() if r.last_seen else None,
                    "sample_tx_id": int(r.sample_tx_id) if r.sample_tx_id else None,
                })
        except Exception as exc:
            logger.warning("Failed querying entity observations: %s", exc, exc_info=True)

    if items:
        units = [it for it in items if it["label"] == "UNIT"]
        call_types = [it for it in items if it["label"] == "EVT_TYPE"]
        locations = [it for it in items if it["label"] in ("LOC", "ADDRESS")]
        status = [it for it in items if it["label"] == "STATUS"]
        return {
            "all": items,
            "units": units,
            "call_types": call_types,
            "locations": locations,
            "status": status,
            "total_entities_detected": sum(it["freq"] for it in items),
            "insufficient_data": False,
        }

    return {
        "all": [],
        "units": [],
        "call_types": [],
        "locations": [],
        "status": [],
        "total_entities_detected": 0,
        "insufficient_data": True,
    }


def hour_label(h: int) -> str:
    """Return a 12-hour label such as '9 AM' for an hour 0-23."""
    h12 = 12 if h in (0, 12) else h % 12
    return f"{h12} {'AM' if h < 12 else 'PM'}"


def hour_clock_label(h: int) -> str:
    """Return a 12-hour clock label such as '9:00 AM' for an hour 0-23."""
    h12 = 12 if h in (0, 12) else h % 12
    return f"{h12}:00 {'AM' if h < 12 else 'PM'}"


def _hour_drivers_and_incident(
    db: Session,
    events_db: Optional[Session],
    target_date: date,
    hour: int,
    limit: int = 3,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Top talkgroups and most frequent NER call type for one hour of real traffic."""
    h_start = datetime.combine(target_date, time(hour, 0, 0))
    h_end = datetime.combine(target_date, time(hour, 59, 59))

    tg_rows = db.query(
        LogEntry.talkgroup,
        func.count(LogEntry.id).label('cnt')
    ).filter(
        LogEntry.timestamp >= h_start,
        LogEntry.timestamp <= h_end,
        LogEntry.is_deleted.is_(False)
    ).group_by(
        LogEntry.talkgroup
    ).order_by(
        func.count(LogEntry.id).desc()
    ).limit(limit).all()

    total_rows = sum(int(r.cnt) for r in tg_rows)
    hour_total = db.query(func.count(LogEntry.id)).filter(
        LogEntry.timestamp >= h_start,
        LogEntry.timestamp <= h_end,
        LogEntry.is_deleted.is_(False)
    ).scalar() or total_rows
    hour_total = max(1, int(hour_total))

    drivers = [
        {
            "talkgroup": r.talkgroup or "Unknown",
            "count": int(r.cnt),
            "percentage": round((int(r.cnt) / hour_total) * 100, 1),
        }
        for r in tg_rows
    ]

    likely_incident: Optional[str] = None
    if events_db is not None:
        try:
            log_ids = [
                row[0] for row in db.query(LogEntry.id).filter(
                    LogEntry.timestamp >= h_start,
                    LogEntry.timestamp <= h_end,
                    LogEntry.is_deleted.is_(False)
                ).all()
            ]
            counter: Counter = Counter()
            for i in range(0, len(log_ids), 500):
                chunk = log_ids[i:i + 500]
                span_rows = events_db.query(SpanStore.evt_type).filter(
                    SpanStore.log_entry_id.in_(chunk),
                    SpanStore.evt_type.isnot(None),
                ).all()
                for (evt_type,) in span_rows:
                    for item in str(evt_type).split(","):
                        cleaned = item.strip()
                        if cleaned:
                            counter[cleaned] += 1
            if counter:
                likely_incident = counter.most_common(1)[0][0]
        except SQLAlchemyError as exc:
            logger.warning("Failed to derive likely incident for hour %s: %s", hour, exc, exc_info=True)

    return drivers, likely_incident


def get_traffic_anomaly_telemetry(
    db: Session,
    target_date: date,
    events_db: Optional[Session] = None
) -> Dict[str, Any]:
    """Calculate radio traffic anomaly and surge metrics comparing volume against diurnal baseline."""
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())

    hourly_rows = db.query(
        extract('hour', LogEntry.timestamp).label('hour'),
        func.count(LogEntry.id).label('cnt')
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False)
    ).group_by(
        extract('hour', LogEntry.timestamp)
    ).all()

    observed_map = {int(r.hour): int(r.cnt) for r in hourly_rows}
    total_observed = sum(observed_map.values())

    if total_observed == 0:
        return {
            "current_hour_label": hour_label(min(23, max(0, datetime.now().hour))),
            "observed": 0,
            "baseline": 0,
            "surge_percentage": 0.0,
            "z_score": 0.0,
            "severity": "normal",
            "status_label": "No traffic recorded",
            "primary_driver": "",
            "drivers": [],
            "timeline": [
                {
                    "hour": h,
                    "label": hour_label(h),
                    "observed": 0,
                    "baseline": 0,
                    "upper_bound": 0.0,
                    "z_score": 0.0,
                    "is_anomaly": False,
                }
                for h in range(24)
            ],
            "recent_anomalies": [],
            "insufficient_data": True,
        }

    # extract('dow') is Sunday=0; date.weekday() is Monday=0.
    dow = (target_date.weekday() + 1) % 7
    trailing_start = target_date - timedelta(days=21)

    # Count distinct calendar days matching this weekday in the trailing 21-day window that have logged traffic
    active_trailing_days = (
        db.query(func.count(func.distinct(func.date(LogEntry.timestamp))))
        .filter(
            LogEntry.timestamp >= datetime.combine(trailing_start, datetime.min.time()),
            LogEntry.timestamp < start,
            extract('dow', LogEntry.timestamp) == dow,
            LogEntry.is_deleted.is_(False),
        )
        .scalar()
        or 0
    )
    divisor = max(1, int(active_trailing_days))

    hist_rows = db.query(
        extract('hour', LogEntry.timestamp).label('hour'),
        func.count(LogEntry.id).label('cnt')
    ).filter(
        LogEntry.timestamp >= datetime.combine(trailing_start, datetime.min.time()),
        LogEntry.timestamp < start,
        extract('dow', LogEntry.timestamp) == dow,
        LogEntry.is_deleted.is_(False)
    ).group_by(
        extract('hour', LogEntry.timestamp)
    ).all()

    baseline_map = {int(r.hour): max(5, int(r.cnt // divisor)) for r in hist_rows}
    for h in range(24):
        if h not in baseline_map:
            baseline_map[h] = max(4, int(total_observed / 24 * 0.8))

    timeline = []
    anomalies = []
    peak_hour = 0
    peak_z = -999.0

    for h in range(24):
        obs = observed_map.get(h, 0)
        base = baseline_map.get(h, 10)
        sigma = max(2.5, math.sqrt(base) * 0.85)
        z_score = round((obs - base) / sigma, 2)
        upper_bound = round(base + 2.0 * sigma, 1)
        is_anomaly = obs >= upper_bound and obs >= 8

        if z_score > peak_z:
            peak_z = z_score
            peak_hour = h

        timeline.append({
            "hour": h,
            "label": hour_label(h),
            "observed": obs,
            "baseline": base,
            "upper_bound": upper_bound,
            "z_score": z_score,
            "is_anomaly": is_anomaly,
        })

        if is_anomaly:
            hour_drivers, likely_incident = _hour_drivers_and_incident(db, events_db, target_date, h, limit=1)
            anomalies.append({
                "hour": h,
                "time_window": f"{hour_clock_label(h)} – {hour_clock_label((h + 1) % 24)}",
                "z_score": z_score,
                "observed": obs,
                "baseline": base,
                "primary_driver": hour_drivers[0]["talkgroup"] if hour_drivers else "Unknown",
                "likely_incident": likely_incident,
            })

    cur_h = min(23, max(0, datetime.now().hour))
    focus_h = peak_hour if (timeline[peak_hour]["z_score"] >= 1.5) else cur_h
    focus_pt = timeline[focus_h]

    drivers, _ = _hour_drivers_and_incident(db, events_db, target_date, focus_h, limit=3)
    primary_driver = drivers[0]["talkgroup"] if drivers else ""
    z = focus_pt["z_score"]
    surge_pct = round(((focus_pt["observed"] - focus_pt["baseline"]) / max(1, focus_pt["baseline"])) * 100, 1)

    if z >= 3.0:
        severity = "critical"
        status_label = f"Critical Anomaly ({z:+.1f}σ)"
    elif z >= 2.0:
        severity = "high"
        status_label = f"High Surge Alert ({z:+.1f}σ)"
    elif z >= 1.0:
        severity = "elevated"
        status_label = f"Elevated Traffic ({z:+.1f}σ)"
    else:
        severity = "normal"
        status_label = f"Nominal Flow ({z:+.1f}σ)"

    return {
        "current_hour_label": focus_pt["label"],
        "observed": focus_pt["observed"],
        "baseline": focus_pt["baseline"],
        "surge_percentage": surge_pct,
        "z_score": z,
        "severity": severity,
        "status_label": status_label,
        "primary_driver": primary_driver,
        "drivers": drivers,
        "timeline": timeline,
        "recent_anomalies": anomalies,
        # Baseline is estimated from the same day when fewer than 25 calls exist.
        "insufficient_data": total_observed < 25,
    }


def get_asr_quality_spectrum(db: Session, start_date: date, end_date: date) -> Dict[str, Any]:
    """Calculate Whisper ASR confidence and signal fidelity breakdown across quality tiers."""
    start = datetime.combine(start_date, datetime.min.time())
    end = datetime.combine(end_date, datetime.max.time())

    rows = db.query(
        LogEntry.confidence
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted.is_(False),
        LogEntry.confidence.isnot(None)
    ).all()

    total = len(rows)
    if total > 0:
        high = 0
        moderate = 0
        low = 0
        sum_conf = 0.0

        for (conf_val,) in rows:
            c = float(conf_val or 0.0)
            score = c * 100.0 if c <= 1.0 else c
            sum_conf += score
            if score >= 85.0:
                high += 1
            elif score >= 70.0:
                moderate += 1
            else:
                low += 1

        mean_conf = round(sum_conf / max(1, total), 1)
        return {
            "high_count": high,
            "high_percentage": round((high / total) * 100, 1),
            "moderate_count": moderate,
            "moderate_percentage": round((moderate / total) * 100, 1),
            "low_count": low,
            "low_percentage": round((low / total) * 100, 1),
            "mean_confidence": mean_conf,
            "total_evaluated": total,
            "insufficient_data": total < 10,
        }

    return {
        "high_count": 0,
        "high_percentage": 0.0,
        "moderate_count": 0,
        "moderate_percentage": 0.0,
        "low_count": 0,
        "low_percentage": 0.0,
        "mean_confidence": 0.0,
        "total_evaluated": 0,
        "insufficient_data": True,
    }


def compute_insights_stats(
    db: Session,
    target_date: date,
    view: str,
    date_to: Optional[date] = None,
    events_db: Optional[Session] = None,
) -> Dict[str, Any]:
    """Compute complete insights stats payload for a date or date range."""
    # Check if a multi-day range was provided
    if date_to is not None and date_to != target_date:
        start_date = min(target_date, date_to)
        end_date = max(target_date, date_to)
        num_days = (end_date - start_date).days + 1
    else:
        start_date = target_date
        end_date = target_date
        num_days = 1

    if num_days > 1:
        # Multi-day range: graph adapts to range timeline
        effective_view = "weekly" if (view == "weekly" or (num_days > 35 and view != "daily")) else "daily"
        summary = get_range_summary(db, start_date, end_date)
        activity = get_range_activity(db, start_date, end_date, events_db=events_db, view=effective_view)
        talkgroups = get_range_talkgroup_breakdown(db, start_date, end_date, limit=10)
        all_talkgroups = get_all_range_talkgroups(db, start_date, end_date)
        recent = get_range_recent_activity(db, start_date, end_date, limit=50, events_db=events_db)
    else:
        # Single day
        if view == "hourly":
            summary = get_daily_summary(db, target_date)
            activity = get_hourly_activity(db, target_date, events_db=events_db)
        elif view == "daily":
            summary = get_weekly_summary(db, target_date)
            activity = get_daily_activity(db, target_date, events_db=events_db)
        else:  # weekly
            summary = get_monthly_summary(db, target_date)
            activity = get_weekly_activity(db, target_date, events_db=events_db)

        talkgroups = get_talkgroup_breakdown(db, target_date, view)
        recent = get_recent_activity(db, target_date, limit=50, events_db=events_db)
        all_talkgroups = get_all_talkgroups(db, target_date, view)

    calls_last_minute = get_last_full_minute_transcription_count(db)
    summary["calls_last_minute"] = calls_last_minute
    summary["calls_per_minute_window"] = 1
    summary["trends"] = get_summary_trends(db, calls_last_minute)

    heatmap = get_diurnal_heatmap(db, start_date, end_date)
    rtf_telemetry = get_rtf_telemetry(db, start_date, end_date)
    ner_summary = get_ner_tactical_summary(events_db or db, start_date, end_date)
    traffic_anomaly = get_traffic_anomaly_telemetry(db, start_date, events_db=events_db or db)
    asr_quality = get_asr_quality_spectrum(db, start_date, end_date)

    return {
        "summary": summary,
        "activity": activity,
        "talkgroups": talkgroups,
        "talkgroups_all": all_talkgroups,
        "recent": recent,
        "heatmap": heatmap,
        "rtf": rtf_telemetry,
        "ner": ner_summary,
        "anomaly": traffic_anomaly,
        "asr_quality": asr_quality,
    }

