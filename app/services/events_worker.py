"""Events pipeline: NER entity extraction → Single-pass OpenRouter LLM router."""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from ..config import get_settings
from ..database import EventsSessionLocal, LogsSessionLocal
from ..models.event import Monitor, Event, EventTranscriptLink, SpanStore, EntityObservation
from ..models.log_entry import LogEntry
from .events_common import event_work_lock, parse_json_list
from .entity_normalize import normalize_entity, supported_labels as _entity_supported_labels
from .ner_service import (
    extract_entities,
    normalize_span_for_ner,
    parse_list_field,
    load_ner_model,
)
from .events_debug import append_pipeline_debug, append_ner as debug_append_ner
from .events_router_engine import (
    EventsRouter,
    BROADCAST_TYPE_SLUGS,
    WORKER_BROADCAST_EVENT_TYPE,
)
from .websocket import websocket_manager

logger = logging.getLogger(__name__)


def _dispatch_geocoding_for_event(event_id: str, location: Optional[str], monitor_id: int) -> None:
    """Asynchronously geocode location for an event and broadcast coordinate update."""
    if not location or not location.strip() or location.strip().upper() == "N/A":
        return

    def _worker():
        try:
            geo_region = None
            ev_db = EventsSessionLocal()
            try:
                mon = ev_db.query(Monitor).filter(Monitor.id == monitor_id).first()
                if mon:
                    geo_region = mon.geo_region
            finally:
                ev_db.close()

            from .geocoder_service import resolve_address_sync
            res = resolve_address_sync(location, geo_region)
            if res:
                ev_db = EventsSessionLocal()
                try:
                    ev = ev_db.query(Event).filter(Event.event_id == event_id).first()
                    if ev:
                        ev.latitude = res.latitude
                        ev.longitude = res.longitude
                        ev.resolved_address = res.resolved_address
                        ev_db.commit()
                        logger.info("Geocoded event_id=%s -> (%f, %f) %s", event_id, res.latitude, res.longitude, res.resolved_address)
                        websocket_manager.broadcast_sync({
                            "type": "event_geocoded",
                            "data": {
                                "event_id": event_id,
                                "monitor_id": monitor_id,
                                "location": location,
                                "latitude": res.latitude,
                                "longitude": res.longitude,
                                "resolved_address": res.resolved_address,
                            }
                        })
                finally:
                    ev_db.close()
        except Exception as exc:
            logger.warning("Background geocoding failed for event_id=%s: %s", event_id, exc)

    threading.Thread(target=_worker, daemon=True, name=f"geocode-{event_id}").start()


def _utc_from_log_timestamp(dt: datetime, iana_tz: str) -> datetime:
    """LogEntry.timestamp is naive local wall time from ingest (queue_processor); see routes/events._iso_utc."""
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


