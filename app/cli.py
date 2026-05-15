"""ScanScribe maintenance CLI.

Usage:
    python -m app.cli rebuild_entity_observations [--since YYYY-MM-DD] [--monitor MID] [--dry-run]

Subcommands:
    rebuild_entity_observations
        Recompute and re-insert EntityObservation rows for existing SpanStore rows.
        Use after changing rules in app/services/entity_normalize.py. Idempotent:
        deletes existing observations for the affected span range first, then re-inserts.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, time as dtime, timezone
from typing import Optional

logger = logging.getLogger("scanscribe.cli")


def _parse_since(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        d = date.fromisoformat(value)
    except ValueError as ex:
        raise SystemExit(f"--since: expected YYYY-MM-DD, got {value!r} ({ex})") from ex
    return datetime.combine(d, dtime.min, tzinfo=timezone.utc)


def cmd_rebuild_entity_observations(args: argparse.Namespace) -> int:
    """Recompute entity_observations from existing SpanStore rows."""
    # Import deferred so plain `--help` doesn't load the whole stack.
    import json
    from sqlalchemy.orm import Session

    from .database import EventsSessionLocal, init_db
    from .models.event import EntityObservation, EventTranscriptLink, SpanStore
    from .services.entity_normalize import normalize_entity, supported_labels

    init_db()  # ensure tables exist
    since_dt = _parse_since(args.since)
    supported = supported_labels()

    db: Session = EventsSessionLocal()
    inserted = 0
    deleted = 0
    scanned = 0
    try:
        q = db.query(SpanStore)
        if since_dt is not None:
            q = q.filter(SpanStore.created_at >= since_dt)
        if args.monitor is not None:
            q = q.filter(SpanStore.monitor_id == int(args.monitor))

        # entities_json on EventTranscriptLink is the richest source (per-link NER).
        # Fall back to SpanStore comma-joined columns if no link exists.
        spans = q.order_by(SpanStore.id.asc()).all()
        scanned = len(spans)
        if not spans:
            print("rebuild_entity_observations: no SpanStore rows matched filters; nothing to do.")
            return 0

        span_ids = [s.id for s in spans]
        log_ids = [s.log_entry_id for s in spans if s.log_entry_id is not None]
        link_rows = (
            db.query(EventTranscriptLink.log_entry_id, EventTranscriptLink.entities_json)
            .filter(EventTranscriptLink.log_entry_id.in_(log_ids))
            .all()
            if log_ids
            else []
        )
        entities_by_log: dict[int, dict] = {}
        for log_id, entities_json in link_rows:
            if log_id is None or not entities_json:
                continue
            try:
                d = json.loads(entities_json)
                if isinstance(d, dict):
                    entities_by_log[log_id] = d
            except (TypeError, json.JSONDecodeError):
                continue

        if not args.dry_run:
            d_q = db.query(EntityObservation).filter(EntityObservation.span_store_id.in_(span_ids))
            deleted = d_q.delete(synchronize_session=False)
            db.commit()

        batch: list[EntityObservation] = []
        for span in spans:
            entities = entities_by_log.get(span.log_entry_id, None)
            if not entities:
                # Reconstruct minimal entities dict from SpanStore comma-joined cols.
                entities = {}
                for col, label in (
                    (span.evt_type, "EVT_TYPE"),
                    (span.units, "UNIT"),
                    (span.locations, "LOC"),
                    (span.addresses, "ADDRESS"),
                    (getattr(span, "status", None), "STATUS"),
                    (span.time_mentions, "TIME"),
                ):
                    if not col:
                        continue
                    parts = [p.strip() for p in str(col).split(",") if p.strip()]
                    if parts:
                        entities[label] = parts

            ts = span.created_at or datetime.now(timezone.utc)
            for label, values in entities.items():
                if label not in supported or not values:
                    continue
                for raw in values:
                    if not raw:
                        continue
                    canonical = normalize_entity(label, raw)
                    if not canonical:
                        continue
                    batch.append(
                        EntityObservation(
                            span_store_id=span.id,
                            monitor_id=span.monitor_id,
                            talkgroup=span.talkgroup,
                            log_entry_id=span.log_entry_id,
                            ts=ts,
                            label=label,
                            canonical=canonical[:500],
                            raw=raw[:500],
                        )
                    )
            if not args.dry_run and len(batch) >= 1000:
                db.add_all(batch)
                db.commit()
                inserted += len(batch)
                batch.clear()
        if not args.dry_run and batch:
            db.add_all(batch)
            db.commit()
            inserted += len(batch)

        print(
            f"rebuild_entity_observations: scanned={scanned} deleted={deleted} "
            f"inserted={inserted} dry_run={args.dry_run}"
        )
        return 0
    except Exception as ex:
        db.rollback()
        logger.exception("rebuild failed: %s", ex)
        return 1
    finally:
        db.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="app.cli", description="ScanScribe maintenance CLI"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rebuild = sub.add_parser(
        "rebuild_entity_observations",
        help="Recompute entity_observations from existing SpanStore rows",
    )
    p_rebuild.add_argument("--since", type=str, default=None, help="Only spans on/after YYYY-MM-DD (UTC)")
    p_rebuild.add_argument("--monitor", type=int, default=None, help="Restrict to one monitor id")
    p_rebuild.add_argument("--dry-run", action="store_true", help="Do not write changes")
    p_rebuild.set_defaults(func=cmd_rebuild_entity_observations)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
