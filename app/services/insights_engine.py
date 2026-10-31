"""Insights analytics and aggregation engine."""
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
import logging
import math
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, extract, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.event import EntityObservation, Event, EventTranscriptLink, SpanStore
from ..models.log_entry import LogEntry

logger = logging.getLogger(__name__)

_NOISE_INCIDENT_TERMS = frozenset({
    "status check",
    "check",
    "service",
    "in service",
    "out of service",
    "rest",
    "rog",
    "roger",
    "copy",
    "clear",
    "10-4",
    "10-8",
    "traffic",
    "unknown",
    "none",
    "n/a",
    "test",
})


def _not_deleted():
    """SQLite-friendly non-deleted predicate that avoids driving scans via ix_log_entries_is_deleted."""
    return LogEntry.is_deleted.is_not(True)


def _valid_speech():
    """Exclude Silero VAD rejected silent/noise rows from speech quality and Whisper inference metrics."""
    return and_(
        LogEntry.transcript.isnot(None),
        LogEntry.transcript != "VAD_REJECTED",
        ~LogEntry.transcript.contains("[VAD_REJECTED]"),
    )


def _clean_incident_type(raw_val: Optional[str]) -> Optional[str]:
    """Normalize and filter raw SpanStore evt_type strings so punctuation or chatter tokens are ignored."""
    if not raw_val:
        return None
    cleaned = str(raw_val).strip().strip(".,;:!?\"'()[]-")
    if len(cleaned) < 3:
        return None
    if not any(ch.isalpha() for ch in cleaned):
        return None
    if cleaned.lower() in _NOISE_INCIDENT_TERMS:
        return None
    return cleaned


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


