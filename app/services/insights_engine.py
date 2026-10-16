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
    except Exception as exc:
        logger.debug("Failed to query range daily events: %s", exc)
        return {}


def get_range_summary(db: Session, start_date: date, end_date: date) -> Dict[str, Any]:
    """Get summary statistics across an arbitrary date range."""
    start = datetime.combine(start_date, datetime.min.time())
    end = datetime.combine(end_date, datetime.max.time())

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

    # Determine peak day in range
    peak_row = db.query(
        func.date(LogEntry.timestamp).label('day'),
        func.count(LogEntry.id).label('cnt')
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        LogEntry.is_deleted == False
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
                LogEntry.is_deleted == False
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
        LogEntry.is_deleted == False
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
    ).limit(limit).all()
    return [{"talkgroup": r.talkgroup, "count": r.count} for r in results]


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


def get_range_recent_activity(db: Session, start_date: date, end_date: date, limit: int = 50, events_db: Optional[Session] = None) -> List[Dict[str, Any]]:
    """Get recent transcriptions within date range."""
    start = datetime.combine(start_date, datetime.min.time())
    end = datetime.combine(end_date, datetime.max.time())
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
        LogEntry.is_deleted == False
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

    return {
        "summary": summary,
        "activity": activity,
        "talkgroups": talkgroups,
        "talkgroups_all": all_talkgroups,
        "recent": recent,
        "heatmap": heatmap,
    }

