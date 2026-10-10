"""Core routing & transcript ingestion pipeline."""
from datetime import datetime, timezone
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from ...config import get_settings
from ...database import EventsSessionLocal, LogsSessionLocal
from ...models.event import Event, EventTranscriptLink, Monitor, SpanStore
from ...models.log_entry import LogEntry
from ..events_common import event_work_lock, parse_json_list
from ..events_debug import append_ner as debug_append_ner, append_pipeline_debug
from ..events_router_engine import EventsRouter
from ..ner_service import extract_entities, load_ner_model, normalize_span_for_ner
from ..websocket import websocket_manager
from .context import get_global_prompt_rules, is_pure_chatter, merge_list_field
from .incidents import create_event_full, dispatch_geocoding_for_event, summarize_event_attachments
from .spans import (
    entities_json,
    entity_observations_from_entities,
    span_store_from_entities,
)

logger = logging.getLogger(__name__)

_monitor_index_lock = threading.Lock()
_monitor_index_cache: Optional[Tuple[Any, Dict[str, List[int]]]] = None
_last_fp_check: float = 0.0
_MONITOR_FP_CHECK_INTERVAL: float = 5.0  # Check DB fingerprint at most once every 5s on ingest


def normalize_talkgroup_key(tg: str) -> str:
    """Normalize a talkgroup string by lowercasing, stripping, and collapsing internal whitespace."""
    if not tg:
        return ""
    return re.sub(r"\s+", " ", tg.strip().lower())


def build_monitor_talkgroup_index(events_db) -> Tuple[Any, Dict[str, List[int]]]:
    """Build {talkgroup_lower: [monitor_ids]} index. Fingerprint = max(updated_at) over enabled monitors."""
    from sqlalchemy import func as sa_func

    fingerprint = events_db.query(sa_func.max(Monitor.updated_at)).scalar()
    index: Dict[str, List[int]] = {}
    for m in events_db.query(Monitor).filter(Monitor.enabled == True).all():
        for tg in parse_json_list(m.talkgroup_ids):
            if not isinstance(tg, str):
                continue
            key = normalize_talkgroup_key(tg)
            if not key:
                continue
            index.setdefault(key, []).append(m.id)
    return fingerprint, index


def invalidate_monitor_index_cache() -> None:
    """Explicitly invalidate monitor index cache when monitors are added/modified."""
    global _last_fp_check, _monitor_index_cache
    with _monitor_index_lock:
        _last_fp_check = 0.0
        _monitor_index_cache = None


def get_matching_monitor_ids(events_db, talkgroup: str) -> List[int]:
    """Return enabled monitor IDs matching talkgroup. Uses a fingerprint-cached index."""
    global _monitor_index_cache, _last_fp_check
    if not talkgroup:
        return []
    key = normalize_talkgroup_key(talkgroup)
    if not key:
        return []

    now = time.time()
    with _monitor_index_lock:
        if _monitor_index_cache is None or (now - _last_fp_check) > _MONITOR_FP_CHECK_INTERVAL:
            from sqlalchemy import func as sa_func

            current_fp = events_db.query(sa_func.max(Monitor.updated_at)).scalar()
            _last_fp_check = now
            if _monitor_index_cache is None or _monitor_index_cache[0] != current_fp:
                _monitor_index_cache = build_monitor_talkgroup_index(events_db)
        index = _monitor_index_cache[1]
    return list(index.get(key, []))


def ensure_ner_model_loaded() -> bool:
    settings = get_settings()
    cfg = getattr(settings.config, "events_pipeline", None)
    if not cfg or not cfg.enabled or not cfg.ner_model_path:
        return False
    return load_ner_model(cfg.ner_model_path)


