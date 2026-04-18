"""Master LLM normalizes Event header fields (event_type, location, units, status_detail) from linked transcripts.

NER is not written to the event row; optional NER hints are passed to the model only as context.
"""
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from ..config import get_settings, incidents_ollama_master_model
from ..database import EventsSessionLocal, LogsSessionLocal
from ..models.event import Event, EventTranscriptLink
from ..models.log_entry import LogEntry
from .events_common import merge_entities_from_link_json_strings
from .events_debug import append_ner as debug_append_ner
from .ollama_event_routing import (
    _message_text_for_decision,
    _ollama_native_chat_request,
    _ollama_openai_completions_request,
    _prepare_assistant_text_for_json,
    _resolve_reasoning_effort,
    _resolve_timeout,
    _routing_response_message,
    _scan_for_json_object,
    _scan_for_json_object_from_end,
    _scan_for_json_object_near_event_type_key,
)

logger = logging.getLogger(__name__)

# Enough room for models that put JSON after long reasoning/thinking blocks.
_HEADER_MAX_TOKENS = 8192


def _aggregate_ner_hints(links: List[EventTranscriptLink]) -> str:
    merged = merge_entities_from_link_json_strings([link.entities_json for link in links])
    if not merged:
        return ""
    lines = []
    for k in sorted(merged.keys()):
        seen = set()
        parts = []
        for p in merged[k]:
            low = p.lower()
            if low not in seen:
                seen.add(low)
                parts.append(p)
        lines.append(f"- {k}: {', '.join(parts)}")
    return "\n".join(lines)


