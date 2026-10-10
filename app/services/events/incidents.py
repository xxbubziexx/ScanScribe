"""Incident creation, merging, summarization, and geocoding dispatch."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import logging
import re
from typing import Any, Dict, List, Optional
import uuid

from ...database import EventsSessionLocal, LogsSessionLocal
from ...models.event import Event, EventTranscriptLink, Monitor
from ...models.log_entry import LogEntry
from ..events_debug import append_pipeline_debug
from ..events_router_engine import (
    BROADCAST_TYPE_SLUGS,
    WORKER_BROADCAST_EVENT_TYPE,
    EventsRouter,
)
from ..websocket import websocket_manager
from .context import build_header_from_entities, get_global_prompt_rules
from .spans import entities_json

logger = logging.getLogger(__name__)

_bounded_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="scanscribe-worker")


async def _async_geocode_worker(event_id: str, location: str, monitor_id: int) -> None:
    try:
        geo_region = None
        ev_db = EventsSessionLocal()
        try:
            mon = ev_db.query(Monitor).filter(Monitor.id == monitor_id).first()
            if mon:
                geo_region = mon.geo_region
        finally:
            ev_db.close()

        from ..geocoder_service import resolve_address

        res = await resolve_address(location, geo_region)
        if res:
            ev_db = EventsSessionLocal()
            try:
                ev = ev_db.query(Event).filter(Event.event_id == event_id).first()
                if ev:
                    ev.latitude = res.latitude
                    ev.longitude = res.longitude
                    ev.resolved_address = res.resolved_address
                    ev_db.commit()
                    logger.info(
                        "Geocoded event_id=%s -> (%f, %f) %s",
                        event_id,
                        res.latitude,
                        res.longitude,
                        res.resolved_address,
                    )
                    await websocket_manager.broadcast(
                        {
                            "type": "event_geocoded",
                            "data": {
                                "event_id": event_id,
                                "monitor_id": monitor_id,
                                "location": location,
                                "latitude": res.latitude,
                                "longitude": res.longitude,
                                "resolved_address": res.resolved_address,
                            },
                        }
                    )
            finally:
                ev_db.close()
    except Exception as exc:
        logger.warning("Background geocoding failed for event_id=%s: %s", event_id, exc)


def dispatch_geocoding_for_event(event_id: str, location: Optional[str], monitor_id: int) -> None:
    """Asynchronously geocode location for an event and broadcast coordinate update."""
    if not location or not location.strip() or location.strip().upper() == "N/A":
        return

    try:
        asyncio.get_running_loop()
        from ..task_manager import task_manager

        task_manager.spawn(
            _async_geocode_worker(event_id, location, monitor_id),
            name=f"geocode-{event_id}",
        )
    except RuntimeError:
        def _sync_wrapper():
            asyncio.run(_async_geocode_worker(event_id, location, monitor_id))

        _bounded_executor.submit(_sync_wrapper)


def infer_broadcast_slug_from_transcript(transcript: str) -> Optional[str]:
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


def summarize_event_attachments(
    event: Event,
    events_db,
    logs_db,
    force: bool = False,
) -> Optional[str]:
    """Fetch all chronological attachments for an event and generate an updated summary."""
    try:
        links = (
            events_db.query(EventTranscriptLink)
            .filter(EventTranscriptLink.event_id == event.id)
            .order_by(EventTranscriptLink.linked_at.asc(), EventTranscriptLink.id.asc())
            .all()
        )
        if not links:
            return event.summary

        log_ids = [l.log_entry_id for l in links if l.log_entry_id is not None]
        log_rows = {}
        if log_ids:
            for r in logs_db.query(LogEntry).filter(LogEntry.id.in_(log_ids)).all():
                log_rows[r.id] = r

        attachments = []
        for l in links:
            le = log_rows.get(l.log_entry_id)
            if not le or not le.transcript or not le.transcript.strip():
                continue
            time_str = None
            if le.timestamp:
                try:
                    time_str = le.timestamp.strftime("%H:%M:%S")
                except Exception:
                    pass
            attachments.append(
                {
                    "time": time_str,
                    "talkgroup": le.talkgroup or "",
                    "transcript": le.transcript.strip(),
                }
            )

        if not attachments:
            return event.summary

        global_rules = get_global_prompt_rules(events_db)
        new_summary = EventsRouter.generate_event_summary(
            event_type=event.event_type,
            location=event.resolved_address or event.location,
            units=event.units,
            status_detail=event.status_detail,
            status=event.status,
            attachments=attachments,
            current_summary=event.summary,
            global_rules=global_rules,
        )

        if new_summary and new_summary.strip():
            event.summary = new_summary.strip()
            event.master_last_run_at = datetime.now(timezone.utc)
            events_db.commit()

        return event.summary
    except Exception as e:
        logger.warning(
            "Failed to generate summary for event_id=%s: %s",
            getattr(event, "event_id", ""),
            e,
        )
        return event.summary


def create_event_full(
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
            inferred = infer_broadcast_slug_from_transcript(transcript)
            if inferred:
                bt_slug = inferred

    ner_hdr = build_header_from_entities(entities, transcript)

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
            "event_type": (event_type or "").strip()
            or (ner_hdr.get("event_type") if ner_hdr.get("event_type") != "N/A" else "Incident"),
            "location": (location or "").strip()
            or (ner_hdr.get("location") if ner_hdr.get("location") != "N/A" else None),
            "units": (", ".join(units) if units else None)
            or (ner_hdr.get("units") if ner_hdr.get("units") != "N/A" else None),
            "status_detail": (status_detail or "").strip()
            or (ner_hdr.get("status_detail") if ner_hdr.get("status_detail") != "N/A" else "Active"),
            "original_transcription": transcript,
            "summary": None,
        }
        ev_status = "open"
        closed_at = None

        # Deduplication safeguard: check if a very recent open event of the same type exists
        recent_cutoff = datetime.now(timezone.utc) - timedelta(seconds=120)
        existing_dup = (
            events_db.query(Event)
            .filter(
                Event.monitor_id == monitor_id,
                Event.status == "open",
                Event.created_at >= recent_cutoff,
            )
            .first()
        )
        if existing_dup:
            e1 = (existing_dup.event_type or "").lower()
            e2 = (header["event_type"] or "").lower()
            generic_words = {
                "call",
                "emergency",
                "incident",
                "report",
                "check",
                "in",
                "progress",
                "active",
                "investigation",
                "response",
                "detail",
                "dispatch",
                "alarm",
            }
            e1_words = set(re.findall(r"[a-z0-9]+", e1)) - generic_words
            e2_words = set(re.findall(r"[a-z0-9]+", e2)) - generic_words
            same_type = bool(
                (e1 and e2 and (e1 in e2 or e2 in e1))
                or (e1_words and e2_words and (e1_words & e2_words))
            )
            same_loc = bool(
                existing_dup.location
                and header["location"]
                and existing_dup.location.lower() == header["location"].lower()
            )
            if same_type or same_loc:
                logger.warning(
                    "Events deduplication safeguard: merging into recent open event %s (%s) instead of creating duplicate",
                    existing_dup.event_id,
                    existing_dup.event_type,
                )
                events_db.add(
                    EventTranscriptLink(
                        event_id=existing_dup.id,
                        log_entry_id=log_entry_id,
                        entities_json=entities_json(entities),
                        llm_reason=(debug_reason or "").strip()[:2000] or None,
                    )
                )
                loc_changed = False
                if not existing_dup.location and header["location"]:
                    existing_dup.location = header["location"]
                    loc_changed = True
                if header["units"]:
                    if not existing_dup.units:
                        existing_dup.units = header["units"]
                    else:
                        existing_units = set(
                            u.strip()
                            for u in existing_dup.units.split(",")
                            if u.strip()
                        )
                        for nu in header["units"].split(","):
                            if nu.strip():
                                existing_units.add(nu.strip())
                        existing_dup.units = ", ".join(sorted(existing_units))
                if header["status_detail"] and (
                    not existing_dup.status_detail or existing_dup.status_detail == "Active"
                ):
                    existing_dup.status_detail = header["status_detail"]

                existing_dup.updated_at = datetime.now(timezone.utc)
                events_db.commit()

                logs_db = LogsSessionLocal()
                try:
                    summarize_event_attachments(existing_dup, events_db, logs_db, force=True)
                except Exception as e:
                    logger.warning("Failed updating event summary on deduplication merge: %s", e)
                finally:
                    logs_db.close()

                if loc_changed and existing_dup.location:
                    dispatch_geocoding_for_event(
                        existing_dup.event_id, existing_dup.location, monitor_id
                    )

                span_count = (
                    events_db.query(EventTranscriptLink)
                    .filter(EventTranscriptLink.event_id == existing_dup.id)
                    .count()
                )
                websocket_manager.broadcast_sync(
                    {
                        "type": "event_update",
                        "action": "attach",
                        "data": {
                            "id": existing_dup.id,
                            "event_id": existing_dup.event_id,
                            "monitor_id": monitor_id,
                            "status": existing_dup.status,
                            "event_type": existing_dup.event_type,
                            "location": existing_dup.location,
                            "resolved_address": existing_dup.resolved_address,
                            "units": existing_dup.units,
                            "status_detail": existing_dup.status_detail,
                            "summary": existing_dup.summary,
                            "spans_attached": span_count,
                            "updated_at": (
                                existing_dup.updated_at.isoformat()
                                if existing_dup.updated_at
                                else datetime.now(timezone.utc).isoformat()
                            ),
                        },
                    }
                )
                return existing_dup.event_id

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
        updated_at=datetime.now(timezone.utc),
        closed_at=closed_at,
    )
    events_db.add(event)
    events_db.flush()
    events_db.add(
        EventTranscriptLink(
            event_id=event.id,
            log_entry_id=log_entry_id,
            entities_json=entities_json(entities),
            llm_reason=(debug_reason or "").strip()[:2000] or None,
        )
    )

    try:
        summarize_event_attachments(event, events_db, events_db, force=True)
    except Exception as e:
        logger.warning("Failed initial event summary generation: %s", e)

    events_db.commit()

    dispatch_geocoding_for_event(event_id, header.get("location"), monitor_id)

    websocket_manager.broadcast_sync(
        {
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
                "summary": event.summary,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": (
                    event.updated_at.isoformat()
                    if event.updated_at
                    else datetime.now(timezone.utc).isoformat()
                ),
                "closed_at": closed_at.isoformat() if closed_at else None,
                "spans_attached": 1,
                "talkgroup": talkgroup,
            },
        }
    )

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


# Aliases for backward compatibility
_dispatch_geocoding_for_event = dispatch_geocoding_for_event
_infer_broadcast_slug_from_transcript = infer_broadcast_slug_from_transcript
_create_event_full = create_event_full