def process_transcript_for_monitor(
    monitor_id: int,
    talkgroup: str,
    transcript: str,
    log_entry_id: int,
    log_timestamp=None,
) -> None:
    """Single-pass OpenRouter LLM router pipeline."""
    settings = get_settings()
    cfg = getattr(settings.config, "events_pipeline", None)
    if not cfg or not cfg.enabled or not cfg.ner_model_path:
        return

    events_db = EventsSessionLocal()
    logs_db = LogsSessionLocal()
    try:
        monitor = (
            events_db.query(Monitor)
            .filter(Monitor.id == monitor_id, Monitor.enabled == True)
            .first()
        )
        if not monitor:
            return

        strip_commas = getattr(cfg, "ner_strip_commas", True)
        ner_threshold = float(getattr(cfg, "ner_confidence_threshold", 0.0) or 0.0)
        ner_text = normalize_span_for_ner(transcript, strip_commas)
        t0 = time.perf_counter()
        entities, raw_output = extract_entities(ner_text, threshold=ner_threshold)
        ner_duration_ms = (time.perf_counter() - t0) * 1000

        span_row = span_store_from_entities(
            monitor_id, talkgroup or "", transcript, log_entry_id, entities
        )
        events_db.add(span_row)
        events_db.flush()

        try:
            obs_rows = entity_observations_from_entities(
                span_store_id=span_row.id,
                monitor_id=monitor_id,
                talkgroup=talkgroup or "",
                log_entry_id=log_entry_id,
                entities=entities,
                ts=log_timestamp if isinstance(log_timestamp, datetime) else None,
            )
            if obs_rows:
                events_db.add_all(obs_rows)
        except Exception as ex:
            logger.warning(
                "entity_observations write failed log_entry_id=%s: %s",
                log_entry_id,
                ex,
            )
        events_db.commit()

        open_events = list(
            events_db.query(Event)
            .filter(Event.monitor_id == monitor_id, Event.status == "open")
            .order_by(Event.created_at.desc())
            .all()
        )

        start_labels = parse_json_list(monitor.keyword_config) or ["EVT_TYPE"]
        start_labels = [s.strip().upper() for s in start_labels if s]
        has_start_label = any(entities.get(lbl) for lbl in start_labels)

        if not open_events:
            if not entities:
                debug_append_ner(
                    monitor_id,
                    log_entry_id,
                    "ner_empty",
                    "",
                    ner_duration_ms,
                    {},
                    "",
                    raw_output,
                    transcript,
                )
                return
            if not has_start_label:
                debug_append_ner(
                    monitor_id,
                    log_entry_id,
                    "idle_no_evt_type",
                    "",
                    ner_duration_ms,
                    entities,
                    "",
                    raw_output,
                    transcript,
                )
                return

        if open_events and is_pure_chatter(transcript, entities):
            append_pipeline_debug(
                monitor_id=monitor_id,
                log_entry_id=log_entry_id,
                action="local_skip_chatter",
                event_id="",
                duration_ms=ner_duration_ms,
                entities=entities,
                error="",
                raw_output=raw_output,
                transcript=transcript,
                llm_output="Filtered by zero-token local chatter pre-filter",
            )
            logger.info(
                "Events: local chatter pre-filter skipped transcript=%r log_entry_id=%s",
                transcript,
                log_entry_id,
            )
            return

        open_incidents_payload: List[Dict[str, Any]] = []
        for ev in open_events:
            link_log_ids = [
                lid
                for (lid,) in events_db.query(EventTranscriptLink.log_entry_id)
                .filter(EventTranscriptLink.event_id == ev.id)
                .order_by(EventTranscriptLink.id.desc())
                .limit(3)
                .all()
                if lid is not None
            ]
            recent_t_texts: List[str] = []
            if link_log_ids:
                log_rows = (
                    logs_db.query(LogEntry.transcript)
                    .filter(LogEntry.id.in_(link_log_ids))
                    .all()
                )
                recent_t_texts = [r[0] for r in log_rows if r and r[0]]

            open_incidents_payload.append(
                {
                    "event_id": ev.event_id,
                    "event_type": ev.event_type,
                    "location": ev.location,
                    "resolved_address": ev.resolved_address,
                    "units": ev.units,
                    "status_detail": ev.status_detail,
                    "summary": ev.summary,
                    "recent_transcripts": recent_t_texts,
                }
            )

        recent_limit = int(getattr(cfg, "recent_spans_limit", 6) or 6)
        if recent_limit <= 0:
            recent_limit = 6

        recent_spans_rows = (
            events_db.query(SpanStore)
            .filter(
                SpanStore.monitor_id == monitor_id,
                SpanStore.id < span_row.id,
                SpanStore.transcript.isnot(None),
                SpanStore.transcript != "",
            )
            .order_by(SpanStore.id.desc())
            .limit(recent_limit)
            .all()
        )
        recent_spans: List[Dict[str, Any]] = []
        for s in reversed(recent_spans_rows):
            t_text = (s.transcript or "").strip()
            if not t_text:
                continue
            time_str = None
            if getattr(s, "created_at", None):
                ca = s.created_at
                if isinstance(ca, datetime):
                    time_str = ca.strftime("%H:%M:%S")
                elif isinstance(ca, str):
                    try:
                        time_str = datetime.fromisoformat(ca.replace("Z", "+00:00")).strftime("%H:%M:%S")
                    except Exception:
                        time_str = ca[:8]

            recent_spans.append(
                {
                    "id": s.id,
                    "transcript": t_text,
                    "talkgroup": s.talkgroup or "",
                    "units": s.units or "",
                    "location": s.locations or s.addresses or "",
                    "time": time_str,
                }
            )

        global_rules = get_global_prompt_rules(events_db)
        decision = EventsRouter.route_transcript(
            monitor_name=monitor.name or "",
            talkgroup=talkgroup or "",
            transcript=transcript,
            entities=entities,
            open_incidents=open_incidents_payload,
            recent_spans=recent_spans,
            known_units=getattr(monitor, "known_units", None),
            global_rules=global_rules,
        )

        action = decision.get("action", "SKIP")
        reason = decision.get("reason", "")
        llm_output = decision.get("raw_llm_output", "")
        total_duration_ms = ner_duration_ms + float(decision.get("duration_ms", 0.0))

        if action == "SKIP":
            append_pipeline_debug(
                monitor_id=monitor_id,
                log_entry_id=log_entry_id,
                action="router_skip",
                event_id="",
                duration_ms=total_duration_ms,
                entities=entities,
                error=decision.get("error") or "",
                raw_output=raw_output,
                transcript=transcript,
                llm_output=llm_output,
            )
            return

        if action == "CREATE":
            create_event_full(
                events_db=events_db,
                monitor_id=monitor_id,
                talkgroup=talkgroup or "",
                transcript=transcript,
                entities=entities,
                log_entry_id=log_entry_id,
                log_timestamp=log_timestamp,
                duration_ms=total_duration_ms,
                raw_output=raw_output,
                debug_action="router_create",
                debug_reason=reason,
                debug_llm_output=llm_output,
                event_type=decision.get("event_type"),
                broadcast_type_slug=decision.get("broadcast_type"),
                location=decision.get("location"),
                units=decision.get("units"),
                status_detail=decision.get("status_detail"),
                is_broadcast=False,
            )
            return

        if action == "BROADCAST":
            create_event_full(
                events_db=events_db,
                monitor_id=monitor_id,
                talkgroup=talkgroup or "",
                transcript=transcript,
                entities=entities,
                log_entry_id=log_entry_id,
                log_timestamp=log_timestamp,
                duration_ms=total_duration_ms,
                raw_output=raw_output,
                debug_action="router_broadcast",
                debug_reason=reason,
                debug_llm_output=llm_output,
                broadcast_type_slug=decision.get("broadcast_type"),
                is_broadcast=True,
            )
            return

        if action == "ATTACH":
            target_eid = decision.get("event_id")
            target_ev = None
            if target_eid:
                target_ev = (
                    events_db.query(Event)
                    .filter(
                        Event.event_id == target_eid,
                        Event.monitor_id == monitor_id,
                        Event.status == "open",
                    )
                    .first()
                )

            if not target_ev and len(open_events) == 1:
                target_ev = open_events[0]

            if target_ev:
                with event_work_lock(target_ev.id):
                    already_linked = (
                        events_db.query(EventTranscriptLink)
                        .filter(
                            EventTranscriptLink.event_id == target_ev.id,
                            EventTranscriptLink.log_entry_id == log_entry_id,
                        )
                        .first()
                    )
                    if not already_linked:
                        events_db.add(
                            EventTranscriptLink(
                                event_id=target_ev.id,
                                log_entry_id=log_entry_id,
                                entities_json=entities_json(entities),
                                llm_reason=(reason or "").strip()[:2000] or None,
                            )
                        )

                    new_units = decision.get("units") or entities.get("UNIT", [])
                    if new_units:
                        target_ev.units = merge_list_field(target_ev.units, new_units)

                    old_loc = target_ev.location
                    dec_loc = decision.get("location")
                    loc_changed = False
                    if dec_loc and (
                        not target_ev.location
                        or target_ev.location == "N/A"
                        or len(dec_loc) > len(target_ev.location or "")
                    ):
                        if dec_loc != old_loc:
                            target_ev.location = dec_loc
                            loc_changed = True

                    dec_status = decision.get("status_detail")
                    if dec_status:
                        target_ev.status_detail = dec_status
                        if dec_status.strip().lower() in ("cleared", "terminated", "closed", "resolved"):
                            target_ev.status = "closed"
                            if not target_ev.closed_at:
                                target_ev.closed_at = datetime.now(timezone.utc)

                    dec_etype = decision.get("event_type")
                    if dec_etype and (not target_ev.event_type or target_ev.event_type == "N/A"):
                        target_ev.event_type = dec_etype

                    target_ev.updated_at = datetime.now(timezone.utc)
                    events_db.commit()

                    try:
                        summarize_event_attachments(target_ev, events_db, logs_db, force=True)
                    except Exception as e:
                        logger.warning("Failed updating event summary on attach: %s", e)

                    if loc_changed and target_ev.location:
                        dispatch_geocoding_for_event(target_ev.event_id, target_ev.location, monitor_id)

                    span_count = (
                        events_db.query(EventTranscriptLink)
                        .filter(EventTranscriptLink.event_id == target_ev.id)
                        .count()
                    )
                    websocket_manager.broadcast_sync(
                        {
                            "type": "event_update",
                            "action": "attach",
                            "data": {
                                "id": target_ev.id,
                                "event_id": target_ev.event_id,
                                "monitor_id": target_ev.monitor_id,
                                "status": target_ev.status,
                                "event_type": target_ev.event_type,
                                "broadcast_type": target_ev.broadcast_type,
                                "location": target_ev.location,
                                "latitude": target_ev.latitude,
                                "longitude": target_ev.longitude,
                                "resolved_address": target_ev.resolved_address,
                                "units": target_ev.units,
                                "status_detail": target_ev.status_detail,
                                "original_transcription": target_ev.original_transcription,
                                "summary": target_ev.summary,
                                "talkgroup": talkgroup,
                                "spans_attached": span_count,
                                "updated_at": (
                                    target_ev.updated_at.isoformat()
                                    if target_ev.updated_at
                                    else datetime.now(timezone.utc).isoformat()
                                ),
                            },
                        }
                    )

                append_pipeline_debug(
                    monitor_id=monitor_id,
                    log_entry_id=log_entry_id,
                    action="router_attach",
                    event_id=target_ev.event_id,
                    duration_ms=total_duration_ms,
                    entities=entities,
                    error="",
                    raw_output=raw_output,
                    transcript=transcript,
                    llm_output=llm_output,
                )
                logger.info(
                    "Events: attached log_entry_id=%s to event_id=%s",
                    log_entry_id,
                    target_ev.event_id,
                )
            else:
                append_pipeline_debug(
                    monitor_id=monitor_id,
                    log_entry_id=log_entry_id,
                    action="router_attach_invalid",
                    event_id=target_eid or "",
                    duration_ms=total_duration_ms,
                    entities=entities,
                    error=f"No matching open event found for event_id={target_eid}",
                    raw_output=raw_output,
                    transcript=transcript,
                    llm_output=llm_output,
                )
            return

        if action == "CLOSE":
            target_eid = decision.get("event_id")
            target_ev = None
            if target_eid:
                target_ev = (
                    events_db.query(Event)
                    .filter(
                        Event.event_id == target_eid,
                        Event.monitor_id == monitor_id,
                        Event.status == "open",
                    )
                    .first()
                )

            if not target_ev and len(open_events) == 1:
                target_ev = open_events[0]

            if target_ev:
                with event_work_lock(target_ev.id):
                    already_linked = (
                        events_db.query(EventTranscriptLink)
                        .filter(
                            EventTranscriptLink.event_id == target_ev.id,
                            EventTranscriptLink.log_entry_id == log_entry_id,
                        )
                        .first()
                    )
                    if not already_linked:
                        events_db.add(
                            EventTranscriptLink(
                                event_id=target_ev.id,
                                log_entry_id=log_entry_id,
                                entities_json=entities_json(entities),
                                llm_reason=(reason or "").strip()[:2000] or None,
                            )
                        )

                    new_units = decision.get("units") or entities.get("UNIT", [])
                    if new_units:
                        target_ev.units = merge_list_field(target_ev.units, new_units)

                    dec_status = decision.get("status_detail") or "Closed"
                    target_ev.status_detail = dec_status
                    target_ev.status = "closed"
                    target_ev.closed_at = datetime.now(timezone.utc)
                    target_ev.updated_at = datetime.now(timezone.utc)
                    events_db.commit()

                    try:
                        summarize_event_attachments(target_ev, events_db, logs_db, force=True)
                    except Exception as e:
                        logger.warning("Failed updating event summary on close: %s", e)

                    websocket_manager.broadcast_sync(
                        {
                            "type": "event_update",
                            "action": "close",
                            "data": {
                                "id": target_ev.id,
                                "event_id": target_ev.event_id,
                                "monitor_id": target_ev.monitor_id,
                                "status": "closed",
                                "closed_at": (
                                    target_ev.closed_at.isoformat()
                                    if target_ev.closed_at
                                    else None
                                ),
                                "updated_at": (
                                    target_ev.updated_at.isoformat()
                                    if target_ev.updated_at
                                    else datetime.now(timezone.utc).isoformat()
                                ),
                                "summary": target_ev.summary,
                            },
                        }
                    )

                append_pipeline_debug(
                    monitor_id=monitor_id,
                    log_entry_id=log_entry_id,
                    action="router_close",
                    event_id=target_ev.event_id,
                    duration_ms=total_duration_ms,
                    entities=entities,
                    error="",
                    raw_output=raw_output,
                    transcript=transcript,
                    llm_output=llm_output,
                )
                logger.info(
                    "Events: closed event_id=%s with log_entry_id=%s",
                    target_ev.event_id,
                    log_entry_id,
                )
            else:
                append_pipeline_debug(
                    monitor_id=monitor_id,
                    log_entry_id=log_entry_id,
                    action="router_close_invalid",
                    event_id=target_eid or "",
                    duration_ms=total_duration_ms,
                    entities=entities,
                    error=f"No matching open event found for event_id={target_eid}",
                    raw_output=raw_output,
                    transcript=transcript,
                    llm_output=llm_output,
                )
            return

    finally:
        events_db.close()
        logs_db.close()


# Aliases for backward compatibility
_normalize_talkgroup_key = normalize_talkgroup_key
_build_monitor_talkgroup_index = build_monitor_talkgroup_index
