"""Maintenance routes for database cleanup and stats."""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_logs_db
from ..models.event import EntityObservation, Event, Monitor, SpanStore, SystemSetting
from ..models.log_entry import LogEntry
from ..models.user import User
from ..schemas.maintenance import (
    DailyVolumePoint,
    DatabaseOverviewResponse,
    DatabaseStatsResponse,
    EntityLabelStat,
    NerOverviewStats,
    PurgeResponse,
    RedactSsnResponse,
    RetentionConfigResponse,
    StorageHealthStats,
    TableInventoryItem,
    TalkgroupVolumeItem,
)
from ..services.events_worker import is_events_pipeline_active
from ..services.ner_service import is_loaded as is_ner_loaded
from ..services.redaction_service import scrub_database_ssn
from ..services.retention import run_retention
from ..utils.audio_paths import NOT_SAVED
from .auth import get_current_active_user, get_current_admin_user

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])
logger = logging.getLogger(__name__)
settings = get_settings()


@router.get("/retention-config", response_model=RetentionConfigResponse)
def get_retention_config(
    current_user: User = Depends(get_current_active_user)
) -> RetentionConfigResponse:
    """Return retention_days and cleanup_hour from config for manual cleanup UI."""
    s = get_settings()
    return RetentionConfigResponse(
        retention_days=s.config.storage.retention_days,
        cleanup_hour=s.config.storage.cleanup_hour,
    )


class PurgeRequest(BaseModel):
    """Request to purge old data."""
    retention_days: int


@router.get("/stats", response_model=DatabaseStatsResponse)
def get_database_stats(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db)
) -> DatabaseStatsResponse:
    """Get database statistics. Runs in threadpool to prevent blocking the event loop."""
    # Get oldest and newest entries
    oldest = db.query(LogEntry.log_date).filter(LogEntry.log_date.isnot(None)).order_by(LogEntry.log_date.asc()).first()
    newest = db.query(LogEntry.log_date).filter(LogEntry.log_date.isnot(None)).order_by(LogEntry.log_date.desc()).first()
    total = db.query(func.count(LogEntry.id)).scalar()
    
    # Calculate days of data
    days_of_data = 0
    if oldest and newest and oldest[0] and newest[0]:
        try:
            oldest_date = datetime.strptime(oldest[0], '%Y-%m-%d')
            newest_date = datetime.strptime(newest[0], '%Y-%m-%d')
            days_of_data = (newest_date - oldest_date).days + 1
        except (ValueError, TypeError):
            pass
    
    return DatabaseStatsResponse(
        total_entries=total or 0,
        oldest_date=oldest[0] if oldest else None,
        newest_date=newest[0] if newest else None,
        days_of_data=days_of_data
    )


def _safe_file_size(path: Path) -> int:
    """Return file size in bytes or 0 if missing/unreadable."""
    try:
        return int(os.stat(path).st_size)
    except OSError:
        return 0


