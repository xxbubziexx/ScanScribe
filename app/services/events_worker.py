"""Events pipeline: NER → span_store; Worker (EVT_TYPE) opens incidents; Master routes until close."""
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..config import get_settings
from ..database import EventsSessionLocal
from ..models.event import Monitor, Event, EventTranscriptLink, SpanStore
from .events_common import event_work_lock, parse_json_list
from .ner_service import (
    extract_entities,
    normalize_span_for_ner,
    parse_list_field,
    load_ner_model,
)
from .events_debug import append_ner as debug_append_ner
from .event_summary_ollama import schedule_event_summary
from .master_event_header_ollama import schedule_master_header_normalize
from .ollama_event_routing import route_transcript_with_llm
from .ollama_worker import (
    BROADCAST_TYPE_SLUGS,
    WORKER_BROADCAST_EVENT_TYPE,
    worker_should_create_event,
)

logger = logging.getLogger(__name__)


def _use_master_header_normalize() -> bool:
    settings = get_settings()
    pipe = settings.config.events_pipeline
    io_cfg = getattr(settings.config, "incidents_ollama", None)
    return (
        getattr(pipe, "master_header_normalize", True)
        and io_cfg is not None
        and getattr(io_cfg, "enabled", False)
    )


def _entities_json(entities: Dict[str, List[str]]) -> Optional[str]:
    if not entities:
        return None
    try:
        return json.dumps(entities)
    except (TypeError, ValueError):
        return None


def _comma_join_parts(parts: List[str]) -> Optional[str]:
    out = [((p or "").strip()) for p in parts if (p or "").strip()]
    return ", ".join(out) if out else None


def _span_store_from_entities(
    monitor_id: int,
    talkgroup: str,
    transcript: str,
    log_entry_id: int,
    entities: Dict[str, List[str]],
) -> SpanStore:
    evt = entities.get("EVT_TYPE", [])
    return SpanStore(
        monitor_id=monitor_id,
        talkgroup=talkgroup or None,
        transcript=transcript,
        evt_type=_comma_join_parts(evt),
        units=_comma_join_parts(entities.get("UNIT", []) + entities.get("AGENCY", [])),
        locations=_comma_join_parts(entities.get("LOC", [])),
        addresses=_comma_join_parts(entities.get("ADDRESS", [])),
        cross_streets=_comma_join_parts(entities.get("X_STREET", [])),
        persons=_comma_join_parts(entities.get("SUBJECT", [])),
        vehicles=_comma_join_parts(entities.get("DESC", []) + entities.get("STATUS", [])),
        plates=_comma_join_parts(entities.get("CONTEXT", [])),
        log_entry_id=log_entry_id,
    )


_monitor_index_lock = threading.Lock()
_monitor_index_cache: Optional[Tuple[Any, Dict[str, List[int]]]] = None


def _build_monitor_talkgroup_index(events_db) -> Tuple[Any, Dict[str, List[int]]]:
    """Build {talkgroup_lower: [monitor_ids]} index. Fingerprint = max(updated_at) over enabled monitors."""
    from sqlalchemy import func as sa_func

    fingerprint = events_db.query(sa_func.max(Monitor.updated_at)).scalar()
    index: Dict[str, List[int]] = {}
    for m in events_db.query(Monitor).filter(Monitor.enabled == True).all():
        for tg in parse_json_list(m.talkgroup_ids):
            if not isinstance(tg, str):
                continue
            key = tg.strip().lower()
            if not key:
                continue
            index.setdefault(key, []).append(m.id)
    return fingerprint, index


def get_matching_monitor_ids(events_db, talkgroup: str) -> List[int]:
    """Return enabled monitor IDs matching talkgroup. Uses a fingerprint-cached index."""
    global _monitor_index_cache
    if not talkgroup:
        return []
    key = talkgroup.strip().lower()
    if not key:
        return []
    from sqlalchemy import func as sa_func

    current_fp = events_db.query(sa_func.max(Monitor.updated_at)).scalar()
    with _monitor_index_lock:
        if _monitor_index_cache is None or _monitor_index_cache[0] != current_fp:
            _monitor_index_cache = _build_monitor_talkgroup_index(events_db)
        index = _monitor_index_cache[1]
    return list(index.get(key, []))


