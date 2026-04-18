"""Background worker to auto-generate hour summaries."""
import asyncio
import logging
from datetime import datetime, date, timedelta, time
from typing import Set

from sqlalchemy import extract

from ..config import get_settings
from ..database import LogsSessionLocal
from ..models.log_entry import LogEntry
from ..models.hour_summary import HourSummary
from .summarization import generate_hour_summary

logger = logging.getLogger(__name__)

_auto_task = None


def _hours_with_logs(db, target_date: date) -> Set[int]:
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())
    rows = (
        db.query(extract("hour", LogEntry.timestamp).label("hour"))
        .filter(
            LogEntry.timestamp >= start,
            LogEntry.timestamp <= end,
            LogEntry.is_deleted == False,
        )
        .group_by(extract("hour", LogEntry.timestamp))
        .all()
    )
    return {int(r.hour) for r in rows}


def _hours_with_summaries(db, date_str: str) -> Set[int]:
    rows = db.query(HourSummary.summary_hour).filter(HourSummary.summary_date == date_str).all()
    return {int(r[0]) for r in rows}


async def _auto_summary_loop() -> None:
    settings = get_settings()
    cfg = settings.config.summaries
    interval = max(60, int(cfg.auto_generate_interval_seconds or 300))
    lookback_days = max(1, int(cfg.auto_generate_days or 1))

    logger.info(
        "✅ Auto summaries enabled: interval=%ss, lookback_days=%s",
        interval,
        lookback_days,
    )

    while True:
        try:
            today = datetime.utcnow().date()
            now_hour = datetime.utcnow().hour

            db = LogsSessionLocal()
            try:
                for offset in range(lookback_days):
                    target_date = today - timedelta(days=offset)
                    date_str = target_date.isoformat()

                    hours_logs = _hours_with_logs(db, target_date)
                    if not hours_logs:
                        continue

                    hours_have = _hours_with_summaries(db, date_str)
                    pending = sorted(hours_logs - hours_have)
                    if not pending:
                        continue

                    # Avoid summarizing the current (still active) hour for today
                    if target_date == today:
                        pending = [h for h in pending if h < now_hour]

                    for hour in pending:
                        start = datetime.combine(target_date, time(hour, 0, 0))
                        end = datetime.combine(target_date, time(hour, 59, 59))
                        rows = (
                            db.query(LogEntry)
                            .filter(
                                LogEntry.timestamp >= start,
                                LogEntry.timestamp <= end,
                                LogEntry.is_deleted == False,
                            )
                            .order_by(LogEntry.timestamp.asc())
                            .all()
                        )
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
                        if not entries:
                            continue

                        try:
                            result = generate_hour_summary(entries, date_str=date_str, hour=hour)
                            text = result["summary"]
                        except Exception as e:
                            logger.warning(
                                "Auto summary generation failed for %s hour=%s: %s",
                                date_str,
                                hour,
                                e,
                            )
                            continue

                        existing = (
                            db.query(HourSummary)
                            .filter(
                                HourSummary.summary_date == date_str,
                                HourSummary.summary_hour == hour,
                            )
                            .first()
                        )
                        if existing:
                            continue

                        created = HourSummary(
                            summary_date=date_str,
                            summary_hour=hour,
                            summary_text=text,
                            created_by="auto",
                        )
                        db.add(created)
                        db.commit()
                        logger.info("✅ Auto summary created for %s hour=%s", date_str, hour)
            finally:
                db.close()
        except Exception as e:
            logger.warning("Auto summaries loop error: %s", e)

        await asyncio.sleep(interval)


async def start_auto_summary_worker() -> None:
    """Start background auto-summary loop if enabled."""
    settings = get_settings()
    cfg = settings.config.summaries
    if not cfg.auto_generate_enabled:
        return

    global _auto_task
    if _auto_task and not _auto_task.done():
        return

    loop = asyncio.get_running_loop()
    _auto_task = loop.create_task(_auto_summary_loop())


async def stop_auto_summary_worker() -> None:
    """Stop background auto-summary loop if running."""
    global _auto_task
    if _auto_task and not _auto_task.done():
        _auto_task.cancel()
        _auto_task = None

