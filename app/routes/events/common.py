"""Shared helpers and serialization utilities for Events API routes."""
from collections import defaultdict
from datetime import datetime as dt, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.event import Event, EventTranscriptLink
from ...models.log_entry import LogEntry
from ...services.events_common import parse_json_list


def iso_utc(d: dt | None, assume_utc: bool = False) -> str | None:
    """Serialize datetime for the Events API / browser display.

    - Timezone-aware values are normalized to UTC with a Z suffix.
    - Naive values with assume_utc=True are treated as UTC.
    - Naive values with assume_utc=False (default) are treated as local wall-clock.
    """
    if d is None:
        return None
    if d.tzinfo is None:
        if assume_utc:
            d = d.replace(tzinfo=timezone.utc)
        else:
            return d.isoformat()
    u = d.astimezone(timezone.utc)
    return u.isoformat().replace("+00:00", "Z")


def start_labels(raw: Optional[str]) -> List[str]:
    labels = parse_json_list(raw)
    return labels if labels else ["EVT_TYPE"]


def batch_event_link_aggregates(
    events_db: Session,
    logs_db: Session,
    event_ids: List[int],
) -> Tuple[
    Dict[int, int],
    Dict[int, str],
    Dict[int, Optional[dt]],
    Dict[int, Optional[dt]],
    Dict[int, Optional[str]],
]:
    """Spans per event, aggregated talkgroups, earliest linked log timestamp, latest linked log timestamp, primary audio_path."""
    if not event_ids:
        return {}, {}, {}, {}, {}
    count_rows = (
        events_db.query(EventTranscriptLink.event_id, func.count(EventTranscriptLink.id))
        .filter(EventTranscriptLink.event_id.in_(event_ids))
        .group_by(EventTranscriptLink.event_id)
        .all()
    )
    link_counts = {eid: int(cnt or 0) for eid, cnt in count_rows}
    link_rows = (
        events_db.query(
            EventTranscriptLink.event_id,
            EventTranscriptLink.log_entry_id,
            EventTranscriptLink.linked_at,
        )
        .filter(EventTranscriptLink.event_id.in_(event_ids))
        .all()
    )
    log_ids = sorted({lid for _, lid, _ in link_rows if lid is not None})
    talkgroup_by_log_id: Dict[int, str] = {}
    ts_by_log_id: Dict[int, dt] = {}
    audio_path_by_log_id: Dict[int, str] = {}
    if log_ids:
        for lid, tg, ts, apath in (
            logs_db.query(LogEntry.id, LogEntry.talkgroup, LogEntry.timestamp, LogEntry.audio_path)
            .filter(LogEntry.id.in_(log_ids))
            .all()
        ):
            if tg:
                talkgroup_by_log_id[lid] = tg
            if ts is not None:
                ts_by_log_id[lid] = ts
            if apath and apath != "file not saved":
                audio_path_by_log_id[lid] = apath
    links_by_event: Dict[int, List[int]] = defaultdict(list)
    max_linked_at_by_event: Dict[int, dt] = {}
    for ev_id, log_id, linked_at in link_rows:
        if log_id is not None:
            links_by_event[ev_id].append(log_id)
        if linked_at is not None:
            if ev_id not in max_linked_at_by_event or linked_at > max_linked_at_by_event[ev_id]:
                max_linked_at_by_event[ev_id] = linked_at
    first_span_at_by_event: Dict[int, Optional[dt]] = {}
    last_span_at_by_event: Dict[int, Optional[dt]] = {}
    audio_path_by_event: Dict[int, Optional[str]] = {}
    for ev_id, lids in links_by_event.items():
        tss = [ts_by_log_id[lid] for lid in lids if lid in ts_by_log_id]
        if tss:
            first_span_at_by_event[ev_id] = min(tss)
            last_span_at_by_event[ev_id] = max(tss)
        elif ev_id in max_linked_at_by_event:
            first_span_at_by_event[ev_id] = max_linked_at_by_event[ev_id]
            last_span_at_by_event[ev_id] = max_linked_at_by_event[ev_id]
        for lid in lids:
            if lid in audio_path_by_log_id:
                audio_path_by_event[ev_id] = audio_path_by_log_id[lid]
                break
    talkgroups_by_event: Dict[int, set] = defaultdict(set)
    for ev_id, log_id, _ in link_rows:
        tg = talkgroup_by_log_id.get(log_id)
        if tg:
            talkgroups_by_event[ev_id].add(tg)
    talkgroup_str = {
        eid: ", ".join(sorted(talkgroups_by_event[eid])) if talkgroups_by_event.get(eid) else ""
        for eid in event_ids
    }
    return link_counts, talkgroup_str, first_span_at_by_event, last_span_at_by_event, audio_path_by_event


def event_type_csv_display(event: Event) -> str:
    """Single column matching UI: BROADCAST subtype vs incident event_type."""
    bt = (getattr(event, "broadcast_type", None) or "").strip()
    if bt:
        return f"BROADCAST:{bt}"
    et = (event.event_type or "").strip()
    if et.upper() == "BROADCAST":
        return "BROADCAST"
    return et


# Aliases for backward compatibility
_iso_utc = iso_utc
_start_labels = start_labels
_batch_event_link_aggregates = batch_event_link_aggregates
_event_type_csv_display = event_type_csv_display
