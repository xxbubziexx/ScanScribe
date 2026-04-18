"""Event summary via the same Ollama stack as the Master LLM (chat completions or native /api/chat).

Runs in background when attached spans >= summary_trigger_spans.
"""
import logging
import threading
from typing import Any, List

from ..config import get_settings, incidents_ollama_master_model
from ..database import EventsSessionLocal, LogsSessionLocal
from ..models.event import Event, EventTranscriptLink
from ..models.log_entry import LogEntry
from .ollama_event_routing import (
    _call_master_chat_plain,
    _message_text_for_decision,
    _resolve_reasoning_effort,
    _resolve_timeout,
    _routing_response_message,
)

logger = logging.getLogger(__name__)

_SUMMARY_MAX_TOKENS = 1024


def _build_event_summary_user_content(
    entries: List[dict],
    *,
    incident_time: str = "",
    system_time: str = "",
) -> str:
    """User message body: times + transcript lines."""
    times_block = ""
    if incident_time or system_time:
        times_block = (
            f"Incident time (earliest linked log metadata): {incident_time or '—'}\n"
            f"System time (event record created in DB): {system_time or '—'}\n\n"
        )
    header = times_block + "Transcripts (time | talkgroup | text):\n"
    lines = []
    for e in entries:
        t = e.get("time") or ""
        tg = e.get("talkgroup") or "N/A"
        text = (e.get("transcript") or "").strip()
        if text:
            lines.append(f"- {t} | {tg} | {text}")
    if not lines:
        return header + "(No transcript text.)\n"
    return header + "\n".join(lines) + "\n"


def _run_event_summary(event_db_id: int, cfg: Any, pipe: Any) -> None:
    base_url = (cfg.base_url or "http://localhost:11434").rstrip("/")
    model = incidents_ollama_master_model(cfg)
    timeout = _resolve_timeout(cfg)
    use_openai_api = bool(getattr(pipe, "llm_routing_openai_api", True))
    reasoning_effort = _resolve_reasoning_effort(pipe)
    max_tok = getattr(pipe, "llm_routing_max_tokens", None)
    try:
        max_tokens = int(max_tok) if max_tok is not None and int(max_tok) > 0 else _SUMMARY_MAX_TOKENS
    except (TypeError, ValueError):
        max_tokens = _SUMMARY_MAX_TOKENS

    system = (
        "You summarize public-safety radio incident threads for dispatch awareness.\n"
        "Use 2-4 short sentences. Include: incident type, location, units, and key updates. "
        "Do NOT invent facts.\n\n"
        "On the last line, write exactly RECOMMEND_CLOSE or RECOMMEND_OPEN "
        "(RECOMMEND_CLOSE only if the incident appears resolved, e.g. units cleared, scene closed)."
    )

    events_db = EventsSessionLocal()
    logs_db = LogsSessionLocal()
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
        log_ids = [l.log_entry_id for l in links if l.log_entry_id is not None]
        if not log_ids:
            return
        log_rows = (
            logs_db.query(LogEntry)
            .filter(LogEntry.id.in_(log_ids), LogEntry.is_deleted == False)
            .all()
        )
        log_by_id = {le.id: le for le in log_rows}
        entries = []
        span_times = []
        for lid in log_ids:
            le = log_by_id.get(lid)
            if not le:
                continue
            if le.timestamp is not None:
                span_times.append(le.timestamp)
            entries.append({
                "time": le.timestamp.strftime("%H:%M:%S") if le.timestamp else "",
                "talkgroup": le.talkgroup or "N/A",
                "transcript": le.transcript or "",
            })
        if not entries:
            return
        incident_at = min(span_times) if span_times else None
        incident_iso = (
            incident_at.isoformat() if incident_at is not None and hasattr(incident_at, "isoformat") else ""
        )
        system_iso = ev.created_at.isoformat() if ev.created_at else ""
        user_content = _build_event_summary_user_content(
            entries, incident_time=incident_iso, system_time=system_iso
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]

        data = _call_master_chat_plain(
            base_url,
            model,
            messages,
            timeout,
            max_tokens=max_tokens,
            use_openai_api=use_openai_api,
            reasoning_effort=reasoning_effort,
        )
        if not data:
            logger.debug("Event summary: no response from Ollama (Master path) event_db_id=%s", event_db_id)
            return

        msg = _routing_response_message(data, use_openai_api)
        raw = _message_text_for_decision(msg).strip()

        if raw:
            recommend_close = "RECOMMEND_CLOSE" in raw.upper()
            summary_lines = [
                ln for ln in raw.strip().split("\n")
                if ln.strip().upper() not in ("RECOMMEND_CLOSE", "RECOMMEND_OPEN")
            ]
            ev.summary = "\n".join(summary_lines).strip() or raw
            ev.close_recommendation = recommend_close
            events_db.commit()
            logger.info(
                "Events: Master LLM summary updated for event_id=%s (recommend_close=%s)",
                ev.event_id, recommend_close,
            )
    except Exception as e:
        logger.warning("Events: Ollama summary failed for event_db_id=%s: %s", event_db_id, e)
    finally:
        events_db.close()
        logs_db.close()


def _maybe_run_summary(event_db_id: int, cfg: Any, pipe: Any) -> None:
    """Run summary if span count meets trigger. Called inline (same thread) after header normalize."""
    trigger = getattr(pipe, "summary_trigger_spans", 0) or 0
    if trigger <= 0:
        return
    from sqlalchemy import func as sqlfunc
    db = EventsSessionLocal()
    try:
        count = db.query(sqlfunc.count(EventTranscriptLink.id)).filter(
            EventTranscriptLink.event_id == event_db_id
        ).scalar() or 0
    finally:
        db.close()
    if count >= trigger:
        _run_event_summary(event_db_id, cfg, pipe)


def schedule_event_summary(event_db_id: int) -> None:
    """Schedule background summary for event. No-op if Ollama disabled."""
    settings = get_settings()
    cfg = getattr(settings.config, "incidents_ollama", None)
    pipe = settings.config.events_pipeline
    if not cfg or not getattr(cfg, "enabled", False):
        return
    threading.Thread(target=_run_event_summary, args=(event_db_id, cfg, pipe), daemon=True).start()