def _utc_from_event_created(dt: datetime) -> datetime:
    """Event.created_at defaults to aware UTC; SQLite may round-trip naive UTC."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=timezone.utc)


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


def _infer_broadcast_slug_from_transcript(transcript: str) -> Optional[str]:
    """If router returns BROADCAST without broadcast_type, infer category from transcript text."""
    if not (transcript or "").strip():
        return None
    t = transcript.lower()
    if "attempt to locate" in t or re.search(r"\batl\b", t):
        return "attempt_to_locate"
    if "road debris" in t or ("debris" in t and "road" in t):
        return "road_debris"
    if "cni" in t or "cni driver" in t:
        return "cni_drivers"
    if (
        "storm warning" in t
        or "severe weather" in t
        or "tornado" in t
        or ("storm" in t and "warning" in t)
    ):
        return "storm_warning"
    return None


def _span_store_from_entities(
    monitor_id: int,
    talkgroup: str,
    transcript: str,
    log_entry_id: int,
    entities: Dict[str, List[str]],
) -> SpanStore:
    return SpanStore(
        monitor_id=monitor_id,
        talkgroup=talkgroup or None,
        transcript=transcript,
        evt_type=_comma_join_parts(entities.get("EVT_TYPE", [])),
        units=_comma_join_parts(entities.get("UNIT", [])),
        locations=_comma_join_parts(entities.get("LOC", [])),
        addresses=_comma_join_parts(entities.get("ADDRESS", [])),
        status=_comma_join_parts(entities.get("STATUS", [])),
        time_mentions=_comma_join_parts(entities.get("TIME", [])),
        log_entry_id=log_entry_id,
    )


def _entity_observations_from_entities(
    span_store_id: int,
    monitor_id: int,
    talkgroup: str,
    log_entry_id: int,
    entities: Dict[str, List[str]],
    ts: Optional[datetime] = None,
) -> List[EntityObservation]:
    """One EntityObservation row per (label, raw entity). Canonicalized for analytics grouping."""
    out: List[EntityObservation] = []
    supported = _entity_supported_labels()
    for label, values in entities.items():
        if not values or label not in supported:
            continue
        for raw in values:
            if not raw:
                continue
            canonical = normalize_entity(label, raw)
            if not canonical:
                continue
            out.append(
                EntityObservation(
                    span_store_id=span_store_id,
                    monitor_id=monitor_id,
                    talkgroup=talkgroup or None,
                    log_entry_id=log_entry_id,
                    ts=ts or datetime.now(timezone.utc),
                    label=label,
                    canonical=canonical[:500],
                    raw=raw[:500],
                )
            )
    return out


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

    addresses = entities.get("ADDRESS", [])
    if addresses:
        location = join_sorted_unique(addresses)
    else:
        location = join_sorted_unique(entities.get("LOC", []))

    units = join_sorted_unique(entities.get("UNIT", []))
    evt_type_parts = entities.get("EVT_TYPE", [])
    event_type = join_sorted_unique(evt_type_parts) if evt_type_parts else "N/A"
    status_detail = first(entities.get("STATUS", []))

    return {
        "event_type": event_type,
        "location": location,
        "units": units,
        "status_detail": status_detail,
        "original_transcription": transcript,
        "summary": None,
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


def _auto_close_stale_events(events_db, stale_seconds: int) -> None:
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
                ref_ts = logs_db.query(sa_func.max(LogEntry.timestamp)).filter(
                    LogEntry.id.in_(log_ids),
                    LogEntry.is_deleted == False,
                ).scalar()
                if ref_ts is not None:
                    ref_ts = _utc_from_log_timestamp(ref_ts, log_tz)
            else:
                ref_ts = None

            if ref_ts is None:
                ca = ev.created_at
                ref_ts = _utc_from_event_created(ca) if ca is not None else None
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
    event_type: Optional[str] = None,
    broadcast_type_slug: Optional[str] = None,
    location: Optional[str] = None,
    units: Optional[List[str]] = None,
    status_detail: Optional[str] = None,
    is_broadcast: bool = False,
) -> str:
    bt_slug = None
    if is_broadcast:
        if broadcast_type_slug:
            s = broadcast_type_slug.strip().lower()
            bt_slug = s if s in BROADCAST_TYPE_SLUGS else None
        if bt_slug is None:
            inferred = _infer_broadcast_slug_from_transcript(transcript)
            if inferred:
                bt_slug = inferred

    ner_hdr = _build_header_from_entities(entities, transcript)

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
    else:
        header = {
            "event_type": (event_type or "").strip() or (ner_hdr.get("event_type") if ner_hdr.get("event_type") != "N/A" else "Incident"),
            "location": (location or "").strip() or (ner_hdr.get("location") if ner_hdr.get("location") != "N/A" else None),
            "units": (", ".join(units) if units else None) or (ner_hdr.get("units") if ner_hdr.get("units") != "N/A" else None),
            "status_detail": (status_detail or "").strip() or (ner_hdr.get("status_detail") if ner_hdr.get("status_detail") != "N/A" else "Active"),
            "original_transcription": transcript,
            "summary": None,
        }
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
        master_last_run_at=datetime.now(timezone.utc),
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

    _dispatch_geocoding_for_event(event_id, header.get("location"), monitor_id)

    websocket_manager.broadcast_sync({
        "type": "event_update",
        "action": "create",
        "data": {
            "id": event.id,
            "event_id": event_id,
            "monitor_id": monitor_id,
            "status": ev_status,
            "event_type": header["event_type"],
            "broadcast_type": bt_slug if is_broadcast else None,
            "location": header["location"],
            "latitude": event.latitude,
            "longitude": event.longitude,
            "resolved_address": event.resolved_address,
            "units": header["units"],
            "status_detail": header["status_detail"],
            "original_transcription": header["original_transcription"],
            "summary": header["summary"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "closed_at": closed_at.isoformat() if closed_at else None,
            "spans_attached": 1,
            "talkgroup": talkgroup,
        }
    })

    append_pipeline_debug(
        monitor_id=monitor_id,
        log_entry_id=log_entry_id,
        action=debug_action,
        event_id=event_id,
        duration_ms=duration_ms,
        entities=entities,
        error="",
        raw_output=raw_output,
        transcript=transcript,
        llm_output=debug_llm_output,
    )
    logger.info(
        "Events: created event_id=%s (type=%s) monitor_id=%s log_entry_id=%s closed=%s",
        event_id,
        header.get("event_type"),
        monitor_id,
        log_entry_id,
        is_broadcast,
    )
    return event_id


def process_transcript_for_monitor(
    monitor_id: int,
    talkgroup: str,
    transcript: str,
    log_entry_id: int,
    log_timestamp=None,
) -> None:
    """
    Single-pass OpenRouter LLM router pipeline:
    1. Extract NER entities & persist to SpanStore / EntityObservation.
    2. Pre-flight check: if idle and no trigger entities, exit early.
    3. Query active open events + context for this monitor.
    4. Call EventsRouter.route_transcript (single pass).
    5. Handle CREATE, ATTACH, CLOSE, BROADCAST, or SKIP.
    """
    settings = get_settings()
    cfg = getattr(settings.config, "events_pipeline", None)
    if not cfg or not cfg.enabled or not cfg.ner_model_path:
        return

    events_db = EventsSessionLocal()
    logs_db = LogsSessionLocal()
    try:
        monitor = events_db.query(Monitor).filter(Monitor.id == monitor_id, Monitor.enabled == True).first()
        if not monitor:
            return

        strip_commas = getattr(cfg, "ner_strip_commas", True)
        ner_threshold = float(getattr(cfg, "ner_confidence_threshold", 0.0) or 0.0)
        ner_text = normalize_span_for_ner(transcript, strip_commas)
        t0 = time.perf_counter()
        entities, raw_output = extract_entities(ner_text, threshold=ner_threshold)
        ner_duration_ms = (time.perf_counter() - t0) * 1000

        # Persist every span to span_store so history reflects full activity
        span_row = _span_store_from_entities(monitor_id, talkgroup or "", transcript, log_entry_id, entities)
        events_db.add(span_row)
        events_db.flush()

        try:
            obs_rows = _entity_observations_from_entities(
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
            logger.warning("entity_observations write failed log_entry_id=%s: %s", log_entry_id, ex)
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

        # Pre-flight early exits when monitor is idle
        if not open_events:
            if not entities:
                debug_append_ner(
                    monitor_id, log_entry_id, "ner_empty", "", ner_duration_ms, {}, "", raw_output, transcript,
                )
                return
            if not has_start_label:
                debug_append_ner(
                    monitor_id, log_entry_id, "idle_no_evt_type", "", ner_duration_ms, entities, "", raw_output, transcript,
                )
                return

        # Fetch recent linked transcripts for open events to provide rich context to LLM
        open_incidents_payload: List[Dict[str, Any]] = []
        for ev in open_events:
            link_log_ids = [
                lid for (lid,) in events_db.query(EventTranscriptLink.log_entry_id)
                .filter(EventTranscriptLink.event_id == ev.id)
                .order_by(EventTranscriptLink.id.desc())
                .limit(3)
                .all()
                if lid is not None
            ]
            recent_t_texts: List[str] = []
            if link_log_ids:
                log_rows = logs_db.query(LogEntry.transcript).filter(LogEntry.id.in_(link_log_ids)).all()
                recent_t_texts = [r[0] for r in log_rows if r and r[0]]

            open_incidents_payload.append({
                "event_id": ev.event_id,
                "event_type": ev.event_type,
                "location": ev.location,
                "units": ev.units,
                "status_detail": ev.status_detail,
                "recent_transcripts": recent_t_texts,
            })

        # Fetch recent channel spans for conversational context
        recent_spans_rows = (
            events_db.query(SpanStore.transcript)
            .filter(SpanStore.monitor_id == monitor_id, SpanStore.id < span_row.id)
            .order_by(SpanStore.id.desc())
            .limit(3)
            .all()
        )
        recent_spans = [r[0] for r in reversed(recent_spans_rows) if r and r[0]]

        # Call the single-pass OpenRouter LLM
        decision = EventsRouter.route_transcript(
            monitor_name=monitor.name or "",
            talkgroup=talkgroup or "",
            transcript=transcript,
            entities=entities,
            open_incidents=open_incidents_payload,
            recent_spans=recent_spans,
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
            _create_event_full(
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
            _create_event_full(
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
                target_ev = events_db.query(Event).filter(
                    Event.event_id == target_eid,
                    Event.monitor_id == monitor_id,
                    Event.status == "open",
                ).first()

            # Fallback if single open event
            if not target_ev and len(open_events) == 1:
                target_ev = open_events[0]

            if target_ev:
                with event_work_lock(target_ev.id):
                    already_linked = events_db.query(EventTranscriptLink).filter(
                        EventTranscriptLink.event_id == target_ev.id,
                        EventTranscriptLink.log_entry_id == log_entry_id,
                    ).first()
                    if not already_linked:
                        events_db.add(
                            EventTranscriptLink(
                                event_id=target_ev.id,
                                log_entry_id=log_entry_id,
                                entities_json=_entities_json(entities),
                                llm_reason=(reason or "").strip()[:2000] or None,
                            )
                        )

                    # Update event header from LLM decision & NER
                    new_units = decision.get("units") or entities.get("UNIT", [])
                    if new_units:
                        target_ev.units = _merge_list_field(target_ev.units, new_units)

                    old_loc = target_ev.location
                    dec_loc = decision.get("location")
                    loc_changed = False
                    if dec_loc and (not target_ev.location or target_ev.location == "N/A" or len(dec_loc) > len(target_ev.location or "")):
                        if dec_loc != old_loc:
                            target_ev.location = dec_loc
                            loc_changed = True

                    dec_status = decision.get("status_detail")
                    if dec_status:
                        target_ev.status_detail = dec_status

                    dec_etype = decision.get("event_type")
                    if dec_etype and (not target_ev.event_type or target_ev.event_type == "N/A"):
                        target_ev.event_type = dec_etype

                    target_ev.master_last_run_at = datetime.now(timezone.utc)
                    events_db.commit()

                    if loc_changed and target_ev.location:
                        _dispatch_geocoding_for_event(target_ev.event_id, target_ev.location, monitor_id)

                    websocket_manager.broadcast_sync({
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
                        }
                    })

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
                logger.info("Events: attached log_entry_id=%s to event_id=%s", log_entry_id, target_ev.event_id)
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
                target_ev = events_db.query(Event).filter(
                    Event.event_id == target_eid,
                    Event.monitor_id == monitor_id,
                    Event.status == "open",
                ).first()

            if not target_ev and len(open_events) == 1:
                target_ev = open_events[0]

            if target_ev:
                with event_work_lock(target_ev.id):
                    already_linked = events_db.query(EventTranscriptLink).filter(
                        EventTranscriptLink.event_id == target_ev.id,
                        EventTranscriptLink.log_entry_id == log_entry_id,
                    ).first()
                    if not already_linked:
                        events_db.add(
                            EventTranscriptLink(
                                event_id=target_ev.id,
                                log_entry_id=log_entry_id,
                                entities_json=_entities_json(entities),
                                llm_reason=(reason or "").strip()[:2000] or None,
                            )
                        )

                    new_units = decision.get("units") or entities.get("UNIT", [])
                    if new_units:
                        target_ev.units = _merge_list_field(target_ev.units, new_units)

                    dec_status = decision.get("status_detail") or "Closed"
                    target_ev.status_detail = dec_status
                    target_ev.status = "closed"
                    target_ev.closed_at = datetime.now(timezone.utc)
                    target_ev.master_last_run_at = datetime.now(timezone.utc)
                    events_db.commit()

                    websocket_manager.broadcast_sync({
                        "type": "event_update",
                        "action": "close",
                        "data": {
                            "id": target_ev.id,
                            "event_id": target_ev.event_id,
                            "monitor_id": target_ev.monitor_id,
                            "status": "closed",
                            "closed_at": target_ev.closed_at.isoformat() if target_ev.closed_at else None,
                        }
                    })

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
                logger.info("Events: closed event_id=%s with log_entry_id=%s", target_ev.event_id, log_entry_id)
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


def ensure_ner_model_loaded() -> bool:
    settings = get_settings()
    cfg = getattr(settings.config, "events_pipeline", None)
    if not cfg or not cfg.enabled or not cfg.ner_model_path:
        return False
    return load_ner_model(cfg.ner_model_path)