def _run_master_header_normalize(event_db_id: int, cfg: Any, pipe: Any) -> None:
    base_url = (cfg.base_url or "http://localhost:11434").rstrip("/")
    model = incidents_ollama_master_model(cfg)
    timeout = _resolve_timeout(cfg)
    use_openai_api = bool(getattr(pipe, "llm_routing_openai_api", True))
    reasoning_effort = _resolve_reasoning_effort(pipe)
    max_tok = getattr(pipe, "llm_routing_max_tokens", None)
    try:
        max_tokens = int(max_tok) if max_tok is not None and int(max_tok) > 0 else _HEADER_MAX_TOKENS
    except (TypeError, ValueError):
        max_tokens = _HEADER_MAX_TOKENS
    max_tokens = min(max_tokens, _HEADER_MAX_TOKENS)

    system = (
        "You normalize public-safety incident header fields from linked radio transcripts.\n"
        "Do not write thinking steps, analysis, or markdown. Your reply must be ONLY one JSON object; "
        "the first non-whitespace character must be '{'.\n"
        "Output ONLY a single JSON object (no markdown, no commentary) with exactly these string keys:\n"
        '  "event_type" — 2–6 words, Title Case incident noun phrase (e.g. Structure Fire, Traffic Stop).\n'
        '  "location" — primary street address or named place; deduplicate; empty string if unknown.\n'
        '  "units" — comma-separated units/agencies as heard (e.g. Engine 4, 12U-1771); empty string if unknown.\n'
        '  "status_detail" — short operational status (e.g. En Route, On Scene, Clear); empty string if unknown.\n'
        "Use transcript lines as the source of truth. A separate NER hints block may be noisy — use it only to "
        "disambiguate when it agrees with audio. Do not invent facts.\n"
        "Use empty string \"\" for any field you cannot support from the transcripts."
    )

    events_db = EventsSessionLocal()
    logs_db = LogsSessionLocal()
    ev: Optional[Event] = None
    links: List[EventTranscriptLink] = []
    t0 = 0.0
    debug_raw_llm = ""
    try:
        ev = events_db.query(Event).filter(Event.id == event_db_id).first()
        if not ev:
            return
        links = (
            events_db.query(EventTranscriptLink)
            .filter(EventTranscriptLink.event_id == event_db_id)
            .order_by(EventTranscriptLink.linked_at.asc())
            .all()
        )
        if not links:
            return
        t0 = time.perf_counter()

        lines: List[str] = []
        span_times: List[Any] = []
        log_ids = [link.log_entry_id for link in links if link.log_entry_id is not None]
        log_rows = (
            logs_db.query(LogEntry)
            .filter(LogEntry.id.in_(log_ids), LogEntry.is_deleted == False)
            .all()
            if log_ids
            else []
        )
        log_by_id = {le.id: le for le in log_rows}
        for link in links:
            le = log_by_id.get(link.log_entry_id)
            if not le:
                continue
            if le.timestamp is not None:
                span_times.append(le.timestamp)
            tg = le.talkgroup or "N/A"
            ts = le.timestamp.strftime("%H:%M:%S") if le.timestamp else ""
            tx = (le.transcript or "").strip()
            if tx:
                lines.append(f"- {ts} | {tg} | {tx}")

        if not lines:
            logger.warning(
                "Master header: no non-empty transcripts for event_db_id=%s; trying NER-only header",
                event_db_id,
            )

        incident_at = min(span_times) if span_times else None
        incident_iso = (
            incident_at.isoformat() if incident_at is not None and hasattr(incident_at, "isoformat") else ""
        )
        system_iso = ev.created_at.isoformat() if ev.created_at else ""
        times_block = (
            f"Incident time (earliest linked log): {incident_iso or '—'}\n"
            f"System time (event record created): {system_iso or '—'}\n\n"
        )
        ner_block = _aggregate_ner_hints(links)
        ner_section = (
            f"NER hints (verify against transcripts; may be fragmented):\n{ner_block}\n\n"
            if ner_block
            else ""
        )
        transcript_block = (
            "Transcripts (time | talkgroup | text):\n" + "\n".join(lines)
            if lines
            else "(No transcript text on linked logs — use NER hints only if present.)\n"
        )
        user_content = times_block + ner_section + transcript_block

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]

        et, loc, units, sd = "", "", "", ""
        data: Optional[Dict[str, Any]] = None
        if lines or ner_block:
            if use_openai_api:
                # omit_response_format=True: reasoning models (Qwen3, DeepSeek-R1) separate thinking
                # into the `reasoning` field and emit clean JSON in `content`. json_object mode
                # forces thinking inline into content, breaking JSON extraction.
                data = _ollama_openai_completions_request(
                    base_url,
                    model,
                    messages,
                    None,
                    timeout,
                    max_tokens=max_tokens,
                    reasoning_effort=reasoning_effort,
                    omit_response_format=True,
                )
            else:
                data = _ollama_native_chat_request(
                    base_url, model, messages, None, timeout, max_tokens=max_tokens, format_json=True,
                )

        if not data:
            logger.warning("Master header: no Ollama response event_db_id=%s", event_db_id)
        else:
            msg = _routing_response_message(data, use_openai_api)
            raw = _message_text_for_decision(msg).strip()
            if not raw:
                raw = (msg.get("content") or "").strip()
            if raw:
                debug_raw_llm = raw[:12000]
            if not raw:
                logger.warning(
                    "Master header: empty model text event_db_id=%s (check max_tokens / reasoning fields)",
                    event_db_id,
                )
            else:
                cleaned = _prepare_assistant_text_for_json(raw) or raw
                _keys = ("event_type", "location", "units", "status_detail")
                # Prefer object whose first key is event_type (thinking blocks often contain stray `{`).
                result = _scan_for_json_object_near_event_type_key(cleaned, *_keys)
                if not result:
                    result = _scan_for_json_object_from_end(cleaned, *_keys)
                if not result:
                    result = _scan_for_json_object(cleaned, *_keys)
                if not result:
                    try:
                        parsed = json.loads(cleaned)
                        result = parsed if isinstance(parsed, dict) else None
                    except json.JSONDecodeError:
                        result = None
                if not isinstance(result, dict):
                    logger.info(
                        "Master header: JSON parse failed event_db_id=%s (NER fallback may apply); head=%r",
                        event_db_id,
                        (raw[:240] + "…") if len(raw) > 240 else raw,
                    )
                    result = {}
                else:
                    et = (result.get("event_type") or "").strip()[:255]
                    loc = (result.get("location") or "").strip()[:500]
                    units = (result.get("units") or "").strip()[:4000]
                    sd = (result.get("status_detail") or "").strip()[:255]

        # Fill any still-empty fields from merged NER on links (legacy Worker header logic).
        merged_ent = merge_entities_from_link_json_strings([link.entities_json for link in links])
        if merged_ent and (not et or not loc or not units or not sd):
            from .events_worker import _build_header_from_entities

            combined_tx = "\n".join(
                (ln.split("|", 2)[2] if "|" in ln else ln).strip()
                for ln in lines
                if ln.strip().startswith("-")
            )[:8000]
            fb = _build_header_from_entities(merged_ent, combined_tx or "")
            if not et and fb.get("event_type") and fb["event_type"] != "N/A":
                et = fb["event_type"][:255]
            if not loc and fb.get("location") and fb["location"] != "N/A":
                loc = fb["location"][:500]
            if not units and fb.get("units") and fb["units"] != "N/A":
                units = fb["units"][:4000]
            if not sd and fb.get("status_detail") and fb["status_detail"] != "N/A":
                sd = fb["status_detail"][:255]
            if et or loc or units:
                logger.info(
                    "Master header: NER top-up event_db_id=%s type=%r loc=%r",
                    event_db_id,
                    et[:40] if et else "",
                    loc[:40] if loc else "",
                )

        ev2 = events_db.query(Event).filter(Event.id == event_db_id).first()
        if not ev2:
            return
        ev2.event_type = et or None
        ev2.location = loc or None
        ev2.units = units or None
        ev2.status_detail = sd or None
        events_db.commit()
        logger.info(
            "Master header: updated event_id=%s type=%r location=%r",
            ev2.event_id,
            et,
            loc[:80] if loc else "",
        )
        duration_ms = (time.perf_counter() - t0) * 1000 if t0 else 0.0
        combined_tx = "\n".join(
            (ln.split("|", 2)[2] if "|" in ln else ln).strip()
            for ln in lines
            if ln.strip().startswith("-")
        )[:4000]
        if debug_raw_llm.strip():
            llm_debug = debug_raw_llm[:12000]
        else:
            llm_debug = json.dumps(
                {"event_type": et, "location": loc, "units": units, "status_detail": sd},
                ensure_ascii=False,
            )[:12000]
        try:
            debug_append_ner(
                ev.monitor_id,
                links[0].log_entry_id,
                "master_header_normalize",
                ev2.event_id,
                duration_ms,
                merged_ent,
                "",
                [],
                combined_tx or (ev.original_transcription or "")[:4000],
                llm_debug,
            )
        except Exception as ex:
            logger.debug("Master header: debug log skipped: %s", ex)
    except Exception as e:
        logger.warning("Master header: failed event_db_id=%s: %s", event_db_id, e)
        if ev is not None and links:
            try:
                duration_ms = (time.perf_counter() - t0) * 1000 if t0 else 0.0
                merged_ent = merge_entities_from_link_json_strings(
                    [link.entities_json for link in links]
                )
                debug_append_ner(
                    ev.monitor_id,
                    links[0].log_entry_id,
                    "master_header_fail",
                    ev.event_id,
                    duration_ms,
                    merged_ent,
                    str(e)[:500],
                    [],
                    "",
                    debug_raw_llm[:12000] if debug_raw_llm else "",
                )
            except Exception as ex:
                logger.debug("Master header: fail debug log skipped: %s", ex)
    finally:
        events_db.close()
        logs_db.close()


def schedule_master_header_normalize(event_db_id: int) -> None:
    """Background: fill header fields then chain summary in the same thread (no lock contention)."""
    settings = get_settings()
    cfg = getattr(settings.config, "incidents_ollama", None)
    pipe = settings.config.events_pipeline
    if not cfg or not getattr(cfg, "enabled", False):
        return
    if not getattr(pipe, "master_header_normalize", True):
        return

    def _run() -> None:
        _run_master_header_normalize(event_db_id, cfg, pipe)
        # Chain summary in same thread so it always runs after header, never races it.
        from .event_summary_ollama import _maybe_run_summary
        _maybe_run_summary(event_db_id, cfg, pipe)

    threading.Thread(target=_run, daemon=True).start()
