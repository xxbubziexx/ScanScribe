"""Events cleanup: periodic sweeping and auto-closing of stale events."""
import asyncio
from datetime import datetime, timezone
import logging
from zoneinfo import ZoneInfo

from ...config import get_settings
from ...database import EventsSessionLocal, LogsSessionLocal
from ...models.event import Event, EventTranscriptLink
from ...models.log_entry import LogEntry
from ..events_debug import append_ner as debug_append_ner

logger = logging.getLogger(__name__)


def utc_from_log_timestamp(dt: datetime, iana_tz: str) -> datetime:
    """LogEntry.timestamp is naive local wall time from ingest; normalize to UTC."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)
    name = (iana_tz or "").strip()
    if name:
        try:
            tz = ZoneInfo(name)
        except Exception:
            tz = datetime.now().astimezone().tzinfo
    else:
        tz = datetime.now().astimezone().tzinfo
    return dt.replace(tzinfo=tz).astimezone(timezone.utc)


def utc_from_event_created(dt: datetime) -> datetime:
    """Event.created_at defaults to aware UTC; SQLite may round-trip naive UTC."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=timezone.utc)


def auto_close_stale_events(events_db, stale_seconds: int) -> None:
    """Close open events whose last linked log entry timestamp is older than stale_seconds."""
    if stale_seconds <= 0:
        return
    from sqlalchemy import func as sa_func

    pipe = get_settings().config.events_pipeline
    log_tz = str(getattr(pipe, "log_naive_timezone", "") or "")

    now = datetime.now(timezone.utc)
    open_events = events_db.query(Event).filter(Event.status == "open").all()
    if not open_events:
        return

    logs_db = LogsSessionLocal()
    changed = False
    try:
        for ev in open_events:
            log_ids = [
                lid
                for (lid,) in events_db.query(EventTranscriptLink.log_entry_id)
                .filter(
                    EventTranscriptLink.event_id == ev.id,
                    EventTranscriptLink.log_entry_id.isnot(None),
                )
                .all()
            ]
            if log_ids:
                ref_ts = (
                    logs_db.query(sa_func.max(LogEntry.timestamp))
                    .filter(
                        LogEntry.id.in_(log_ids),
                        LogEntry.is_deleted == False,
                    )
                    .scalar()
                )
                if ref_ts is not None:
                    ref_ts = utc_from_log_timestamp(ref_ts, log_tz)
            else:
                ref_ts = None

            if ref_ts is None:
                ca = ev.created_at
                ref_ts = utc_from_event_created(ca) if ca is not None else None
            if ref_ts is None:
                continue
            if (now - ref_ts).total_seconds() >= stale_seconds:
                ev.status = "closed"
                ev.closed_at = now
                changed = True
                logger.info(
                    "Events cleanup: auto-closed stale event_id=%s (last_incident_ts=%s)",
                    ev.event_id,
                    ref_ts.isoformat(),
                )
                debug_append_ner(
                    ev.monitor_id,
                    log_ids[-1] if log_ids else 0,
                    "cleanup_auto_close",
                    ev.event_id,
                    0.0,
                    {},
                    f"auto-closed: last incident ts {ref_ts.isoformat()}, threshold {stale_seconds}s",
                )
    finally:
        logs_db.close()
    if changed:
        events_db.commit()


async def async_cleanup_loop() -> None:
    while True:
        cfg = get_settings().config.events_pipeline
        interval = int(getattr(cfg, "cleanup_interval_seconds", 0) or 0)
        stale = int(getattr(cfg, "auto_close_stale_seconds", 0) or 0)
        sleep_for = interval if interval > 0 else 60
        if cfg.enabled and interval > 0 and stale > 0:
            try:
                db = EventsSessionLocal()
                try:
                    auto_close_stale_events(db, stale)
                finally:
                    db.close()
            except Exception as exc:
                logger.warning("Events cleanup sweep failed: %s", exc)
        await asyncio.sleep(sleep_for)


def start_event_cleanup_worker() -> None:
    """Periodically auto-closes stale events using incident time."""
    try:
        from ..task_manager import task_manager

        task_manager.spawn(async_cleanup_loop(), name="events-cleanup")
    except RuntimeError:
        pass
