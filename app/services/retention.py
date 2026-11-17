"""ScanScribe data retention — full, date-driven purge.

Replaces the per-row purge that previously lived in ``routes/maintenance.py``, which had
four defects:

1. It reported ``deleted_count``/``audio_files_deleted`` derived from ORM rows only, so
   "Removed 0 entries and 0 audio files" was unverifiable against the disk.
2. It resolved audio as ``output_dir / Path(audio_path).name``, throwing away any
   directory component — fine only while ``audio_storage/`` is flat, fatal once sharded.
3. It deleted the DB row even when the audio file could not be removed, silently
   manufacturing orphan files that no later purge can ever see.
4. It never reclaimed SQLite pages, so deleting rows freed nothing.

Retention semantics
-------------------
* A row expires when ``log_entries.log_date < cutoff`` (cutoff = today - retention_days).
* Dependents are removed completely, never nulled. ``span_store.log_entry_id`` and
  ``entity_observations.log_entry_id`` are declared ``ON DELETE SET NULL``, so deleting
  log entries alone would only blank the link; those rows are deleted explicitly.
* ``events`` are purged by ``created_at`` date; events still marked ``open`` are skipped.
* ``hour_summaries`` are purged by ``summary_date``.
* Audio files are removed via the row's recorded path, and orphaned files (on disk with no
  row) older than the cutoff are swept separately.
* ``VACUUM`` is optional, runs outside a transaction, and takes an exclusive lock — never
  invoke it while ingest is active.

NEVER touched (the /intel surface plus application state):
    users, monitors, system_settings, chat_threads, chat_messages, pipeline_debug_log

Usage
-----
    python -m app.services.retention --days 30                 # dry run (default)
    python -m app.services.retention --days 30 --apply         # execute
    python -m app.services.retention --days 30 --apply --vacuum
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Iterator, Optional

from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal, engine

logger = logging.getLogger(__name__)

CHUNK = 500
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac"}

# Tables that must survive every retention run.
PROTECTED_TABLES = (
    "users",
    "monitors",
    "system_settings",
    "chat_threads",
    "chat_messages",
    "pipeline_debug_log",
)


@dataclass
class RetentionReport:
    cutoff_date: str = ""
    dry_run: bool = True
    log_entries: int = 0
    audio_files_deleted: int = 0
    audio_bytes_freed: int = 0
    audio_files_missing: int = 0
    orphan_files_deleted: int = 0
    orphan_bytes_freed: int = 0
    span_store: int = 0
    entity_observations: int = 0
    event_links: int = 0
    events: int = 0
    events_skipped_open: int = 0
    hour_summaries: int = 0
    vacuumed: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- paths
def resolve_audio_file(audio_path: Optional[str], output_dir: Path) -> Optional[Path]:
    """Map a stored ``audio_path`` to an on-disk file.

    Handles every layout in use or planned:
      * ``audio_storage/foo.wav``            -> output_dir/foo.wav
      * ``audio_storage/2026/11/16/foo.wav`` -> output_dir/2026/11/16/foo.wav  (sharded)
      * bare ``foo.wav``                     -> output_dir/foo.wav
      * absolute paths                       -> used as-is
    Returns the first existing candidate, else ``None``.
    """
    if not audio_path:
        return None
    raw = str(audio_path).strip()
    if not raw or raw == "file not saved":
        return None

    raw = raw.replace("\\", "/")
    if os.path.isabs(raw) and Path(raw).is_file():
        return Path(raw)

    marker = "audio_storage/"
    rel = raw[len(marker):] if raw.startswith(marker) else raw
    rel = rel.lstrip("/")

    for candidate in (output_dir / rel, output_dir / Path(rel).name):
        if candidate.is_file():
            return candidate
    return None


def file_date(name: str, mtime: float) -> Optional[str]:
    """Best-effort YYYY-MM-DD for an audio file: from its name, else its mtime."""
    m = re.match(r"^(\d{4})(\d{2})(\d{2})_", name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^\d{1,2}-\d{2}-\d{2} [AP]M (\d{2})-(\d{2})-(\d{2})", name)
    if m:
        mm, dd, yy = m.groups()
        return f"20{yy}-{mm}-{dd}"
    try:
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    except (OSError, ValueError, OverflowError):
        return None


# --------------------------------------------------------------------------- helpers
def _expired_ids(session: Session, cutoff: str) -> Iterator[int]:
    """Stream expired log_entry ids with keyset pagination (no OFFSET scans)."""
    last = 0
    while True:
        rows = session.execute(
            text(
                "SELECT id FROM log_entries "
                "WHERE log_date < :cutoff AND id > :last ORDER BY id LIMIT :n"
            ),
            {"cutoff": cutoff, "last": last, "n": CHUNK},
        ).fetchall()
        if not rows:
            return
        for (row_id,) in rows:
            yield row_id
        last = rows[-1][0]


def _chunks(items: Iterable[int]) -> Iterator[list[int]]:
    buf: list[int] = []
    for item in items:
        buf.append(item)
        if len(buf) >= CHUNK:
            yield buf
            buf = []
    if buf:
        yield buf


def _delete_in(session: Session, table: str, column: str, ids: list[int]) -> int:
    if not ids:
        return 0
    stmt = text(f"DELETE FROM {table} WHERE {column} IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    return session.execute(stmt, {"ids": ids}).rowcount or 0


def _count_in(session: Session, table: str, column: str, ids: list[int]) -> int:
    if not ids:
        return 0
    stmt = text(f"SELECT COUNT(*) FROM {table} WHERE {column} IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    return int(session.execute(stmt, {"ids": ids}).scalar_one())


def _scalar(session: Session, sql: str, params: dict) -> int:
    return int(session.execute(text(sql), params).scalar_one())


# --------------------------------------------------------------------------- main
def run_retention(
    days: int,
    *,
    dry_run: bool = True,
    vacuum: bool = False,
    sweep_orphans: bool = True,
    session: Optional[Session] = None,
    output_dir: Optional[str] = None,
) -> RetentionReport:
    """Purge transmissions older than ``days``. ``dry_run`` performs no writes."""
    if days <= 0:
        raise ValueError("days must be > 0")

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    report = RetentionReport(cutoff_date=cutoff, dry_run=dry_run)

    settings = get_settings()
    out_dir = Path(output_dir or settings.output_dir)
    own_session = session is None
    db = session or SessionLocal()

    logger.info(
        "retention start cutoff=%s dry_run=%s audio_dir=%s", cutoff, dry_run, out_dir
    )

    try:
        # ---- phase 1: dependent rows (explicit, because the FKs only SET NULL) ----
        expired = list(_expired_ids(db, cutoff))
        report.log_entries = len(expired)
        logger.info("expired log_entries: %d", len(expired))

        if dry_run:
            # A dry run must still report what would go, or it cannot be reviewed.
            for chunk in _chunks(expired):
                report.entity_observations += _count_in(
                    db, "entity_observations", "log_entry_id", chunk
                )
                report.event_links += _count_in(
                    db, "event_transcript_links", "log_entry_id", chunk
                )
                report.span_store += _count_in(db, "span_store", "log_entry_id", chunk)
        else:
            for chunk in _chunks(expired):
                report.entity_observations += _delete_in(
                    db, "entity_observations", "log_entry_id", chunk
                )
                report.event_links += _delete_in(
                    db, "event_transcript_links", "log_entry_id", chunk
                )
                report.span_store += _delete_in(db, "span_store", "log_entry_id", chunk)
                db.commit()
        logger.info(
            "dependents: entity_observations=%d event_transcript_links=%d span_store=%d",
            report.entity_observations,
            report.event_links,
            report.span_store,
        )

        # ---- phase 2: audio files recorded on the expired rows ----
        last = 0
        while True:
            rows = db.execute(
                text(
                    "SELECT id, audio_path FROM log_entries "
                    "WHERE log_date < :cutoff AND id > :last ORDER BY id LIMIT :n"
                ),
                {"cutoff": cutoff, "last": last, "n": CHUNK},
            ).fetchall()
            if not rows:
                break
            for _row_id, audio_path in rows:
                target = resolve_audio_file(audio_path, out_dir)
                if target is None:
                    report.audio_files_missing += 1
                    continue
                try:
                    size = target.stat().st_size
                except OSError as exc:
                    logger.warning("cannot stat %s: %s", target, exc)
                    size = 0
                if dry_run:
                    report.audio_files_deleted += 1
                    report.audio_bytes_freed += size
                    continue
                try:
                    target.unlink()
                    report.audio_files_deleted += 1
                    report.audio_bytes_freed += size
                except FileNotFoundError:
                    report.audio_files_missing += 1
                except OSError as exc:
                    logger.warning("could not remove %s: %s", target, exc)
            last = rows[-1][0]
        logger.info(
            "audio: removed=%d (%.1f MB) missing=%d",
            report.audio_files_deleted,
            report.audio_bytes_freed / 1e6,
            report.audio_files_missing,
        )

        # ---- phase 3: the transmission rows themselves ----
        if not dry_run:
            for chunk in _chunks(iter(expired)):
                _delete_in(db, "log_entries", "id", chunk)
                db.commit()

        # ---- phase 4: events (by created_at; never while still open) ----
        report.events_skipped_open = _scalar(
            db,
            "SELECT COUNT(*) FROM events "
            "WHERE substr(created_at, 1, 10) < :cutoff AND status = 'open'",
            {"cutoff": cutoff},
        )
        report.events = _scalar(
            db,
            "SELECT COUNT(*) FROM events "
            "WHERE substr(created_at, 1, 10) < :cutoff "
            "AND (status IS NULL OR status != 'open')",
            {"cutoff": cutoff},
        )
        if not dry_run and report.events:
            db.execute(
                text(
                    "DELETE FROM events WHERE substr(created_at, 1, 10) < :cutoff "
                    "AND (status IS NULL OR status != 'open')"
                ),
                {"cutoff": cutoff},
            )
            db.commit()
        logger.info(
            "events: purged=%d skipped_open=%d", report.events, report.events_skipped_open
        )

        # ---- phase 5: hour summaries ----
        report.hour_summaries = _scalar(
            db,
            "SELECT COUNT(*) FROM hour_summaries WHERE summary_date < :cutoff",
            {"cutoff": cutoff},
        )
        if not dry_run and report.hour_summaries:
            db.execute(
                text("DELETE FROM hour_summaries WHERE summary_date < :cutoff"),
                {"cutoff": cutoff},
            )
            db.commit()
        logger.info("hour_summaries: purged=%d", report.hour_summaries)

        # ---- phase 6: orphaned audio (on disk, no live row) older than cutoff ----
        if sweep_orphans and out_dir.is_dir():
            known = {
                Path(str(p).replace("\\", "/")).name
                for (p,) in db.execute(text("SELECT audio_path FROM log_entries"))
                if p
            }
            for entry in os.scandir(out_dir):
                if not entry.is_file(follow_symlinks=False):
                    continue
                if Path(entry.name).suffix.lower() not in AUDIO_SUFFIXES:
                    continue
                if entry.name in known:
                    continue
                try:
                    st = entry.stat()
                except OSError as exc:
                    logger.warning("cannot stat %s: %s", entry.path, exc)
                    continue
                fdate = file_date(entry.name, st.st_mtime)
                if not fdate or fdate >= cutoff:
                    continue
                if dry_run:
                    report.orphan_files_deleted += 1
                    report.orphan_bytes_freed += st.st_size
                    continue
                try:
                    os.unlink(entry.path)
                    report.orphan_files_deleted += 1
                    report.orphan_bytes_freed += st.st_size
                except OSError as exc:
                    logger.warning("could not remove orphan %s: %s", entry.path, exc)
            logger.info(
                "orphans: removed=%d (%.1f MB)",
                report.orphan_files_deleted,
                report.orphan_bytes_freed / 1e6,
            )

        # ---- phase 7: reclaim (exclusive lock; never while ingest is busy) ----
        if vacuum and not dry_run:
            if own_session:
                db.close()
                db = None
            else:
                db.commit()
            try:
                with engine.connect() as conn:
                    conn = conn.execution_options(isolation_level="AUTOCOMMIT")
                    conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
                    conn.execute(text("VACUUM"))
                report.vacuumed = True
                logger.info("vacuum: complete")
            except SQLAlchemyError as exc:
                logger.error("vacuum failed", exc_info=exc)
                report.vacuumed = False

    finally:
        if own_session and db is not None:
            try:
                db.commit()
            except SQLAlchemyError as exc:
                logger.error("final commit failed", exc_info=exc)
                db.rollback()
            db.close()

    logger.info("retention done: %s", report.as_dict())
    return report


# --------------------------------------------------------------------------- CLI
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="ScanScribe data retention purge")
    parser.add_argument("--days", type=int, required=True, help="retention window in days")
    parser.add_argument(
        "--apply", action="store_true", help="actually delete (default is a dry run)"
    )
    parser.add_argument("--vacuum", action="store_true", help="VACUUM + truncate WAL afterwards")
    parser.add_argument(
        "--no-orphan-sweep", action="store_true", help="skip deleting orphaned audio files"
    )
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s"
    )

    report = run_retention(
        args.days,
        dry_run=not args.apply,
        vacuum=args.vacuum,
        sweep_orphans=not args.no_orphan_sweep,
    )

    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
        return 0

    verb = "WOULD DELETE" if report.dry_run else "DELETED"
    print(f"\ncutoff {report.cutoff_date}  ({'DRY RUN' if report.dry_run else 'APPLIED'})")
    print(f"  transmissions       {verb}: {report.log_entries:,}")
    print(
        f"  audio files         {verb}: {report.audio_files_deleted:,} "
        f"({report.audio_bytes_freed / 1e6:,.1f} MB)"
    )
    print(f"  audio already gone       : {report.audio_files_missing:,}")
    print(
        f"  orphan files        {verb}: {report.orphan_files_deleted:,} "
        f"({report.orphan_bytes_freed / 1e6:,.1f} MB)"
    )
    print(f"  span_store          {verb}: {report.span_store:,}")
    print(f"  entity_observations {verb}: {report.entity_observations:,}")
    print(f"  event_transcript_links {verb}: {report.event_links:,}")
    print(
        f"  events              {verb}: {report.events:,} "
        f"(skipped open: {report.events_skipped_open:,})"
    )
    print(f"  hour_summaries      {verb}: {report.hour_summaries:,}")
    print(f"  vacuum                   : {'done' if report.vacuumed else 'not run'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