def _sort_entities_together(parts: List[str]) -> List[str]:
    def is_numeric(s: str) -> bool:
        return bool(s and s[0].isdigit())
    alpha = sorted([x for x in parts if x and not is_numeric(x)])
    numeric = sorted([x for x in parts if x and is_numeric(x)])
    return alpha + numeric


def _build_header_from_entities(entities: Dict[str, List[str]], transcript: str) -> Dict[str, str]:
    def first(ls: List[str]) -> str:
        return ls[0] if ls else "N/A"

    def join_sorted_unique(parts: List[str]) -> str:
        if not parts:
            return "N/A"
        seen = set()
        out = []
        for x in parts:
            x = (x or "").strip()
            if x and x.lower() not in seen:
                seen.add(x.lower())
                out.append(x)
        return ", ".join(_sort_entities_together(out)) if out else "N/A"

    location_parts = []
    for k in ("ADDRESS", "LOC", "X_STREET"):
        location_parts.extend(entities.get(k, []))
    location = join_sorted_unique(location_parts)

    unit_parts = entities.get("UNIT", []) + entities.get("AGENCY", [])
    units = join_sorted_unique(unit_parts)

    evt_type_parts = entities.get("EVT_TYPE", [])
    event_type = join_sorted_unique(evt_type_parts) if evt_type_parts else "N/A"
    status_detail = first(entities.get("STATUS", []))

    desc_parts = entities.get("DESC", []) + entities.get("SUBJECT", []) + entities.get("CONTEXT", [])
    summary = join_sorted_unique(desc_parts) if desc_parts else None

    return {
        "event_type": event_type,
        "location": location,
        "units": units,
        "status_detail": status_detail,
        "original_transcription": transcript,
        "summary": summary,
    }


def _merge_list_field(existing_raw: Optional[str], new_values: List[str]) -> str:
    """Merge new values into existing CSV/JSON list field, dedup case-insensitively, sort."""
    existing = parse_list_field(existing_raw)
    seen = {u.strip().lower() for u in existing if u}
    out = [u for u in existing if u]
    for v in new_values:
        v = (v or "").strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return ", ".join(_sort_entities_together(out)) if out else "N/A"


def _should_normalize_on_attach(events_db, event_db_id: int) -> bool:
    """Return True if total link count triggers a normalization run (every N spans)."""
    from sqlalchemy import func
    n = int(getattr(get_settings().config.events_pipeline, "normalize_every_n_spans", 5) or 0)
    if n <= 1:
        return True
    count = events_db.query(func.count(EventTranscriptLink.id)).filter(
        EventTranscriptLink.event_id == event_db_id
    ).scalar() or 0
    return count % n == 0


def _maybe_schedule_event_summary(events_db, event_db_id: int) -> None:
    cfg = get_settings().config.events_pipeline
    trigger = getattr(cfg, "summary_trigger_spans", 0) or 0
    if trigger <= 0:
        return
    from sqlalchemy import func
    count = events_db.query(func.count(EventTranscriptLink.id)).filter(
        EventTranscriptLink.event_id == event_db_id
    ).scalar() or 0
    if count >= trigger:
        schedule_event_summary(event_db_id)


def _auto_close_stale_events(events_db, stale_seconds: int) -> None:
    """Close open events whose last linked log entry timestamp is older than stale_seconds.

    Uses actual incident time (LogEntry.timestamp) rather than system/link timestamps.
    """
    if stale_seconds <= 0:
        return
    from ..database import LogsSessionLocal
    from ..models.log_entry import LogEntry
    from sqlalchemy import func as sa_func

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
                ref_ts = logs_db.query(sa_func.max(LogEntry.timestamp)).filter(
                    LogEntry.id.in_(log_ids),
                    LogEntry.is_deleted == False,
                ).scalar()
            else:
                ref_ts = None

            if ref_ts is None:
                ref_ts = ev.created_at
            if ref_ts is None:
                continue
            if getattr(ref_ts, "tzinfo", None) is None:
                ref_ts = ref_ts.replace(tzinfo=timezone.utc)
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


