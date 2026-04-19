"""Worker LLM: create vs skip for new incidents (EVT_TYPE spans).

Uses Ollama with tools: get_recent_spans + list_open_events, then JSON decision.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..config import get_settings, incidents_ollama_worker_model
from ..database import LogsSessionLocal
from ..models.log_entry import LogEntry

from .ollama_event_routing import (
    CLASSIFY_BROADCAST_TOOL,
    ROUTING_TOOLS,
    _append_tool_call_reprompt,
    _conversation_has_tool_results,
    _dispatch_tool_calls,
    _message_text_for_decision,
    _ollama_native_chat_request,
    _ollama_openai_completions_request,
    _prepare_assistant_text_for_json,
    _resolve_max_tokens,
    _resolve_reasoning_effort,
    _resolve_timeout,
    _routing_response_message,
    _scan_for_json_object,
)

logger = logging.getLogger(__name__)

WORKER_TOOLS: List[Dict[str, Any]] = [
    ROUTING_TOOLS[0],
    ROUTING_TOOLS[2],
    CLASSIFY_BROADCAST_TOOL,
]

_RAW_LOG_MAX = 12000


WORKER_BROADCAST_EVENT_TYPE = "BROADCAST"

BROADCAST_TYPE_SLUGS = frozenset({
    "storm_warning",
    "cni_drivers",
    "road_debris",
    "attempt_to_locate",
})


def _extract_broadcast_type_from_messages(messages: List[Dict[str, Any]]) -> Optional[str]:
    """Last successful classify_broadcast tool result wins."""
    last: Optional[str] = None
    for m in messages:
        if m.get("role") != "tool":
            continue
        raw = m.get("content") or ""
        if not isinstance(raw, str):
            continue
        try:
            obj = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(obj, dict) or not obj.get("ok"):
            continue
        bt = obj.get("broadcast_type")
        if isinstance(bt, str) and bt.strip().lower() in BROADCAST_TYPE_SLUGS:
            last = bt.strip().lower()
    return last


def _extract_worker_decision_json(content: str) -> Optional[Dict[str, Any]]:
    text = _prepare_assistant_text_for_json(content)
    if not text:
        return None
    return _scan_for_json_object(text, "action", "create", "event_type", "broadcast_type")


def _decision_tuple_from_obj(
    decision: Dict[str, Any],
) -> Optional[Tuple[bool, str, Optional[str], Optional[str]]]:
    """Returns (should_create, reason, worker_event_type, broadcast_type_slug)."""
    reason = str(decision.get("reason") or "").strip()[:500]
    bt_raw = decision.get("broadcast_type")
    bt_json: Optional[str] = None
    if isinstance(bt_raw, str) and bt_raw.strip().lower() in BROADCAST_TYPE_SLUGS:
        bt_json = bt_raw.strip().lower()

    et_raw = decision.get("event_type")
    worker_et: Optional[str] = None
    if isinstance(et_raw, str) and et_raw.strip().upper() == WORKER_BROADCAST_EVENT_TYPE:
        worker_et = WORKER_BROADCAST_EVENT_TYPE
    if worker_et == WORKER_BROADCAST_EVENT_TYPE:
        return (True, reason, WORKER_BROADCAST_EVENT_TYPE, bt_json)
    act = (decision.get("action") or "").lower().strip()
    if act == "create":
        return (True, reason, None, None)
    if act == "skip":
        return (False, reason, None, None)
    if "create" in decision:
        c = decision.get("create")
        if isinstance(c, bool):
            return (c, reason, None, None)
        if isinstance(c, str):
            return (c.lower() in ("true", "1", "yes"), reason, None, None)
    return None


def worker_should_create_event(
    *,
    events_db: Session,
    monitor_id: int,
    monitor_name: str,
    talkgroup: str,
    transcript: str,
    entities: Dict[str, List[str]],
    log_entry_id: int,
    open_incidents: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Optional[bool], str, str, Optional[str], Optional[str]]:
    """
    Returns (decision, message, llm_raw_json, worker_event_type, broadcast_type).
    broadcast_type: storm_warning | cni_drivers | road_debris | attempt_to_locate (from tool or JSON).
    """
    settings = get_settings()
    ollama_cfg = getattr(settings.config, "incidents_ollama", None)
    pipe = settings.config.events_pipeline
    if not ollama_cfg or not getattr(ollama_cfg, "enabled", False):
        err = "incidents_ollama is disabled in config"
        logger.warning("Worker: %s (monitor_id=%s log_entry_id=%s)", err, monitor_id, log_entry_id)
        return (None, err, "", None, None)

    return _worker_tool_loop_path(
        events_db=events_db,
        monitor_id=monitor_id,
        monitor_name=monitor_name,
        talkgroup=talkgroup,
        transcript=transcript,
        entities=entities,
        log_entry_id=log_entry_id,
        open_incidents=open_incidents,
        ollama_cfg=ollama_cfg,
        pipe=pipe,
    )


def _worker_tool_loop_path(
    *,
    events_db: Session,
    monitor_id: int,
    monitor_name: str,
    talkgroup: str,
    transcript: str,
    entities: Dict[str, List[str]],
    log_entry_id: int,
    open_incidents: Optional[List[Dict[str, Any]]],
    ollama_cfg: Any,
    pipe: Any,
) -> Tuple[Optional[bool], str, str, Optional[str], Optional[str]]:
    base_url = (ollama_cfg.base_url or "http://localhost:11434").rstrip("/")
    model = incidents_ollama_worker_model(ollama_cfg)
    timeout = _resolve_timeout(ollama_cfg)
    max_rounds = int(getattr(pipe, "llm_routing_max_tool_rounds", 12) or 12)
    use_openai_api = bool(getattr(pipe, "llm_routing_openai_api", True))
    routing_max_tokens = _resolve_max_tokens(pipe)
    routing_reasoning_effort = _resolve_reasoning_effort(pipe)
    log_raw = bool(getattr(pipe, "llm_routing_log_raw", False))

    system = (
        "You are a public-safety incident gate. Your only job is to decide "
        "if a new incident should be created for this monitor.\n"
        "You MUST call tools before deciding.\n"
        "STEP 1: call get_recent_spans to see recent activity on this monitor.\n"
        "STEP 2: call list_open_events to see if a matching incident is already open.\n"
        "STEP 3: output ONLY this JSON (nothing else, never echo the context):\n"
        '{"action":"create"|"skip","reason":"<10 words max>","event_type":null|"BROADCAST",'
        '"broadcast_type":null|storm_warning|cni_drivers|road_debris|attempt_to_locate}\n\n'
        "BROADCAST (non-incident traffic): If the transcript is primarily one of these, "
        "you MUST output create with event_type exactly \"BROADCAST\", a short reason, AND "
        "broadcast_type set to exactly one slug: storm_warning | cni_drivers | road_debris | "
        "attempt_to_locate (pick the best match). "
        "Alternatively call the classify_broadcast tool with that slug before your final JSON. "
        "Do not emit BROADCAST with broadcast_type null.\n"
        "Do not treat these as normal ongoing incidents; they are logged and closed immediately:\n"
        "- Storm warnings / severe weather alerts → storm_warning\n"
        "- CNI driver traffic → cni_drivers\n"
        "- Road debris calls → road_debris\n"
        "- Attempt to locate (ATL) → attempt_to_locate\n\n"
        "Example: "
        '{"action":"create","reason":"CNI highway traffic","event_type":"BROADCAST","broadcast_type":"cni_drivers"}\n\n'
        "create (normal): evt_type is a genuine new incident not already open; use event_type null or omit it.\n"
        "if transcript is VAD_REJECTED (or equivalent system/VAD marker): always skip.\n"
        "skip if: duplicate dispatch, continuation of open incident, "
        "test traffic, or ambiguous.\n"
        "Do not narrate. Do not explain. Do not repeat monitor/transcript fields. "
        "Output only that JSON after tools."
    )

    open_inc = open_incidents or []
    incident_time_str = ""
    system_time_str = ""
    logs_db = LogsSessionLocal()
    try:
        row = logs_db.query(LogEntry.created_at, LogEntry.timestamp).filter(
            LogEntry.id == log_entry_id, LogEntry.is_deleted == False
        ).first()
    finally:
        logs_db.close()
    if row:
        ca, ts = row[0], row[1]
        if ts is not None:
            try:
                incident_time_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            except Exception:
                incident_time_str = str(ts)
        if ca is not None:
            try:
                system_time_str = ca.isoformat() if hasattr(ca, "isoformat") else str(ca)
            except Exception:
                system_time_str = str(ca)

    user_content = (
        "After tool results, reply with ONLY one line of JSON: "
        '{"action":"create"|"skip","reason":"...","event_type":null|"BROADCAST",'
        '"broadcast_type":null|storm_warning|cni_drivers|road_debris|attempt_to_locate}\n\n'
        f"Monitor: {monitor_name} (internal id {monitor_id})\n"
        f"Talkgroup: {talkgroup}\n"
        f"log_entry_id: {log_entry_id}\n"
        f"incident_time (log metadata): {incident_time_str or '—'}\n"
        f"system_time (log row stored in DB): {system_time_str or '—'}\n"
        f"Transcript: {transcript}\n"
        f"NER EVT_TYPE: {json.dumps(entities.get('EVT_TYPE', []), ensure_ascii=False)}\n"
        f"NER (all): {json.dumps(entities, ensure_ascii=False)}\n"
        f"Open incidents on this monitor: {json.dumps(open_inc, ensure_ascii=False)}\n"
        "Hint: get_recent_spans accepts all_talkgroups:true to scan the whole monitor."
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    reprompted_for_tools = False

    for round_i in range(max_rounds):
        if use_openai_api:
            data = _ollama_openai_completions_request(
                base_url, model, messages, WORKER_TOOLS, timeout,
                max_tokens=routing_max_tokens,
                reasoning_effort=routing_reasoning_effort,
                tool_choice="auto" if _conversation_has_tool_results(messages) else "required",
            )
        else:
            data = _ollama_native_chat_request(
                base_url, model, messages, WORKER_TOOLS, timeout, max_tokens=routing_max_tokens,
            )
        if not data:
            err = (
                f"Ollama returned no response (timeout or unreachable); "
                f"model={model!r} base={base_url!r} round={round_i}"
            )
            logger.warning("Worker: %s monitor_id=%s log_entry_id=%s", err, monitor_id, log_entry_id)
            return (None, err, "", None, None)

        try:
            llm_raw_json = json.dumps(data, ensure_ascii=False, default=str)
        except TypeError:
            llm_raw_json = str(data)

        if log_raw:
            logger.info(
                "Worker LLM raw round=%s len=%s: %s",
                round_i,
                len(llm_raw_json),
                llm_raw_json[:_RAW_LOG_MAX] + ("…" if len(llm_raw_json) > _RAW_LOG_MAX else ""),
            )

        resp_msg = _routing_response_message(data, use_openai_api)
        if _dispatch_tool_calls(
            messages, resp_msg, use_openai_api, events_db, monitor_id, talkgroup, log_entry_id
        ):
            continue

        content_raw = _message_text_for_decision(resp_msg)
        if log_raw:
            logger.info(
                "Worker LLM final text round=%s len=%s: %s",
                round_i, len(content_raw),
                content_raw[:_RAW_LOG_MAX] + ("…" if len(content_raw) > _RAW_LOG_MAX else ""),
            )
        decision = _extract_worker_decision_json(content_raw)
        if not decision:
            if not _conversation_has_tool_results(messages) and not reprompted_for_tools:
                reprompted_for_tools = True
                _append_tool_call_reprompt(messages, "worker_gate requires tool reads before deciding")
                continue
            preview = (content_raw[:800] + "…") if len(content_raw) > 800 else content_raw
            err = f"no valid JSON decision (round {round_i}): {preview}"
            logger.warning("Worker: %s monitor_id=%s log_entry_id=%s", err[:500], monitor_id, log_entry_id)
            return (None, err[:2000], llm_raw_json, None, None)

        out = _decision_tuple_from_obj(decision)
        if out is None:
            err = f"invalid action in model output: {decision!r}"
            logger.warning("Worker: %s monitor_id=%s log_entry_id=%s", err, monitor_id, log_entry_id)
            return (None, err[:2000], llm_raw_json, None, None)
        bt_tool = _extract_broadcast_type_from_messages(messages)
        bt = bt_tool or out[3]
        return (out[0], out[1], llm_raw_json, out[2], bt)

    err = f"max tool rounds ({max_rounds}) exceeded without a decision"
    logger.warning("Worker: %s monitor_id=%s log_entry_id=%s", err, monitor_id, log_entry_id)
    return (None, err, "", None, None)