def _utc_now_naive() -> datetime:
    """Return current UTC time as a naive datetime without deprecation warnings."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_last_full_minute_window(now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """Return [start, end) for the previous complete minute in UTC wall-clock time."""
    now_utc = now or _utc_now_naive()
    end = now_utc.replace(second=0, microsecond=0)
    start = end - timedelta(minutes=1)
    return start, end


def get_last_full_hour_window(now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """Return [start, end) for the previous complete hour in UTC wall-clock time."""
    now_utc = now or _utc_now_naive()
    end = now_utc.replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=1)
    return start, end


def _recent_rowid_floor(db: Session, window_rows: int = 25000) -> int:
    """Return a safe primary-key lower bound for recent created_at queries on large tables."""
    try:
        max_id = db.query(func.max(LogEntry.id)).scalar() or 0
        return max(0, int(max_id) - window_rows)
    except SQLAlchemyError:
        return 0


def get_last_full_minute_transcription_count(db: Session) -> int:
    """Count transcriptions created in the previous full minute."""
    start, end = get_last_full_minute_window()
    return get_transcription_count_by_created_window(db, start, end)


def get_transcription_count_by_created_window(db: Session, start: datetime, end: datetime) -> int:
    """Count transcriptions by created_at for [start, end) in UTC naive datetimes."""
    id_floor = _recent_rowid_floor(db, 10000)
    return int(
        db.query(func.count(LogEntry.id)).filter(
            LogEntry.id >= id_floor,
            LogEntry.created_at >= start,
            LogEntry.created_at < end,
            _not_deleted(),
        ).scalar() or 0
    )


def get_unique_talkgroups_by_created_window(db: Session, start: datetime, end: datetime) -> int:
    """Count distinct talkgroups by created_at for [start, end)."""
    id_floor = _recent_rowid_floor(db, 25000)
    return int(
        db.query(func.count(func.distinct(LogEntry.talkgroup))).filter(
            LogEntry.id >= id_floor,
            LogEntry.created_at >= start,
            LogEntry.created_at < end,
            _not_deleted(),
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


def get_summary_trends(
    db: Session,
    calls_last_minute: int,
    today_unique_talkgroups: Optional[int] = None,
) -> Dict[str, Dict[str, object]]:
    """Trend payload for stat cards with requested comparison windows."""
    hour_start, hour_end = get_last_full_hour_window()
    prev_hour_start = hour_start - timedelta(hours=1)
    prev_hour_end = hour_start

    min_start, _ = get_last_full_minute_window()
    prev_min_start = min_start - timedelta(minutes=1)
    prev_min_end = min_start

    id_floor_recent = _recent_rowid_floor(db, 10000)
    counts_row = db.query(
        func.sum(
            case(
                (and_(LogEntry.created_at >= hour_start, LogEntry.created_at < hour_end), 1),
                else_=0,
            )
        ).label("total_hour"),
        func.sum(
            case(
                (and_(LogEntry.created_at >= prev_hour_start, LogEntry.created_at < prev_hour_end), 1),
                else_=0,
            )
        ).label("total_prev_hour"),
        func.sum(
            case(
                (and_(LogEntry.created_at >= prev_min_start, LogEntry.created_at < prev_min_end), 1),
                else_=0,
            )
        ).label("calls_prev_minute"),
    ).filter(
        LogEntry.id >= id_floor_recent,
        LogEntry.created_at >= prev_hour_start,
        LogEntry.created_at < hour_end,
        _not_deleted(),
    ).first()

    total_hour = int(counts_row.total_hour or 0) if counts_row else 0
    total_prev_hour = int(counts_row.total_prev_hour or 0) if counts_row else 0
    calls_prev_minute = int(counts_row.calls_prev_minute or 0) if counts_row else 0

    day_end = _utc_now_naive()
    day_start = day_end - timedelta(days=1)
    prev_day_start = day_start - timedelta(days=1)
    prev_day_end = day_start
    tg_last_day = (
        int(today_unique_talkgroups)
        if today_unique_talkgroups is not None
        else get_unique_talkgroups_by_created_window(db, day_start, day_end)
    )
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
        _not_deleted(),
    ).group_by(
        extract('hour', LogEntry.timestamp)
    ).all()

    hour_counts = {int(r.hour): int(r.count) for r in results}
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
    end_of_week = start_of_week + timedelta(days=6)
    tz = get_local_tz()
    events_day_counts = get_event_daily_counts(events_db, start_of_week, tz)

    start_dt = datetime.combine(start_of_week, datetime.min.time())
    end_dt = datetime.combine(end_of_week, datetime.max.time())
    rows = db.query(
        func.date(LogEntry.timestamp).label("day_str"),
        func.count(LogEntry.id).label("count"),
    ).filter(
        LogEntry.timestamp >= start_dt,
        LogEntry.timestamp <= end_dt,
        _not_deleted(),
    ).group_by(
        func.date(LogEntry.timestamp)
    ).all()
    day_map = {str(r.day_str): int(r.count) for r in rows}

    activity = []
    for i in range(7):
        day = start_of_week + timedelta(days=i)
        d_str = day.isoformat()
        activity.append({
            "label": day.strftime("%a"),
            "count": day_map.get(d_str, 0),
            "events_count": events_day_counts.get(day, 0),
            "date": d_str,
        })
    return activity


def get_weekly_activity(db: Session, target_date: date, events_db: Optional[Session] = None) -> List[Dict[str, Any]]:
    """Get weekly activity for the last 8 weeks."""
    tz = get_local_tz()
    earliest_week_start = target_date - timedelta(weeks=7, days=target_date.weekday())
    latest_week_end = target_date - timedelta(weeks=0, days=target_date.weekday()) + timedelta(days=6)
    events_week_counts = get_event_weekly_counts(events_db, earliest_week_start, latest_week_end, tz)

    start_dt = datetime.combine(earliest_week_start, datetime.min.time())
    end_dt = datetime.combine(latest_week_end, datetime.max.time())
    rows = db.query(
        func.date(LogEntry.timestamp).label("day_str"),
        func.count(LogEntry.id).label("count"),
    ).filter(
        LogEntry.timestamp >= start_dt,
        LogEntry.timestamp <= end_dt,
        _not_deleted(),
    ).group_by(
        func.date(LogEntry.timestamp)
    ).all()

    week_map: Dict[date, int] = defaultdict(int)
    for r in rows:
        if r.day_str:
            try:
                d_obj = datetime.strptime(str(r.day_str)[:10], "%Y-%m-%d").date()
                w_start = d_obj - timedelta(days=d_obj.weekday())
                week_map[w_start] += int(r.count or 0)
            except ValueError:
                pass

    activity = []
    for i in range(7, -1, -1):
        week_start = target_date - timedelta(weeks=i, days=target_date.weekday())
        activity.append({
            "label": week_start.strftime("%m/%d"),
            "count": week_map.get(week_start, 0),
            "events_count": events_week_counts.get(week_start, 0),
            "date": week_start.isoformat(),
        })
    return activity


def _query_window_summary_agg(db: Session, start: datetime, end: datetime) -> Tuple[int, int, float, float]:
    """Single-pass SQL aggregation for (total_count, unique_talkgroups, avg_duration, total_airtime)."""
    row = db.query(
        func.count(LogEntry.id).label("total"),
        func.count(func.distinct(LogEntry.talkgroup)).label("unique_tg"),
        func.avg(LogEntry.duration).label("avg_dur"),
        func.sum(LogEntry.duration).label("sum_dur"),
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        _not_deleted(),
    ).first()
    if not row:
        return 0, 0, 0.0, 0.0
    return (
        int(row.total or 0),
        int(row.unique_tg or 0),
        round(float(row.avg_dur or 0.0), 2),
        round(float(row.sum_dur or 0.0), 1),
    )


def get_daily_summary(db: Session, target_date: date) -> Dict[str, Any]:
    """Get summary stats for a specific day."""
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())

    total, unique_tg, avg_duration, total_airtime = _query_window_summary_agg(db, start, end)

    peak_result = db.query(
        extract('hour', LogEntry.timestamp).label('hour'),
        func.count(LogEntry.id).label('count')
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        _not_deleted(),
    ).group_by(
        extract('hour', LogEntry.timestamp)
    ).order_by(
        func.count(LogEntry.id).desc()
    ).first()

    peak_hour = f"{int(peak_result.hour):02d}:00" if peak_result else "--"
    now_local = datetime.now()
    if target_date == now_local.date():
        elapsed_min = max(1.0, (now_local - start).total_seconds() / 60.0)
        minutes_in_period = min(24.0 * 60.0, elapsed_min)
    else:
        minutes_in_period = 24.0 * 60.0
    calls_per_minute = round(total / minutes_in_period, 2) if minutes_in_period else 0

    return {
        "total": total,
        "unique_talkgroups": unique_tg,
        "avg_duration": avg_duration,
        "total_airtime": total_airtime,
        "peak_hour": peak_hour,
        "calls_per_minute": calls_per_minute,
    }


def get_weekly_summary(db: Session, target_date: date) -> Dict[str, Any]:
    """Get summary stats for the week."""
    start_of_week = target_date - timedelta(days=target_date.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    start = datetime.combine(start_of_week, datetime.min.time())
    end = datetime.combine(end_of_week, datetime.max.time())

    total, unique_tg, avg_duration, total_airtime = _query_window_summary_agg(db, start, end)

    peak_row = db.query(
        func.date(LogEntry.timestamp).label("day"),
        func.count(LogEntry.id).label("cnt"),
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        _not_deleted(),
    ).group_by(
        func.date(LogEntry.timestamp)
    ).order_by(
        func.count(LogEntry.id).desc()
    ).first()

    if peak_row and peak_row.day:
        try:
            peak_label = datetime.strptime(str(peak_row.day)[:10], "%Y-%m-%d").strftime("%a %b %d")
        except ValueError:
            peak_label = str(peak_row.day)
    else:
        peak_label = "--"

    minutes_in_period = 7 * 24 * 60
    calls_per_minute = round(total / minutes_in_period, 2) if minutes_in_period else 0

    return {
        "total": total,
        "unique_talkgroups": unique_tg,
        "avg_duration": avg_duration,
        "total_airtime": total_airtime,
        "peak_hour": peak_label,
        "calls_per_minute": calls_per_minute,
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

    total, unique_tg, avg_duration, total_airtime = _query_window_summary_agg(db, start, end)

    peak_row = db.query(
        func.date(LogEntry.timestamp).label("day"),
        func.count(LogEntry.id).label("cnt"),
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        _not_deleted(),
    ).group_by(
        func.date(LogEntry.timestamp)
    ).order_by(
        func.count(LogEntry.id).desc()
    ).first()

    if peak_row and peak_row.day:
        try:
            peak_label = datetime.strptime(str(peak_row.day)[:10], "%Y-%m-%d").strftime("%b %d")
        except ValueError:
            peak_label = str(peak_row.day)
    else:
        peak_label = "--"

    days_in_month = (end_of_month - start_of_month).days + 1
    minutes_in_period = days_in_month * 24 * 60
    calls_per_minute = round(total / minutes_in_period, 2) if minutes_in_period else 0

    return {
        "total": total,
        "unique_talkgroups": unique_tg,
        "avg_duration": avg_duration,
        "total_airtime": total_airtime,
        "peak_hour": peak_label,
        "calls_per_minute": calls_per_minute,
    }


def _compute_talkgroup_share_list(db: Session, start: datetime, end: datetime, limit: int = 10) -> List[Dict[str, Any]]:
    """Compute top talkgroups with true airtime share % and call volume share % against full period totals."""
    base_filter = [
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        _not_deleted(),
        LogEntry.talkgroup.isnot(None),
        LogEntry.talkgroup != "",
        LogEntry.talkgroup != "N/A",
    ]
    totals_row = db.query(
        func.count(LogEntry.id).label("total_calls"),
        func.sum(LogEntry.duration).label("total_dur"),
    ).filter(*base_filter).first()

    period_calls = int(totals_row.total_calls or 0) if totals_row else 0
    period_airtime = float(totals_row.total_dur or 0.0) if totals_row else 0.0

    results = db.query(
        LogEntry.talkgroup,
        func.count(LogEntry.id).label("count"),
        func.sum(LogEntry.duration).label("duration"),
        func.avg(LogEntry.duration).label("avg_duration"),
    ).filter(*base_filter).group_by(
        LogEntry.talkgroup
    ).order_by(
        func.count(LogEntry.id).desc()
    ).limit(limit).all()

    denom_airtime = period_airtime if period_airtime > 0 else sum(float(r.duration or 0.0) for r in results)
    denom_calls = period_calls if period_calls > 0 else sum(int(r.count or 0) for r in results)

    out = []
    for r in results:
        cnt = int(r.count or 0)
        dur = round(float(r.duration or 0.0), 1)
        pct = round((dur / max(denom_airtime, 0.001)) * 100.0, 1) if denom_airtime > 0 else 0.0
        call_pct = round((cnt / max(denom_calls, 1)) * 100.0, 1) if denom_calls > 0 else 0.0
        out.append({
            "talkgroup": r.talkgroup,
            "count": cnt,
            "duration": dur,
            "avg_duration": round(float(r.avg_duration or 0.0), 1),
            "percentage": pct,
            "call_percentage": call_pct,
        })
    return out


def get_talkgroup_breakdown(db: Session, target_date: date, view: str, limit: int = 10) -> List[Dict[str, Any]]:
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

    return _compute_talkgroup_share_list(db, start, end, limit=limit)


def get_all_talkgroups(db: Session, target_date: date, view: str) -> List[Dict[str, Any]]:
    """Pull all distinct talkgroups from DB for the period with airtime and call share metrics."""
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
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        _not_deleted(),
    ).group_by(
        LogEntry.talkgroup
    ).order_by(
        func.count(LogEntry.id).desc()
    ).all()

    merged_cnt: Dict[str, int] = defaultdict(int)
    merged_dur: Dict[str, float] = defaultdict(float)
    for r in results:
        tg = r.talkgroup if (r.talkgroup and str(r.talkgroup).strip()) else "N/A"
        merged_cnt[tg] += int(r.count or 0)
        merged_dur[tg] += float(r.duration or 0.0)

    total_calls = sum(merged_cnt.values())
    total_airtime = sum(merged_dur.values())
    out = []
    for tg, cnt in merged_cnt.items():
        dur = round(merged_dur[tg], 1)
        avg_dur = round(merged_dur[tg] / max(cnt, 1), 1)
        pct = round((dur / max(total_airtime, 0.001)) * 100.0, 1) if total_airtime > 0 else 0.0
        call_pct = round((cnt / max(total_calls, 1)) * 100.0, 1) if total_calls > 0 else 0.0
        out.append({
            "talkgroup": tg,
            "count": cnt,
            "duration": dur,
            "avg_duration": avg_dur,
            "percentage": pct,
            "call_percentage": call_pct,
        })
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
        logger.warning("Failed to query attached events for logs: %s", exc, exc_info=True)
        return {}


def get_recent_activity(db: Session, target_date: date, limit: int = 20, events_db: Optional[Session] = None) -> List[Dict[str, Any]]:
    """Get recent transcriptions for the day."""
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())

    results = db.query(LogEntry).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        _not_deleted(),
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

    total, unique_tg, avg_duration, total_airtime = _query_window_summary_agg(db, start, end)

    # Determine peak day in range
    peak_row = db.query(
        func.date(LogEntry.timestamp).label('day'),
        func.count(LogEntry.id).label('cnt')
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        _not_deleted(),
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

    now_local = datetime.now()
    if end_date == now_local.date() and days >= 1:
        elapsed_today_min = max(1.0, (now_local - datetime.combine(end_date, datetime.min.time())).total_seconds() / 60.0)
        minutes_in_period = max(1.0, (days - 1) * 24.0 * 60.0 + min(24.0 * 60.0, elapsed_today_min))
    else:
        minutes_in_period = float(max(1, days * 24 * 60))
    calls_per_minute = round(total / minutes_in_period, 2) if minutes_in_period else 0

    return {
        "total": total,
        "unique_talkgroups": unique_tg,
        "avg_duration": avg_duration,
        "total_airtime": total_airtime,
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

    results = db.query(
        func.date(LogEntry.timestamp).label('day_str'),
        func.count(LogEntry.id).label('count')
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        _not_deleted(),
    ).group_by(
        func.date(LogEntry.timestamp)
    ).all()
    day_counts = {str(r.day_str): int(r.count) for r in results}
    events_day_counts = get_event_daily_range_counts(events_db, start_date, end_date, tz)

    if view == "weekly" or (num_days > 35 and view != "daily"):
        # Weekly buckets clipped strictly to [start_date, end_date]
        week_start = start_date - timedelta(days=start_date.weekday())
        activity = []
        cur_w = week_start
        while cur_w <= end_date:
            cur_end = cur_w + timedelta(days=6)
            bucket_start = max(cur_w, start_date)
            bucket_end = min(cur_end, end_date)
            count = 0
            ev_count = 0
            d_iter = bucket_start
            while d_iter <= bucket_end:
                count += day_counts.get(d_iter.isoformat(), 0)
                ev_count += events_day_counts.get(d_iter, 0)
                d_iter += timedelta(days=1)

            activity.append({
                "label": bucket_start.strftime("%m/%d"),
                "count": count,
                "events_count": ev_count,
                "date": bucket_start.isoformat(),
            })
            cur_w += timedelta(days=7)
        return activity

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
    return _compute_talkgroup_share_list(db, start, end, limit=limit)


def get_all_range_talkgroups(db: Session, start_date: date, end_date: date) -> List[Dict[str, Any]]:
    """Pull all distinct talkgroups across date range with airtime and call share metrics."""
    start = datetime.combine(start_date, datetime.min.time())
    end = datetime.combine(end_date, datetime.max.time())
    results = db.query(
        LogEntry.talkgroup,
        func.count(LogEntry.id).label('count'),
        func.sum(LogEntry.duration).label('duration'),
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        _not_deleted(),
    ).group_by(
        LogEntry.talkgroup
    ).order_by(
        func.count(LogEntry.id).desc()
    ).all()
    merged_cnt: Dict[str, int] = defaultdict(int)
    merged_dur: Dict[str, float] = defaultdict(float)
    for r in results:
        tg = r.talkgroup if (r.talkgroup and str(r.talkgroup).strip()) else "N/A"
        merged_cnt[tg] += int(r.count or 0)
        merged_dur[tg] += float(r.duration or 0.0)

    total_calls = sum(merged_cnt.values())
    total_airtime = sum(merged_dur.values())
    out = []
    for tg, cnt in merged_cnt.items():
        dur = round(merged_dur[tg], 1)
        avg_dur = round(merged_dur[tg] / max(cnt, 1), 1)
        pct = round((dur / max(total_airtime, 0.001)) * 100.0, 1) if total_airtime > 0 else 0.0
        call_pct = round((cnt / max(total_calls, 1)) * 100.0, 1) if total_calls > 0 else 0.0
        out.append({
            "talkgroup": tg,
            "count": cnt,
            "duration": dur,
            "avg_duration": avg_dur,
            "percentage": pct,
            "call_percentage": call_pct,
        })
    return out


def get_talkgroup_tracker_telemetry(
    db: Session,
    start_date: date,
    end_date: date,
) -> Dict[str, Any]:
    """
    Extract comprehensive talkgroup tracking telemetry across [start_date, end_date].
    Includes:
    - Complete ranking of every observed talkgroup (count, airtime, avg duration, percentage share).
    - Identification of newly seen talkgroups (first seen in DB during period).
    - Newly active talkgroups compared to previous day.
    - Identification of busiest talkgroup of the period.
    """
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
        LogEntry.talkgroup != '',
        LogEntry.talkgroup != 'N/A'
    ).group_by(
        LogEntry.talkgroup
    ).order_by(
        func.count(LogEntry.id).desc()
    ).all()

    total_calls = sum(int(r.count or 0) for r in results)
    total_airtime = sum(float(r.duration or 0) for r in results)

    tg_names = [str(r.talkgroup).strip() for r in results if r.talkgroup and str(r.talkgroup).strip()]

    # First seen in DB
    first_seen_map: Dict[str, datetime] = {}
    if tg_names:
        try:
            first_rows = db.query(
                LogEntry.talkgroup,
                func.min(LogEntry.timestamp).label('first_seen')
            ).filter(
                LogEntry.talkgroup.in_(tg_names),
                LogEntry.is_deleted.is_(False)
            ).group_by(
                LogEntry.talkgroup
            ).all()
            for r in first_rows:
                if r.talkgroup:
                    first_seen_map[str(r.talkgroup).strip()] = r.first_seen
        except Exception as exc:
            logger.warning("Failed querying first_seen talkgroups: %s", exc)

    # Previous day talkgroups
    prev_day = start_date - timedelta(days=1)
    prev_start = datetime.combine(prev_day, datetime.min.time())
    prev_end = datetime.combine(prev_day, datetime.max.time())
    prev_day_tgs = set()
    try:
        prev_rows = db.query(LogEntry.talkgroup).distinct().filter(
            LogEntry.timestamp >= prev_start,
            LogEntry.timestamp <= prev_end,
            LogEntry.is_deleted.is_(False),
            LogEntry.talkgroup.isnot(None),
            LogEntry.talkgroup != '',
            LogEntry.talkgroup != 'N/A'
        ).all()
        prev_day_tgs = {str(r[0]).strip() for r in prev_rows if r[0]}
    except Exception as exc:
        logger.warning("Failed querying prev_day talkgroups: %s", exc)

    ranked: List[Dict[str, Any]] = []
    for r in results:
        dur = round(float(r.duration or 0), 1)
        pct = round((dur / max(total_airtime, 0.001)) * 100, 1) if total_airtime > 0 else 0.0
        tg = str(r.talkgroup).strip()
        first_dt = first_seen_map.get(tg)
        is_first_seen = bool(first_dt and first_dt >= start)
        is_new_yesterday = (tg not in prev_day_tgs)
        ranked.append({
            "talkgroup": tg,
            "count": int(r.count or 0),
            "duration": dur,
            "avg_duration": round(float(r.avg_duration or 0), 1),
            "percentage": pct,
            "is_new": is_first_seen,
            "is_new_vs_yesterday": is_new_yesterday,
            "first_seen": first_dt.isoformat() if first_dt else None,
        })

    busiest = ranked[0] if ranked else None
    new_tgs = [item for item in ranked if item.get("is_new")]
    new_vs_yesterday = [item for item in ranked if item.get("is_new_vs_yesterday")]

    return {
        "total_talkgroups": len(ranked),
        "total_calls": total_calls,
        "total_airtime": round(total_airtime, 1),
        "busiest_talkgroup": busiest,
        "new_talkgroups_count": len(new_tgs),
        "new_talkgroups": new_tgs,
        "new_vs_yesterday": new_vs_yesterday,
        "ranked_talkgroups": ranked,
    }


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
        _not_deleted(),
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
        _not_deleted(),
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

    # Normalize peak_day selection by number of occurrences of each weekday in [query_start, query_end]
    dow_occurrences = [0] * 7
    span_days = max(1, (query_end - query_start).days + 1)
    for offset in range(span_days):
        cur_d = query_start + timedelta(days=offset)
        dow_occurrences[(cur_d.weekday() + 1) % 7] += 1

    peak_day_idx = (
        max(
            range(7),
            key=lambda i: (day_totals[i] / max(1, dow_occurrences[i]), day_totals[i]),
        )
        if total_calls > 0
        else 0
    )
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
        func.avg(case((LogEntry.confidence > 0, LogEntry.confidence), else_=None)).label("avg_conf"),
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        _not_deleted(),
        _valid_speech(),
    ).first()

    total_tx = int(agg.total_tx or 0) if agg else 0
    sum_dur = float(agg.sum_dur or 0.0) if agg else 0.0
    sum_proc = float(agg.sum_proc or 0.0) if agg else 0.0

    # Discover last model used from DB or config default
    last_model_row = db.query(LogEntry.model_used).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        _not_deleted(),
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
        _not_deleted(),
        _valid_speech(),
    ).group_by(
        extract('hour', LogEntry.timestamp)
    ).all()

    hourly_map = {int(r.hour): r for r in hourly_rows}

    # If real data with processing time exists
    if total_tx > 0 and sum_dur > 0 and sum_proc > 0:
        rtf = round(sum_proc / sum_dur, 3)
        raw_speedup = sum_dur / max(sum_proc, 0.001)
        speedup = round(raw_speedup, 2 if raw_speedup < 1.0 else 1)
        avg_latency_ms = round(float(agg.avg_proc or 0.0) * 1000, 1)
        avg_dur_s = round(float(agg.avg_dur or 0.0), 1)
        raw_conf = float(agg.avg_conf) if (agg and agg.avg_conf is not None) else 0.0
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


_TACTICAL_NER_LABELS = ("UNIT", "EVT_TYPE", "LOC", "ADDRESS", "STATUS")


def _is_valid_ner_entity(canonical: str, label: str) -> bool:
    """Filter single-character or punctuation fragments from NER entity aggregations."""
    cleaned = canonical.strip().strip(".,;:!?\"'()[]-")
    if len(cleaned) < 2:
        return False
    if not any(ch.isalnum() for ch in cleaned):
        return False
    if label in ("LOC", "ADDRESS", "EVT_TYPE"):
        if not any(ch.isalpha() for ch in cleaned):
            return False
        if cleaned.lower() in {"st", "rd", "ave", "dr", "ln", "ct", "blvd", "hwy"}:
            return False
    return True


def get_ner_tactical_summary(
    events_db: Optional[Session],
    start_date: date,
    end_date: date,
    limit: int = 50
) -> Dict[str, Any]:
    """Aggregate top detected entities across categories from EntityObservation."""
    start = datetime.combine(start_date, datetime.min.time())
    end = datetime.combine(end_date, datetime.max.time())

    all_candidates: List[Dict[str, Any]] = []
    total_detected = 0

    if events_db:
        try:
            total_detected = int(
                events_db.query(func.count(EntityObservation.id)).filter(
                    EntityObservation.ts >= start,
                    EntityObservation.ts <= end,
                    EntityObservation.label.in_(_TACTICAL_NER_LABELS),
                ).scalar() or 0
            )

            rows = events_db.query(
                EntityObservation.canonical,
                EntityObservation.label,
                func.count(EntityObservation.id).label("freq"),
                func.min(EntityObservation.ts).label("first_seen"),
                func.max(EntityObservation.ts).label("last_seen"),
                func.max(EntityObservation.log_entry_id).label("sample_tx_id"),
            ).filter(
                EntityObservation.ts >= start,
                EntityObservation.ts <= end,
                EntityObservation.label.in_(_TACTICAL_NER_LABELS),
            ).group_by(
                EntityObservation.canonical,
                EntityObservation.label
            ).order_by(
                func.count(EntityObservation.id).desc()
            ).limit(max(limit * 5, 250)).all()

            for r in rows:
                if not r.canonical or not str(r.canonical).strip():
                    continue
                canon = str(r.canonical).strip()
                lbl = str(r.label).upper() if r.label else "UNKNOWN"
                if not _is_valid_ner_entity(canon, lbl):
                    continue
                all_candidates.append({
                    "canonical": canon,
                    "label": lbl,
                    "freq": int(r.freq),
                    "first_seen": r.first_seen.isoformat() if r.first_seen else None,
                    "last_seen": r.last_seen.isoformat() if r.last_seen else None,
                    "sample_tx_id": int(r.sample_tx_id) if r.sample_tx_id else None,
                })
        except Exception as exc:
            logger.warning("Failed querying entity observations: %s", exc, exc_info=True)

    if all_candidates:
        units = [it for it in all_candidates if it["label"] == "UNIT"][:limit]
        call_types = [it for it in all_candidates if it["label"] == "EVT_TYPE"][:limit]
        locations = [it for it in all_candidates if it["label"] in ("LOC", "ADDRESS")][:limit]
        status = [it for it in all_candidates if it["label"] == "STATUS"][:limit]
        top_all = all_candidates[:limit]
        return {
            "all": top_all,
            "units": units,
            "call_types": call_types,
            "locations": locations,
            "status": status,
            "total_entities_detected": max(total_detected, sum(it["freq"] for it in top_all)),
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
    h_end = datetime.combine(target_date, time(hour, 59, 59, 999999))

    tg_rows = db.query(
        LogEntry.talkgroup,
        func.count(LogEntry.id).label('cnt')
    ).filter(
        LogEntry.timestamp >= h_start,
        LogEntry.timestamp <= h_end,
        _not_deleted(),
    ).group_by(
        LogEntry.talkgroup
    ).order_by(
        func.count(LogEntry.id).desc()
    ).all()

    hour_total = max(1, sum(int(r.cnt) for r in tg_rows))

    drivers = [
        {
            "talkgroup": r.talkgroup or "Unknown",
            "count": int(r.cnt),
            "percentage": round((int(r.cnt) / hour_total) * 100, 1),
        }
        for r in tg_rows[:limit]
    ]

    likely_incident: Optional[str] = None
    if events_db is not None:
        try:
            span_rows = (
                events_db.query(SpanStore.evt_type)
                .join(LogEntry, LogEntry.id == SpanStore.log_entry_id)
                .filter(
                    LogEntry.timestamp >= h_start,
                    LogEntry.timestamp <= h_end,
                    _not_deleted(),
                    SpanStore.evt_type.isnot(None),
                )
                .all()
            )
            counter: Counter = Counter()
            for (evt_type,) in span_rows:
                for item in str(evt_type).split(","):
                    cleaned = _clean_incident_type(item)
                    if cleaned:
                        counter[cleaned] += 1
            if counter:
                likely_incident = counter.most_common(1)[0][0]
        except SQLAlchemyError as exc:
            logger.warning("Failed to derive likely incident for hour %s: %s", hour, exc, exc_info=True)

    return drivers, likely_incident


def _compute_diurnal_baseline_stats(
    db: Session,
    anchor_date: date,
    fallback_hourly_avg: float,
) -> Dict[Tuple[int, int], Tuple[int, float]]:
    """
    Compute diurnal (dow, hour) -> (baseline_mean, regularized_sigma) from the trailing 21-day window.
    Uses empirical day-to-day mean and standard deviation across active historical days, blending
    same-weekday and all-day diurnal profiles, with an overdispersed variance floor.
    """
    trailing_start = anchor_date - timedelta(days=21)
    start_dt = datetime.combine(trailing_start, datetime.min.time())
    end_dt = datetime.combine(anchor_date, datetime.min.time())

    hist_rows = db.query(
        func.date(LogEntry.timestamp).label("day_str"),
        extract("hour", LogEntry.timestamp).label("hour"),
        func.count(LogEntry.id).label("cnt"),
    ).filter(
        LogEntry.timestamp >= start_dt,
        LogEntry.timestamp < end_dt,
        _not_deleted(),
    ).group_by(
        func.date(LogEntry.timestamp),
        extract("hour", LogEntry.timestamp),
    ).all()

    day_totals: Dict[str, int] = defaultdict(int)
    day_hour_counts: Dict[Tuple[str, int], int] = {}
    day_dow_map: Dict[str, int] = {}

    for r in hist_rows:
        if r.day_str is None or r.hour is None:
            continue
        d_str = str(r.day_str)[:10]
        h = int(r.hour)
        cnt = int(r.cnt or 0)
        day_totals[d_str] += cnt
        day_hour_counts[(d_str, h)] = cnt
        if d_str not in day_dow_map:
            try:
                d_obj = datetime.strptime(d_str, "%Y-%m-%d").date()
                day_dow_map[d_str] = (d_obj.weekday() + 1) % 7
            except ValueError:
                pass

    # Exclude partial/offline days (< 24 total calls) when substantial active days exist
    substantial_days = [d for d, tot in day_totals.items() if tot >= 24]
    active_days = substantial_days if substantial_days else list(day_totals.keys())

    default_base = max(4, int(round(fallback_hourly_avg)))
    default_sigma = max(2.5, math.sqrt(default_base), 0.25 * default_base)

    stats_lookup: Dict[Tuple[int, int], Tuple[int, float]] = {}
    if not active_days:
        for dow in range(7):
            for h in range(24):
                stats_lookup[(dow, h)] = (default_base, default_sigma)
        return stats_lookup

    for h in range(24):
        all_vals = [day_hour_counts.get((d_str, h), 0) for d_str in active_days]
        mean_all = sum(all_vals) / len(all_vals)
        if len(all_vals) >= 2:
            var_all = sum((v - mean_all) ** 2 for v in all_vals) / len(all_vals)
            emp_sigma = math.sqrt(var_all)
        else:
            emp_sigma = 0.0

        for dow in range(7):
            dow_vals = [
                day_hour_counts.get((d_str, h), 0)
                for d_str in active_days
                if day_dow_map.get(d_str) == dow
            ]
            if len(dow_vals) >= 2:
                mean_dow = sum(dow_vals) / len(dow_vals)
                blended_mu = 0.5 * mean_dow + 0.5 * mean_all
            elif len(dow_vals) == 1 and len(active_days) >= 3:
                blended_mu = 0.3 * dow_vals[0] + 0.7 * mean_all
            elif len(dow_vals) == 1:
                blended_mu = float(dow_vals[0])
            else:
                blended_mu = mean_all

            base = max(4, int(round(blended_mu))) if blended_mu > 0 else default_base
            sigma = max(emp_sigma, math.sqrt(base), 0.25 * base, 2.5)
            stats_lookup[(dow, h)] = (base, sigma)

    return stats_lookup


def _robust_intraday_baseline(hourly_counts: List[int], num_days: int = 1) -> float:
    """Estimate background hourly rate from non-outlier hours when no trailing history exists."""
    total = sum(hourly_counts)
    if total <= 0:
        return 4.0
    total_slots = max(1, num_days * 24)
    if len(hourly_counts) >= 4:
        sorted_vals = sorted(hourly_counts)
        trim_k = max(1, len(sorted_vals) // 8)
        trimmed = sorted_vals[:-trim_k]
        padded_sum = sum(trimmed)
        padded_slots = max(1, total_slots - trim_k)
        return max(4.0, (padded_sum / padded_slots) * 0.85)
    return max(4.0, (total / total_slots) * 0.8)


def get_traffic_anomaly_telemetry(
    db: Session,
    target_date: date,
    end_date: Optional[date] = None,
    events_db: Optional[Session] = None,
) -> Dict[str, Any]:
    """Calculate radio traffic anomaly and surge metrics comparing volume against diurnal baseline."""
    if end_date is not None and end_date > target_date:
        num_days = (end_date - target_date).days + 1
        start = datetime.combine(target_date, datetime.min.time())
        end = datetime.combine(end_date, datetime.max.time())

        range_hourly_rows = db.query(
            func.date(LogEntry.timestamp).label('day'),
            extract('hour', LogEntry.timestamp).label('hour'),
            func.count(LogEntry.id).label('cnt'),
        ).filter(
            LogEntry.timestamp >= start,
            LogEntry.timestamp <= end,
            _not_deleted(),
        ).group_by(
            func.date(LogEntry.timestamp),
            extract('hour', LogEntry.timestamp),
        ).all()

        total_observed = sum(int(r.cnt or 0) for r in range_hourly_rows)

        if total_observed == 0:
            return {
                "current_hour_label": f"{num_days}-Day Span",
                "observed": 0,
                "baseline": 0,
                "surge_percentage": 0.0,
                "z_score": 0.0,
                "severity": "normal",
                "status_label": "No traffic recorded",
                "primary_driver": "",
                "drivers": [],
                "timeline": [],
                "recent_anomalies": [],
                "insufficient_data": True,
                "is_multi_day": True,
                "range_days": num_days,
            }

        fallback_avg = _robust_intraday_baseline([int(r.cnt) for r in range_hourly_rows], num_days=num_days)
        stats_lookup = _compute_diurnal_baseline_stats(db, target_date, fallback_avg)
        default_base = max(4, int(round(fallback_avg)))
        default_sigma = max(2.5, math.sqrt(default_base), 0.25 * default_base)

        candidate_anomalies: List[Tuple[date, str, int, int, int, float]] = []
        for r in range_hourly_rows:
            d_str = str(r.day)[:10]
            h = int(r.hour)
            cnt = int(r.cnt)
            try:
                d_obj = datetime.strptime(d_str, "%Y-%m-%d").date()
            except ValueError:
                d_obj = target_date
            dow = (d_obj.weekday() + 1) % 7
            base, sigma = stats_lookup.get((dow, h), (default_base, default_sigma))
            z_score = round((cnt - base) / sigma, 2)
            upper_bound = round(base + 2.0 * sigma, 1)
            is_anomaly = cnt >= upper_bound and z_score >= 2.0 and cnt >= 8
            if is_anomaly:
                candidate_anomalies.append((d_obj, d_str, h, cnt, base, z_score))

        candidate_anomalies.sort(key=lambda item: item[5], reverse=True)

        anomalies: List[Dict[str, Any]] = []
        top_drivers: List[Dict[str, Any]] = []
        for idx, (d_obj, d_str, h, cnt, base, z_score) in enumerate(candidate_anomalies[:30]):
            hour_drivers, likely_incident = _hour_drivers_and_incident(
                db, events_db, d_obj, h, limit=3 if idx == 0 else 1
            )
            if idx == 0:
                top_drivers = hour_drivers
            anomalies.append({
                "date": d_str,
                "hour": h,
                "time_window": f"{d_obj.strftime('%b %d')} {hour_clock_label(h)} – {hour_clock_label((h + 1) % 24)}",
                "z_score": z_score,
                "observed": cnt,
                "baseline": base,
                "primary_driver": hour_drivers[0]["talkgroup"] if hour_drivers else "Unknown",
                "likely_incident": likely_incident,
            })

        if anomalies:
            top = anomalies[0]
            focus_label = top["time_window"]
            obs = top["observed"]
            base = top["baseline"]
            z = top["z_score"]
            surge_pct = round(((obs - base) / max(1, base)) * 100, 1)
            primary_driver = top["primary_driver"]
            drivers = top_drivers
            if z >= 3.0:
                severity = "critical"
                status_label = f"Critical Surge ({z:+.1f}σ)"
            elif z >= 2.0:
                severity = "high"
                status_label = f"High Surge Alert ({z:+.1f}σ)"
            elif z >= 1.0:
                severity = "elevated"
                status_label = f"Elevated Traffic ({z:+.1f}σ)"
            else:
                severity = "normal"
                status_label = f"Nominal Flow ({z:+.1f}σ)"
        else:
            # Find highest z-score hour across the range for summary context
            best_row = None
            best_z = -999.0
            best_base = default_base
            best_d_obj = target_date
            for r in range_hourly_rows:
                d_str = str(r.day)[:10]
                h = int(r.hour)
                cnt = int(r.cnt)
                try:
                    d_obj = datetime.strptime(d_str, "%Y-%m-%d").date()
                except ValueError:
                    d_obj = target_date
                dow = (d_obj.weekday() + 1) % 7
                b_val, sig_val = stats_lookup.get((dow, h), (default_base, default_sigma))
                z_val = round((cnt - b_val) / sig_val, 2)
                if z_val > best_z:
                    best_z = z_val
                    best_row = (d_obj, h, cnt)
                    best_base = b_val
                    best_d_obj = d_obj

            if best_row is not None:
                d_obj, h, obs = best_row
                base = best_base
                z = best_z
                surge_pct = round(((obs - base) / max(1, base)) * 100, 1)
                focus_label = f"{d_obj.strftime('%b %d')} {hour_label(h)}"
                drivers, _ = _hour_drivers_and_incident(db, events_db, best_d_obj, h, limit=3)
                primary_driver = drivers[0]["talkgroup"] if drivers else ""
            else:
                focus_label = f"{num_days}-Day Span"
                obs = total_observed
                base = total_observed
                z = 0.0
                surge_pct = 0.0
                primary_driver = ""
                drivers = []

            if z >= 1.0:
                severity = "elevated"
                status_label = f"Elevated Traffic ({z:+.1f}σ)"
            else:
                severity = "normal"
                status_label = f"Nominal Flow ({num_days} Days)"

        return {
            "current_hour_label": focus_label,
            "observed": obs,
            "baseline": base,
            "surge_percentage": surge_pct,
            "z_score": z,
            "severity": severity,
            "status_label": status_label,
            "primary_driver": primary_driver,
            "drivers": drivers,
            "timeline": [],
            "recent_anomalies": anomalies,
            "insufficient_data": total_observed < 25,
            "is_multi_day": True,
            "range_days": num_days,
        }

    # Single-day calculation
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())

    # Batch-fetch (hour, talkgroup, count) in a single query for the entire day
    tg_hourly_rows = db.query(
        extract('hour', LogEntry.timestamp).label('hour'),
        LogEntry.talkgroup,
        func.count(LogEntry.id).label('cnt'),
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        _not_deleted(),
    ).group_by(
        extract('hour', LogEntry.timestamp),
        LogEntry.talkgroup,
    ).all()

    observed_map: Dict[int, int] = defaultdict(int)
    hour_tg_counts: Dict[int, List[Tuple[str, int]]] = defaultdict(list)
    for r in tg_hourly_rows:
        if r.hour is None:
            continue
        h = int(r.hour)
        cnt = int(r.cnt or 0)
        observed_map[h] += cnt
        hour_tg_counts[h].append((r.talkgroup or "Unknown", cnt))

    for h in hour_tg_counts:
        hour_tg_counts[h].sort(key=lambda x: x[1], reverse=True)

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
            "is_multi_day": False,
            "range_days": 1,
        }

    dow = (target_date.weekday() + 1) % 7
    fallback_avg = _robust_intraday_baseline(list(observed_map.values()), num_days=1)
    stats_lookup = _compute_diurnal_baseline_stats(db, target_date, fallback_avg)
    default_base = max(4, int(round(fallback_avg)))
    default_sigma = max(2.5, math.sqrt(default_base), 0.25 * default_base)

    now_local = datetime.now()
    is_today = target_date == now_local.date()
    cur_h = min(23, max(0, now_local.hour))
    cur_min_fraction = max(0.1, (now_local.minute + now_local.second / 60.0) / 60.0)

    timeline = []
    anomalies = []
    peak_hour = 0
    peak_z = -999.0

    for h in range(24):
        obs = observed_map.get(h, 0)
        base, sigma = stats_lookup.get((dow, h), (default_base, default_sigma))
        upper_bound = round(base + 2.0 * sigma, 1)

        if is_today and h > cur_h and obs == 0:
            # Future hours on today have not occurred yet
            z_score = 0.0
            is_anomaly = False
        elif is_today and h == cur_h and cur_min_fraction < 0.85 and obs < base:
            # Pro-rate baseline when comparing an incomplete in-progress hour against below-full-hour count
            eff_base = max(1.0, base * cur_min_fraction)
            eff_sigma = max(2.0, sigma * math.sqrt(cur_min_fraction))
            z_score = round((obs - eff_base) / eff_sigma, 2)
            is_anomaly = False
        else:
            z_score = round((obs - base) / sigma, 2)
            is_anomaly = obs >= upper_bound and z_score >= 2.0 and obs >= 8

        # Track peak hour among hours that have occurred (or have traffic)
        if not (is_today and h > cur_h and obs == 0):
            if z_score > peak_z or (z_score == peak_z and obs > observed_map.get(peak_hour, 0)):
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
            tg_list = hour_tg_counts.get(h, [])
            primary_tg = tg_list[0][0] if tg_list else "Unknown"
            _, likely_incident = _hour_drivers_and_incident(db, events_db, target_date, h, limit=1)
            anomalies.append({
                "date": target_date.isoformat(),
                "hour": h,
                "time_window": f"{hour_clock_label(h)} – {hour_clock_label((h + 1) % 24)}",
                "z_score": z_score,
                "observed": obs,
                "baseline": base,
                "primary_driver": primary_tg,
                "likely_incident": likely_incident,
            })

    if timeline[peak_hour]["z_score"] >= 1.5 or not is_today:
        focus_h = peak_hour
    else:
        # On today with nominal flow, prefer current hour if sufficiently underway, else previous hour
        if cur_min_fraction >= 0.25 or cur_h == 0 or observed_map.get(cur_h, 0) >= timeline[cur_h]["baseline"] * 0.5:
            focus_h = cur_h
        else:
            focus_h = cur_h - 1

    focus_pt = timeline[focus_h]
    focus_total = max(1, focus_pt["observed"])
    drivers = [
        {
            "talkgroup": tg_name,
            "count": cnt,
            "percentage": round((cnt / focus_total) * 100, 1),
        }
        for tg_name, cnt in hour_tg_counts.get(focus_h, [])[:3]
    ]
    primary_driver = drivers[0]["talkgroup"] if drivers else ""
    z = focus_pt["z_score"]
    if is_today and focus_h == cur_h and cur_min_fraction < 0.85 and focus_pt["observed"] < focus_pt["baseline"]:
        eff_base = max(1.0, focus_pt["baseline"] * cur_min_fraction)
        surge_pct = round(((focus_pt["observed"] - eff_base) / eff_base) * 100, 1)
    else:
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
        "is_multi_day": False,
        "range_days": 1,
    }


def get_asr_quality_spectrum(db: Session, start_date: date, end_date: date) -> Dict[str, Any]:
    """Calculate Whisper ASR confidence and signal fidelity breakdown across quality tiers."""
    start = datetime.combine(start_date, datetime.min.time())
    end = datetime.combine(end_date, datetime.max.time())

    norm_score = case(
        (LogEntry.confidence <= 1.0, LogEntry.confidence * 100.0),
        else_=LogEntry.confidence,
    )

    agg = db.query(
        func.count(LogEntry.id).label("total"),
        func.sum(case((norm_score >= 85.0, 1), else_=0)).label("high"),
        func.sum(case((and_(norm_score >= 70.0, norm_score < 85.0), 1), else_=0)).label("moderate"),
        func.sum(case((norm_score < 70.0, 1), else_=0)).label("low"),
        func.avg(norm_score).label("mean_conf"),
    ).filter(
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
        _not_deleted(),
        _valid_speech(),
        LogEntry.confidence.isnot(None),
        LogEntry.confidence > 0,
    ).first()

    total = int(agg.total or 0) if agg else 0
    if total > 0:
        high = int(agg.high or 0)
        moderate = int(agg.moderate or 0)
        low = int(agg.low or 0)
        mean_conf = round(float(agg.mean_conf or 0.0), 1)

        high_pct = round((high / total) * 100.0, 1)
        mod_pct = round((moderate / total) * 100.0, 1)
        low_pct = round((low / total) * 100.0, 1)

        # Ensure rounded percentages sum cleanly to 100.0%
        residual = round(100.0 - (high_pct + mod_pct + low_pct), 1)
        if residual != 0.0:
            if high >= moderate and high >= low:
                high_pct = round(high_pct + residual, 1)
            elif moderate >= high and moderate >= low:
                mod_pct = round(mod_pct + residual, 1)
            else:
                low_pct = round(low_pct + residual, 1)

        return {
            "high_count": high,
            "high_percentage": high_pct,
            "moderate_count": moderate,
            "moderate_percentage": mod_pct,
            "low_count": low,
            "low_percentage": low_pct,
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

    is_today = (num_days == 1 and start_date == datetime.now().date())
    if is_today:
        calls_last_minute = get_last_full_minute_transcription_count(db)
        summary["calls_last_minute"] = calls_last_minute
        summary["calls_per_minute_window"] = 1
        summary["trends"] = get_summary_trends(
            db,
            calls_last_minute,
            today_unique_talkgroups=summary.get("unique_talkgroups"),
        )
        summary["is_multi_day"] = False
        summary["range_days"] = 1
    elif num_days > 1:
        # Multi-day range: null out live real-time metrics
        summary["calls_last_minute"] = None
        summary["calls_per_minute_window"] = None
        summary["trends"] = None
        summary["is_multi_day"] = True
        summary["range_days"] = num_days
    else:
        # Single historical day
        summary["calls_last_minute"] = None
        summary["calls_per_minute_window"] = None
        summary["trends"] = None
        summary["is_multi_day"] = False
        summary["range_days"] = 1

    heatmap = get_diurnal_heatmap(db, start_date, end_date)
    rtf_telemetry = get_rtf_telemetry(db, start_date, end_date)
    ner_summary = get_ner_tactical_summary(events_db or db, start_date, end_date)
    traffic_anomaly = get_traffic_anomaly_telemetry(
        db,
        start_date,
        end_date=end_date if num_days > 1 else None,
        events_db=events_db or db,
    )
    asr_quality = get_asr_quality_spectrum(db, start_date, end_date)
    tracker_telemetry = get_talkgroup_tracker_telemetry(db, start_date, end_date)

    return {
        "summary": summary,
        "activity": activity,
        "talkgroups": tracker_telemetry["ranked_talkgroups"],
        "talkgroups_all": all_talkgroups,
        "talkgroup_tracker": tracker_telemetry,
        "recent": recent,
        "heatmap": heatmap,
        "rtf": rtf_telemetry,
        "ner": ner_summary,
        "anomaly": traffic_anomaly,
        "asr_quality": asr_quality,
    }