def start_event_cleanup_worker() -> None:
    """Daemon thread: periodically auto-closes stale events using incident time."""
    def _loop() -> None:
        while True:
            cfg = get_settings().config.events_pipeline
            interval = int(getattr(cfg, "cleanup_interval_seconds", 0) or 0)
            stale = int(getattr(cfg, "auto_close_stale_seconds", 0) or 0)
            sleep_for = interval if interval > 0 else 60
            if cfg.enabled and interval > 0 and stale > 0:
                try:
                    db = EventsSessionLocal()
                    try:
                        _auto_close_stale_events(db, stale)
                    finally:
                        db.close()
                except Exception as exc:
                    logger.warning("Events cleanup sweep failed: %s", exc)
            time.sleep(sleep_for)

    threading.Thread(target=_loop, daemon=True, name="events-cleanup").start()


def _create_event_full(
    events_db,
    monitor_id: int,
    talkgroup: str,
    transcript: str,
    entities: Dict[str, List[str]],
    log_entry_id: int,
    log_timestamp,
    duration_ms: float,
    raw_output: list,
    debug_action: str = "create",
    debug_reason: str = "",
    debug_llm_output: str = "",
    worker_event_type: Optional[str] = None,
    broadcast_type_slug: Optional[str] = None,
    use_master_header: bool = False,
) -> str:
    is_broadcast = (worker_event_type or "").upper() == WORKER_BROADCAST_EVENT_TYPE
    bt_slug = None
    if is_broadcast and broadcast_type_slug:
        s = broadcast_type_slug.strip().lower()
        bt_slug = s if s in BROADCAST_TYPE_SLUGS else None

    if is_broadcast:
        header = {
            "event_type": WORKER_BROADCAST_EVENT_TYPE,
            "location": None,
            "units": None,
            "status_detail": None,
            "original_transcription": transcript,
            "summary": None,
        }
        ev_status = "closed"
        closed_at = datetime.now(timezone.utc)
    elif use_master_header:
        header = {
            "event_type": None,
            "location": None,
            "units": None,
            "status_detail": None,
            "original_transcription": transcript,
            "summary": None,
        }
        ev_status = "open"
        closed_at = None
    else:
        header = _build_header_from_entities(entities, transcript)
        ev_status = "open"
        closed_at = None

    event_id = uuid.uuid4().hex[:16]
    event = Event(
        event_id=event_id,
        monitor_id=monitor_id,
        status=ev_status,
        event_type=header["event_type"],
        broadcast_type=bt_slug if is_broadcast else None,
        location=header["location"],
        units=header["units"],
        status_detail=header["status_detail"] or None,
        original_transcription=header["original_transcription"],
        summary=header["summary"],
        master_last_run_at=None,
        closed_at=closed_at,
    )
    events_db.add(event)
    events_db.flush()
    events_db.add(
        EventTranscriptLink(
            event_id=event.id,
            log_entry_id=log_entry_id,
            entities_json=_entities_json(entities),
            llm_reason=(debug_reason or "").strip()[:2000] or None,
        )
    )
    events_db.commit()
    debug_append_ner(
        monitor_id,
        log_entry_id,
        debug_action,
        event_id,
        duration_ms,
        entities,
        (debug_reason or "")[:500],
        raw_output,
        transcript,
        debug_llm_output,
    )
    logger.info(
        "Events: created event_id=%s (evt_type=%s) monitor_id=%s log_entry_id=%s closed=%s",
        event_id,
        header.get("event_type") or "(pending Master header)",
        monitor_id,
        log_entry_id,
        is_broadcast,
    )
    if use_master_header and not is_broadcast:
        schedule_master_header_normalize(event.id)
    return event_id