def _fmt_boundary(val: object) -> Optional[str]:
    """Normalize a SQLite min/max timestamp or date scalar to ISO string."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


@router.get("/overview", response_model=DatabaseOverviewResponse)
def get_database_overview(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_logs_db),
) -> DatabaseOverviewResponse:
    """Return aggregated telemetry for the Database Explorer Overview dashboard (admin only)."""
    s = get_settings()
    active_filter = LogEntry.is_deleted.is_not(True)

    # 1. SQLite file + PRAGMA metrics (no directory walks)
    db_file = Path(s.db_path)
    db_bytes = _safe_file_size(db_file)
    wal_bytes = _safe_file_size(Path(f"{s.db_path}-wal"))
    shm_bytes = _safe_file_size(Path(f"{s.db_path}-shm"))

    journal_mode = "unknown"
    page_size = 0
    page_count = 0
    freelist_count = 0
    try:
        jm = db.execute(text("PRAGMA journal_mode")).scalar()
        journal_mode = str(jm).lower() if jm is not None else "unknown"
        page_size = int(db.execute(text("PRAGMA page_size")).scalar() or 0)
        page_count = int(db.execute(text("PRAGMA page_count")).scalar() or 0)
        freelist_count = int(db.execute(text("PRAGMA freelist_count")).scalar() or 0)
    except SQLAlchemyError as exc:
        logger.warning("Failed reading SQLite PRAGMA stats: %s", exc)

    layout_row = (
        db.query(SystemSetting.value)
        .filter(SystemSetting.key == "audio_layout")
        .first()
    )
    audio_layout = str(layout_row[0]) if layout_row and layout_row[0] else "sharded"

    audio_agg = (
        db.query(
            func.count(LogEntry.id),
            func.coalesce(func.sum(LogEntry.file_size), 0),
        )
        .filter(
            active_filter,
            LogEntry.audio_path.isnot(None),
            LogEntry.audio_path != "",
            LogEntry.audio_path != NOT_SAVED,
        )
        .first()
    )
    audio_files_count = int(audio_agg[0] or 0) if audio_agg else 0
    audio_bytes = int(audio_agg[1] or 0) if audio_agg else 0

    storage = StorageHealthStats(
        db_bytes=db_bytes,
        wal_bytes=wal_bytes,
        shm_bytes=shm_bytes,
        total_sqlite_bytes=db_bytes + wal_bytes + shm_bytes,
        journal_mode=journal_mode,
        page_size=page_size,
        page_count=page_count,
        freelist_count=freelist_count,
        reclaimable_bytes=page_size * freelist_count,
        audio_files_count=audio_files_count,
        audio_bytes=audio_bytes,
        audio_layout=audio_layout,
        retention_days=int(getattr(s.config.storage, "retention_days", 0) or 0),
    )

    # 2. Table inventory metrics
    logs_agg = (
        db.query(
            func.count(LogEntry.id),
            func.min(LogEntry.log_date),
            func.max(LogEntry.log_date),
            func.coalesce(func.sum(LogEntry.duration), 0.0),
        )
        .filter(active_filter)
        .first()
    )
    total_logs = int(logs_agg[0] or 0) if logs_agg else 0
    logs_oldest = _fmt_boundary(logs_agg[1]) if logs_agg else None
    logs_newest = _fmt_boundary(logs_agg[2]) if logs_agg else None
    total_duration = float(logs_agg[3] or 0.0) if logs_agg else 0.0

    reviewed_count = int(
        db.query(func.count(LogEntry.id))
        .filter(active_filter, LogEntry.is_reviewed == True)
        .scalar()
        or 0
    )

    spans_agg = db.query(
        func.count(SpanStore.id),
        func.count(func.distinct(SpanStore.log_entry_id)),
        func.min(SpanStore.created_at),
        func.max(SpanStore.created_at),
    ).first()
    total_spans = int(spans_agg[0] or 0) if spans_agg else 0
    covered_logs = int(spans_agg[1] or 0) if spans_agg else 0
    spans_oldest = _fmt_boundary(spans_agg[2]) if spans_agg else None
    spans_newest = _fmt_boundary(spans_agg[3]) if spans_agg else None

    obs_agg = db.query(
        func.count(EntityObservation.id),
        func.count(func.distinct(EntityObservation.raw)),
        func.min(EntityObservation.ts),
        func.max(EntityObservation.ts),
    ).first()
    total_obs = int(obs_agg[0] or 0) if obs_agg else 0
    unique_obs_raw = int(obs_agg[1] or 0) if obs_agg else 0
    obs_oldest = _fmt_boundary(obs_agg[2]) if obs_agg else None
    obs_newest = _fmt_boundary(obs_agg[3]) if obs_agg else None

    events_agg = db.query(
        func.count(Event.id),
        func.min(Event.created_at),
        func.max(Event.created_at),
    ).first()
    total_events = int(events_agg[0] or 0) if events_agg else 0
    events_oldest = _fmt_boundary(events_agg[1]) if events_agg else None
    events_newest = _fmt_boundary(events_agg[2]) if events_agg else None
    open_events = int(
        db.query(func.count(Event.id)).filter(Event.status == "open").scalar() or 0
    )

    total_monitors = int(db.query(func.count(Monitor.id)).scalar() or 0)
    enabled_monitors = int(
        db.query(func.count(Monitor.id)).filter(Monitor.enabled == True).scalar() or 0
    )

    tables: List[TableInventoryItem] = [
        TableInventoryItem(
            key="logs",
            label="Transmissions",
            route="/data/logs",
            row_count=total_logs,
            secondary_label="Reviewed",
            secondary_value=f"{reviewed_count:,}",
            oldest=logs_oldest,
            newest=logs_newest,
        ),
        TableInventoryItem(
            key="spans",
            label="Span Store",
            route="/data/spans",
            row_count=total_spans,
            secondary_label="Unique logs",
            secondary_value=f"{covered_logs:,}",
            oldest=spans_oldest,
            newest=spans_newest,
        ),
        TableInventoryItem(
            key="entities",
            label="NER Entity Observations",
            route="/data/entities",
            row_count=total_obs,
            secondary_label="Unique values",
            secondary_value=f"{unique_obs_raw:,}",
            oldest=obs_oldest,
            newest=obs_newest,
        ),
        TableInventoryItem(
            key="events",
            label="Events",
            route="/data/events",
            row_count=total_events,
            secondary_label="Open",
            secondary_value=f"{open_events:,}",
            oldest=events_oldest,
            newest=events_newest,
        ),
        TableInventoryItem(
            key="dataset",
            label="Fine-Tuning Dataset",
            route="/data/dataset",
            row_count=reviewed_count,
            secondary_label="Share of logs",
            secondary_value=(
                f"{(reviewed_count / total_logs * 100):.1f}%" if total_logs > 0 else "0.0%"
            ),
            oldest=logs_oldest,
            newest=logs_newest,
        ),
        TableInventoryItem(
            key="monitors",
            label="Monitors",
            route="/events/monitors",
            row_count=total_monitors,
            secondary_label="Enabled",
            secondary_value=f"{enabled_monitors:,}",
        ),
    ]

    # 3. NER breakdown & coverage
    label_rows = (
        db.query(
            EntityObservation.label,
            func.count(EntityObservation.id),
            func.count(func.distinct(EntityObservation.raw)),
        )
        .group_by(EntityObservation.label)
        .order_by(func.count(EntityObservation.id).desc())
        .all()
    )
    label_stats: List[EntityLabelStat] = []
    for lbl, cnt, uniq in label_rows:
        c = int(cnt or 0)
        label_stats.append(
            EntityLabelStat(
                label=str(lbl),
                total_count=c,
                unique_raw_count=int(uniq or 0),
                pct_of_total=round((c / total_obs) * 100.0, 1) if total_obs > 0 else 0.0,
            )
        )

    pipe_cfg = getattr(s.config, "events_pipeline", None)
    coverage_pct = min(100.0, round((covered_logs / total_logs) * 100.0, 1)) if total_logs > 0 else 0.0
    ner = NerOverviewStats(
        pipeline_enabled=is_events_pipeline_active(pipe_cfg),
        ner_only=bool(getattr(pipe_cfg, "ner_only", False)) if pipe_cfg else False,
        ner_loaded=is_ner_loaded(),
        ner_model_path=str(getattr(pipe_cfg, "ner_model_path", "") or "") if pipe_cfg else "",
        covered_logs=covered_logs,
        total_logs=total_logs,
        coverage_pct=coverage_pct,
        total_spans=total_spans,
        total_observations=total_obs,
        labels=label_stats,
    )

    # 4. Last 7 days daily volume (local date strings)
    today = datetime.now().date()
    dates_7d = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    vol_rows = (
        db.query(LogEntry.log_date, func.count(LogEntry.id))
        .filter(active_filter, LogEntry.log_date >= dates_7d[0])
        .group_by(LogEntry.log_date)
        .all()
    )
    vol_map = {str(d): int(c or 0) for d, c in vol_rows if d}
    daily_volume = [DailyVolumePoint(date=d, count=vol_map.get(d, 0)) for d in dates_7d]

    # 5. Last 24h volume & top talkgroups (naive local wall time matches LogEntry.timestamp)
    cutoff_24h = datetime.now() - timedelta(hours=24)
    logs_last_24h = int(
        db.query(func.count(LogEntry.id))
        .filter(active_filter, LogEntry.timestamp >= cutoff_24h)
        .scalar()
        or 0
    )
    tg_rows = (
        db.query(
            func.coalesce(LogEntry.talkgroup, "N/A"),
            func.count(LogEntry.id),
            func.coalesce(func.sum(LogEntry.duration), 0.0),
        )
        .filter(active_filter, LogEntry.timestamp >= cutoff_24h)
        .group_by(func.coalesce(LogEntry.talkgroup, "N/A"))
        .order_by(func.count(LogEntry.id).desc())
        .limit(10)
        .all()
    )
    top_talkgroups_24h = [
        TalkgroupVolumeItem(
            talkgroup=str(tg or "N/A"),
            count=int(cnt or 0),
            duration_seconds=round(float(dur or 0.0), 1),
        )
        for tg, cnt, dur in tg_rows
    ]

    return DatabaseOverviewResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        storage=storage,
        tables=tables,
        ner=ner,
        daily_volume=daily_volume,
        top_talkgroups_24h=top_talkgroups_24h,
        logs_last_24h=logs_last_24h,
        total_audio_duration_seconds=round(total_duration, 1),
    )


@router.post("/purge", response_model=PurgeResponse)
def purge_old_data(
    request: PurgeRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db)
) -> PurgeResponse:
    """Purge data older than retention period. Runs in threadpool to avoid event loop stalling."""
    if request.retention_days == 0:
        return PurgeResponse(
            message="Retention set to never delete",
            deleted_count=0,
            audio_files_deleted=0,
            cutoff_date=None
        )
    
    # Delegate to the date-driven retention service. The old implementation walked ORM
    # rows, deleted the row even when the file could not be removed (creating orphans no
    # later run can see), let the FK SET NULL rules blank dependents instead of removing
    # them, and reported counters derived from row count only.
    report = run_retention(request.retention_days, dry_run=False, session=db)

    logger.info(
        "retention purge by %s: transmissions=%d audio=%d (%.1f MB) orphans=%d "
        "span_store=%d observations=%d links=%d events=%d summaries=%d cutoff=%s",
        current_user.username,
        report.log_entries,
        report.audio_files_deleted,
        report.audio_bytes_freed / 1e6,
        report.orphan_files_deleted,
        report.span_store,
        report.entity_observations,
        report.event_links,
        report.events,
        report.hour_summaries,
        report.cutoff_date,
    )

    return PurgeResponse(
        message=(
            f"Purged {report.log_entries} transmissions, {report.events} events and "
            f"{report.hour_summaries} hour summaries older than "
            f"{request.retention_days} days (cutoff {report.cutoff_date})"
        ),
        deleted_count=report.log_entries + report.events + report.hour_summaries,
        audio_files_deleted=report.audio_files_deleted + report.orphan_files_deleted,
        cutoff_date=report.cutoff_date,
    )


class RedactSsnRequest(BaseModel):
    replacement: Optional[str] = None
    dry_run: bool = False


@router.post("/redact-ssn", response_model=RedactSsnResponse)
async def trigger_ssn_redaction(
    request: RedactSsnRequest = RedactSsnRequest(),
    current_user: User = Depends(get_current_active_user),
) -> RedactSsnResponse:
    """Scan and redact historical SSNs from all database tables asynchronously. Admin only."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        stats = await asyncio.to_thread(
            scrub_database_ssn,
            replacement=request.replacement,
            dry_run=request.dry_run
        )
        return RedactSsnResponse(ok=True, stats=stats)
    except Exception as exc:
        logger.exception("SSN scrub failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