def process_transcript_for_monitor(
    monitor_id: int,
    talkgroup: str,
    transcript: str,
    log_entry_id: int,
    log_timestamp=None,
) -> None:
    """
    NER → span_store (if any entities).
    Idle + EVT_TYPE → Worker may create first incident.
    Open incident(s) + EVT_TYPE → Worker may create an additional incident; else Master routes.
    Open incident(s), no EVT_TYPE → Master only (attach/skip/close).
    """
    settings = get_settings()
    cfg = settings.config.events_pipeline
    if not cfg.enabled or not cfg.ner_model_path:
        return

    use_master_header = _use_master_header_normalize()
    events_db = EventsSessionLocal()
    try:
        monitor = events_db.query(Monitor).filter(Monitor.id == monitor_id, Monitor.enabled == True).first()
        if not monitor:
            return
        strip_commas = getattr(cfg, "ner_strip_commas", True)
        ner_threshold = float(getattr(cfg, "ner_confidence_threshold", 0.0) or 0.0)
        ner_text = normalize_span_for_ner(transcript, strip_commas)
        t0 = time.perf_counter()
        entities, raw_output = extract_entities(ner_text, threshold=ner_threshold)
        duration_ms = (time.perf_counter() - t0) * 1000

        open_events = list(
            events_db.query(Event)
            .filter(Event.monitor_id == monitor_id, Event.status == "open")
            .order_by(Event.created_at.desc())
            .all()
        )

        io_cfg = getattr(settings.config, "incidents_ollama", None)
        llm_on = bool(
            getattr(cfg, "llm_routing", False)
            and io_cfg is not None
            and getattr(io_cfg, "enabled", False)
        )

        if not entities:
            if not open_events or not llm_on:
                # Idle monitor or LLM off — nothing to route, drop span.
                debug_append_ner(
                    monitor_id, log_entry_id, "ner_empty", "", duration_ms, {}, "", raw_output, transcript,
                )
                return
            # Open incident exists — pass raw transcript to Master for continuity routing.
            # No span_store insert since there are no entities to store.
        else:
            events_db.add(_span_store_from_entities(monitor_id, talkgroup or "", transcript, log_entry_id, entities))
            events_db.commit()

        start_labels = parse_json_list(monitor.keyword_config) or ["EVT_TYPE"]
        start_labels = [s.strip().upper() for s in start_labels if s]
        has_start_label = any(entities.get(lbl) for lbl in start_labels)
        addresses = entities.get("ADDRESS", []) + entities.get("LOC", []) + entities.get("X_STREET", [])
        units = entities.get("UNIT", []) + entities.get("AGENCY", [])
        evt_types = entities.get("EVT_TYPE", [])

        open_summary = [
            {"event_id": e.event_id, "event_type": e.event_type, "location": e.location}
            for e in open_events
        ]

        # --- Open incident(s): optional stacked Worker (EVT_TYPE) then Master ---
        if open_events:
            if not llm_on:
                debug_append_ner(
                    monitor_id, log_entry_id, "master_needs_ollama", "", duration_ms, entities,
                    "set incidents_ollama.enabled and events_pipeline.llm_routing",
                    raw_output, transcript,
                )
                return
            if evt_types:
                wr_create, wr_reason_raw, wr_llm_output, wr_et, wr_bt = worker_should_create_event(
                    events_db=events_db,
                    monitor_id=monitor_id,
                    monitor_name=monitor.name or "",
                    talkgroup=talkgroup or "",
                    transcript=transcript,
                    entities=entities,
                    log_entry_id=log_entry_id,
                    open_incidents=open_summary,
                )
                if wr_create is None:
                    err = (wr_reason_raw or "Worker LLM error").strip()[:500]
                    debug_append_ner(
                        monitor_id, log_entry_id, "worker_fail", "", duration_ms, entities,
                        err, raw_output, transcript, wr_llm_output,
                    )
                elif wr_create:
                    wr_reason = (wr_reason_raw or "").strip()[:500]
                    stacked_action = (
                        "worker_create_stacked_broadcast"
                        if wr_et == WORKER_BROADCAST_EVENT_TYPE
                        else "worker_create_stacked"
                    )
                    _create_event_full(
                        events_db,
                        monitor_id,
                        talkgroup or "",
                        transcript,
                        entities,
                        log_entry_id,
                        log_timestamp,
                        duration_ms,
                        raw_output,
                        debug_action=stacked_action,
                        debug_reason=wr_reason or "Worker approved new incident while others open",
                        debug_llm_output=wr_llm_output,
                        worker_event_type=wr_et,
                        broadcast_type_slug=wr_bt,
                        use_master_header=use_master_header,
                    )
                    return
                else:
                    debug_append_ner(
                        monitor_id,
                        log_entry_id,
                        "worker_defer_master",
                        "",
                        duration_ms,
                        entities,
                        (wr_reason_raw or "").strip()[:500],
                        raw_output,
                        transcript,
                        wr_llm_output,
                    )

            decision = route_transcript_with_llm(
                monitor_id=monitor_id,
                monitor_name=monitor.name or "",
                talkgroup=talkgroup or "",
                transcript=transcript,
                entities=entities,
                log_entry_id=log_entry_id,
                log_timestamp=log_timestamp,
                has_start_label=has_start_label,
                start_labels=start_labels,
                events_db=events_db,
                worker_deferred=bool(evt_types),
                primary_event_id=open_events[0].event_id if open_events else None,
            )
            if not decision:
                debug_append_ner(
                    monitor_id, log_entry_id, "master_fail", "", duration_ms, entities,
                    "no valid LLM decision", raw_output, transcript,
                )
                return
            act = decision.get("action")
            reason = (decision.get("reason") or "")[:500]
            llm_output = (decision.get("_llm_output") or "")[:12000]
            if act == "skip":
                debug_append_ner(
                    monitor_id, log_entry_id, "master_skip", "", duration_ms, entities, reason, raw_output, transcript, llm_output,
                )
                return
            if act == "attach":
                eid = decision.get("event_id") or ""
                ev = events_db.query(Event).filter(
                    Event.event_id == eid,
                    Event.monitor_id == monitor_id,
                    Event.status == "open",
                ).first()
                if ev:
                    with event_work_lock(ev.id):
                        already_linked = events_db.query(EventTranscriptLink).filter(
                            EventTranscriptLink.event_id == ev.id,
                            EventTranscriptLink.log_entry_id == log_entry_id,
                        ).first()
                        if not already_linked:
                            events_db.add(
                                EventTranscriptLink(
                                    event_id=ev.id,
                                    log_entry_id=log_entry_id,
                                    entities_json=_entities_json(entities),
                                    llm_reason=(reason or "").strip()[:2000] or None,
                                )
                            )
                        if not use_master_header:
                            if units:
                                ev.units = _merge_list_field(ev.units, units)
                            if addresses:
                                ev.location = _merge_list_field(ev.location, addresses)
                        ev.master_last_run_at = datetime.now(timezone.utc)
                        events_db.commit()
                    if use_master_header and _should_normalize_on_attach(events_db, ev.id):
                        schedule_master_header_normalize(ev.id)
                    debug_append_ner(
                        monitor_id, log_entry_id, "master_attach", ev.event_id, duration_ms, entities, reason, raw_output, transcript, llm_output,
                    )
                    logger.info("Events Master: attached log_entry_id=%s to event_id=%s", log_entry_id, ev.event_id)
                else:
                    debug_append_ner(
                        monitor_id, log_entry_id, "master_attach_invalid", eid, duration_ms, entities, reason, raw_output, transcript, llm_output,
                    )
                return
            if act == "close":
                eid = decision.get("event_id") or ""
                ev = events_db.query(Event).filter(
                    Event.event_id == eid,
                    Event.monitor_id == monitor_id,
                    Event.status == "open",
                ).first()
                if ev:
                    with event_work_lock(ev.id):
                        existing = events_db.query(EventTranscriptLink).filter(
                            EventTranscriptLink.event_id == ev.id,
                            EventTranscriptLink.log_entry_id == log_entry_id,
                        ).first()
                        if not existing:
                            events_db.add(
                                EventTranscriptLink(
                                    event_id=ev.id,
                                    log_entry_id=log_entry_id,
                                    entities_json=_entities_json(entities),
                                    llm_reason=(reason or "").strip()[:2000] or None,
                                )
                            )
                        elif (reason or "").strip():
                            existing.llm_reason = (reason or "").strip()[:2000]
                        if not use_master_header:
                            if units:
                                ev.units = _merge_list_field(ev.units, units)
                            if addresses:
                                ev.location = _merge_list_field(ev.location, addresses)
                        ev.status = "closed"
                        ev.closed_at = datetime.now(timezone.utc)
                        ev.master_last_run_at = datetime.now(timezone.utc)
                        events_db.commit()
                    if use_master_header:
                        schedule_master_header_normalize(ev.id)
                    else:
                        _maybe_schedule_event_summary(events_db, ev.id)
                    debug_append_ner(
                        monitor_id, log_entry_id, "master_close", ev.event_id, duration_ms, entities, reason, raw_output, transcript, llm_output,
                    )
                    logger.info("Events Master: closed event_id=%s with log_entry_id=%s", ev.event_id, log_entry_id)
                else:
                    debug_append_ner(
                        monitor_id, log_entry_id, "master_close_invalid", eid, duration_ms, entities, reason, raw_output, transcript, llm_output,
                    )
                return
            return

        # --- Idle: no open incident ---
        if not evt_types:
            debug_append_ner(
                monitor_id, log_entry_id, "idle_no_evt_type", "", duration_ms, entities, "", raw_output, transcript,
            )
            return

        if not llm_on:
            debug_append_ner(
                monitor_id, log_entry_id, "worker_needs_ollama", "", duration_ms, entities,
                "set incidents_ollama.enabled and events_pipeline.llm_routing",
                raw_output, transcript,
            )
            return

        wr_create, wr_reason_raw, wr_llm_output, wr_et, wr_bt = worker_should_create_event(
            events_db=events_db,
            monitor_id=monitor_id,
            monitor_name=monitor.name or "",
            talkgroup=talkgroup or "",
            transcript=transcript,
            entities=entities,
            log_entry_id=log_entry_id,
            open_incidents=[],
        )
        if wr_create is None:
            err = (wr_reason_raw or "Worker LLM error").strip()[:500]
            debug_append_ner(
                monitor_id, log_entry_id, "worker_fail", "", duration_ms, entities,
                err, raw_output, transcript, wr_llm_output,
            )
            return
        worker_reason = (wr_reason_raw or "").strip()[:500]
        if not wr_create:
            debug_append_ner(
                monitor_id, log_entry_id, "worker_reject", "", duration_ms, entities,
                worker_reason, raw_output, transcript, wr_llm_output,
            )
            return

        idle_action = (
            "worker_create_broadcast"
            if wr_et == WORKER_BROADCAST_EVENT_TYPE
            else "worker_create"
        )
        _create_event_full(
            events_db,
            monitor_id,
            talkgroup or "",
            transcript,
            entities,
            log_entry_id,
            log_timestamp,
            duration_ms,
            raw_output,
            debug_action=idle_action,
            debug_reason=worker_reason or "Worker approved create",
            debug_llm_output=wr_llm_output,
            worker_event_type=wr_et,
            broadcast_type_slug=wr_bt,
            use_master_header=use_master_header,
        )
    finally:
        events_db.close()


def ensure_ner_model_loaded() -> bool:
    settings = get_settings()
    cfg = getattr(settings.config, "events_pipeline", None)
    if not cfg or not cfg.enabled or not cfg.ner_model_path:
        return False
    return load_ner_model(cfg.ner_model_path)
