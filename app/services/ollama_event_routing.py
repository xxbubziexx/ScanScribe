"""
LLM-based event routing via Ollama + tools (read-only DB lookups).
Default: OpenAI-compatible POST {base}/v1/chat/completions (better tool calling on many models).
Optional: native POST {base}/api/chat (events_pipeline.llm_routing_openai_api: false).
"""
from __future__ import annotations

import json
import logging
import re
import socket
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import get_settings, incidents_ollama_master_model
from ..database import LogsSessionLocal
from ..models.event import Event, EventTranscriptLink, SpanStore
from ..models.log_entry import LogEntry

logger = logging.getLogger(__name__)

_RAW_LOG_MAX = 12000
_ROUTING_REASONING_EFFORTS = frozenset({"none", "low", "medium", "high"})


# --- Config resolution helpers (shared with ollama_worker) ---

def _resolve_timeout(ollama_cfg: Any) -> float:
    return float(getattr(ollama_cfg, "timeout_seconds", 120) or 120)


def _resolve_max_tokens(pipe: Any) -> Optional[int]:
    _mt = getattr(pipe, "llm_routing_max_tokens", None)
    try:
        v = int(_mt) if _mt is not None else None
    except (TypeError, ValueError):
        v = None
    return v if (v is not None and v > 0) else None


def _resolve_reasoning_effort(pipe: Any) -> Optional[str]:
    """Default to 'low' when unset: reasoning models (Qwen3, DeepSeek-R1) otherwise burn
    the entire max_tokens budget on chain-of-thought and never emit the final JSON/answer."""
    _re = getattr(pipe, "llm_routing_reasoning_effort", None)
    if isinstance(_re, str) and _re.strip():
        e = _re.strip().lower()
        if e in _ROUTING_REASONING_EFFORTS:
            return e
        logger.warning(
            "Invalid events_pipeline.llm_routing_reasoning_effort=%r (expected one of %s); falling back to 'low'",
            _re,
            ", ".join(sorted(_ROUTING_REASONING_EFFORTS)),
        )
    return "low"


def _seconds_ago(ts: Any) -> Optional[int]:
    """Return whole seconds between ts and now (UTC). Handles naive and aware datetimes."""
    if ts is None:
        return None
    try:
        now = datetime.now(timezone.utc)
        if hasattr(ts, "tzinfo") and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max(0, int((now - ts).total_seconds()))
    except Exception:
        return None


ROUTING_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_open_events",
            "description": (
                "Read-only: list open incidents for the current monitor. Does not create anything. "
                "Use to pick attach/close targets. "
                "Returns event_id, type, location, units, span count, talkgroups, "
                "incident_at (earliest linked log timestamp — when the incident happened), "
                "created_at (system time when the event row was recorded), last_span_at."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max events (default 20, max 30)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_event_snapshot",
            "description": (
                "Load one open incident by its public event_id string. "
                "Includes incident_at (earliest linked log time), created_at (system time when the event row was stored), "
                "header fields, and short previews of linked transcripts (same monitor only)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "Public event id (short hex string from list_open_events)",
                    },
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_spans",
            "description": (
                "Last N rows from span_store for this monitor (transcript preview + NER columns when present; "
                "NER-empty spans are included too). Newest last; default is current talkgroup, "
                "or set all_talkgroups:true for the whole monitor. Read-only."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max rows (default 5, max 10)",
                    },
                    "exclude_log_entry_id": {
                        "type": "integer",
                        "description": "Optional: omit this log_entry_id from results (e.g. current span)",
                    },
                    "all_talkgroups": {
                        "type": "boolean",
                        "description": "If true, recent spans across all talkgroups on this monitor (not only current TG)",
                    },
                },
            },
        },
    },
]


def _tool_list_open_events(
    events_db: Session,
    monitor_id: int,
    limit: int,
) -> Dict[str, Any]:
    limit = max(1, min(int(limit or 20), 30))
    rows = (
        events_db.query(Event)
        .filter(Event.monitor_id == monitor_id, Event.status == "open")
        .order_by(Event.created_at.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return {"events": [], "count": 0}

    event_ids = [e.id for e in rows]
    all_links = (
        events_db.query(EventTranscriptLink)
        .filter(EventTranscriptLink.event_id.in_(event_ids))
        .all()
    )
    links_by_event: Dict[int, list] = defaultdict(list)
    for lnk in all_links:
        links_by_event[lnk.event_id].append(lnk)

    all_log_ids = list({lnk.log_entry_id for lnk in all_links})
    log_info: Dict[int, Tuple[Optional[str], Any]] = {}
    if all_log_ids:
        logs_db = LogsSessionLocal()
        try:
            for r in logs_db.query(LogEntry.id, LogEntry.talkgroup, LogEntry.timestamp).filter(
                LogEntry.id.in_(all_log_ids), LogEntry.is_deleted == False
            ).all():
                log_info[r[0]] = (r[1], r[2])
        finally:
            logs_db.close()

    out: List[Dict[str, Any]] = []
    for e in rows:
        links = links_by_event[e.id]
        tgs = sorted({
            log_info[lnk.log_entry_id][0]
            for lnk in links
            if lnk.log_entry_id in log_info and log_info[lnk.log_entry_id][0]
        })
        timestamps = [
            log_info[lnk.log_entry_id][1]
            for lnk in links
            if lnk.log_entry_id in log_info and log_info[lnk.log_entry_id][1] is not None
        ]
        last_span_ts = max(timestamps) if timestamps else None
        first_span_ts = min(timestamps) if timestamps else None
        out.append({
            "event_id": e.event_id,
            "event_type": e.event_type,
            "location": e.location,
            "units": e.units,
            "spans_attached": len(links),
            "talkgroups": ", ".join(tgs),
            "incident_at": first_span_ts.isoformat() if first_span_ts and hasattr(first_span_ts, "isoformat") else (str(first_span_ts) if first_span_ts else None),
            "seconds_since_incident": _seconds_ago(first_span_ts),
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "seconds_since_created": _seconds_ago(e.created_at),
            "last_span_at": last_span_ts.isoformat() if last_span_ts and hasattr(last_span_ts, "isoformat") else (str(last_span_ts) if last_span_ts else None),
            "seconds_since_last_span": _seconds_ago(last_span_ts),
        })
    return {"events": out, "count": len(out)}


def _tool_get_event_snapshot(
    events_db: Session,
    monitor_id: int,
    event_id: str,
) -> Dict[str, Any]:
    e = events_db.query(Event).filter(Event.event_id == event_id).first()
    if not e or e.monitor_id != monitor_id:
        return {"error": "event not found or wrong monitor"}
    if e.status != "open":
        return {"error": "event is not open"}
    links = (
        events_db.query(EventTranscriptLink)
        .filter(EventTranscriptLink.event_id == e.id)
        .order_by(EventTranscriptLink.linked_at.asc())
        .all()
    )
    all_link_log_ids = [lnk.log_entry_id for lnk in links if lnk.log_entry_id is not None]
    recent_links = links[-8:]
    recent_log_ids = [lnk.log_entry_id for lnk in recent_links if lnk.log_entry_id is not None]
    incident_ts: Optional[Any] = None
    log_by_id: Dict[int, LogEntry] = {}
    if all_link_log_ids or recent_log_ids:
        logs_db = LogsSessionLocal()
        try:
            if all_link_log_ids:
                ts_rows = logs_db.query(LogEntry.timestamp).filter(
                    LogEntry.id.in_(all_link_log_ids), LogEntry.is_deleted == False
                ).all()
                tss = [r[0] for r in ts_rows if r[0] is not None]
                if tss:
                    incident_ts = min(tss)
            if recent_log_ids:
                log_rows = (
                    logs_db.query(LogEntry)
                    .filter(LogEntry.id.in_(recent_log_ids), LogEntry.is_deleted == False)
                    .all()
                )
                log_by_id = {le.id: le for le in log_rows}
        finally:
            logs_db.close()
    spans: List[Dict[str, Any]] = []
    for link in recent_links:
        le = log_by_id.get(link.log_entry_id)
        if not le:
            continue
        ent = None
        if link.entities_json:
            try:
                ent = json.loads(link.entities_json)
            except (json.JSONDecodeError, TypeError):
                ent = None
        text = (le.transcript or "").strip()
        if len(text) > 220:
            text = text[:220] + "…"
        spans.append({
            "log_entry_id": le.id,
            "talkgroup": le.talkgroup,
            "time": le.timestamp.isoformat() if le.timestamp else None,
            "transcript_preview": text,
            "ner_entities": ent,
        })
    span_timestamps = [
        s["time"] for s in spans if s.get("time")
    ]
    last_span_ts_str = max(span_timestamps) if span_timestamps else None
    last_span_ts = None
    if last_span_ts_str:
        try:
            last_span_ts = datetime.fromisoformat(last_span_ts_str)
        except (ValueError, TypeError):
            pass
    return {
        "event_id": e.event_id,
        "event_type": e.event_type,
        "location": e.location,
        "units": e.units,
        "status_detail": e.status_detail,
        "summary": (e.summary or "")[:500],
        "incident_at": incident_ts.isoformat() if incident_ts and hasattr(incident_ts, "isoformat") else (str(incident_ts) if incident_ts else None),
        "seconds_since_incident": _seconds_ago(incident_ts),
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "seconds_since_created": _seconds_ago(e.created_at),
        "recent_spans": spans,
        "total_spans": len(links),
        "seconds_since_last_span": _seconds_ago(last_span_ts),
    }


def _tool_get_recent_spans(
    events_db: Session,
    monitor_id: int,
    talkgroup: str,
    limit: int,
    exclude_log_entry_id: Optional[int],
    all_talkgroups: bool = False,
) -> Dict[str, Any]:
    lim = max(1, min(int(limit or 5), 10))
    q = events_db.query(SpanStore).filter(SpanStore.monitor_id == monitor_id)
    if not all_talkgroups:
        q = q.filter(SpanStore.talkgroup == (talkgroup or None))
    if exclude_log_entry_id is not None:
        q = q.filter(SpanStore.log_entry_id != exclude_log_entry_id)
    rows = q.order_by(SpanStore.id.desc()).limit(lim).all()
    spans: List[Dict[str, Any]] = []
    for r in reversed(rows):
        preview = r.transcript or ""
        spans.append({
            "log_entry_id": r.log_entry_id,
            "evt_type": r.evt_type,
            "units": r.units,
            "locations": r.locations,
            "addresses": r.addresses,
            "cross_streets": r.cross_streets,
            "persons": r.persons,
            "vehicles": r.vehicles,
            "plates": r.plates,
            "transcript_preview": (preview[:500] + "…") if len(preview) > 500 else preview,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return {"spans": spans, "count": len(spans)}


# Worker-only: structured broadcast category (not used by Master routing).
CLASSIFY_BROADCAST_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "classify_broadcast",
        "description": (
            "Call when this span is station-wide broadcast traffic (not a normal incident thread). "
            "Records the broadcast category. Use before outputting create with event_type BROADCAST."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "broadcast_type": {
                    "type": "string",
                    "enum": [
                        "storm_warning",
                        "cni_drivers",
                        "road_debris",
                        "attempt_to_locate",
                    ],
                    "description": (
                        "storm_warning: severe weather / storm alerts; "
                        "cni_drivers: CNI driver traffic; "
                        "road_debris: road debris calls; "
                        "attempt_to_locate: ATL / attempt to locate."
                    ),
                },
            },
            "required": ["broadcast_type"],
        },
    },
}


def _tool_classify_broadcast(arguments: Dict[str, Any]) -> Dict[str, Any]:
    allowed = frozenset({"storm_warning", "cni_drivers", "road_debris", "attempt_to_locate"})
    raw = (arguments.get("broadcast_type") or "").strip().lower()
    if raw not in allowed:
        return {
            "ok": False,
            "error": f"invalid broadcast_type {raw!r}",
            "allowed": sorted(allowed),
        }
    return {"ok": True, "broadcast_type": raw}


def _execute_tool(
    name: str,
    arguments: Dict[str, Any],
    events_db: Session,
    monitor_id: int,
    talkgroup: str,
    exclude_log_entry_id: Optional[int] = None,
) -> str:
    try:
        if name == "list_open_events":
            lim = int(arguments.get("limit") or 20)
            data = _tool_list_open_events(events_db, monitor_id, lim)
        elif name == "get_event_snapshot":
            eid = (arguments.get("event_id") or "").strip()
            if not eid:
                return json.dumps({"error": "missing event_id"})
            data = _tool_get_event_snapshot(events_db, monitor_id, eid)
        elif name == "get_recent_spans":
            lim = int(arguments.get("limit") or 5)
            ex = arguments.get("exclude_log_entry_id")
            try:
                ex_id = int(ex) if ex is not None else exclude_log_entry_id
            except (TypeError, ValueError):
                ex_id = exclude_log_entry_id
            ag = bool(arguments.get("all_talkgroups"))
            data = _tool_get_recent_spans(events_db, monitor_id, talkgroup or "", lim, ex_id, ag)
        elif name == "classify_broadcast":
            data = _tool_classify_broadcast(arguments)
        else:
            data = {"error": f"unknown tool {name}"}
        return json.dumps(data, default=str)
    except Exception as ex:
        logger.warning("routing tool %s failed: %s", name, ex)
        return json.dumps({"error": str(ex)})


def _parse_tool_arguments(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _http_post_json(url: str, body: Dict[str, Any], timeout: float) -> Optional[Dict[str, Any]]:
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        err = str(e).lower()
        if "timed out" in err or "timeout" in err:
            logger.warning(
                "Ollama request timed out (%.0fs); raise incidents_ollama.timeout_seconds if needed",
                timeout,
            )
        else:
            logger.debug("Ollama unavailable: %s", e)
        return None
    except socket.timeout:
        logger.warning("Ollama socket timeout (%.0fs)", timeout)
        return None
    except Exception as e:
        logger.warning("Ollama request failed: %s", e)
        return None


def _conversation_has_tool_results(messages: List[Dict[str, Any]]) -> bool:
    return any(m.get("role") == "tool" for m in messages)


def _ollama_openai_completions_request(
    base_url: str,
    model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]],
    timeout: float,
    *,
    max_tokens: Optional[int] = None,
    reasoning_effort: Optional[str] = None,
    tool_choice: Optional[str] = None,
    response_format: Optional[Dict[str, Any]] = None,
    omit_response_format: bool = False,
) -> Optional[Dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "stream": False,
    }
    # json_object + tools breaks many models: they emit JSON instead of tool_calls.
    if not tools and not omit_response_format:
        fmt = response_format if response_format is not None else {"type": "json_object"}
        if fmt:
            body["response_format"] = fmt
    if max_tokens is not None and max_tokens > 0:
        body["max_tokens"] = max_tokens
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort
    if tools:
        body["tools"] = tools
        body["tool_choice"] = tool_choice if tool_choice is not None else "auto"
    data = _http_post_json(url, body, timeout)
    if not data:
        return None
    err = data.get("error")
    if err:
        logger.warning("Ollama /v1 error: %s", err)
        if tools and body.get("tool_choice") == "required":
            body_retry = dict(body)
            body_retry["tool_choice"] = "auto"
            logger.info("Retrying Ollama /v1/chat/completions with tool_choice=auto")
            data = _http_post_json(url, body_retry, timeout)
            if not data:
                return None
            err = data.get("error")
            if err:
                logger.warning("Ollama /v1 error after retry: %s", err)
                return None
        else:
            return None
    return data


def _ollama_native_chat_request(
    base_url: str,
    model: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]],
    timeout: float,
    *,
    max_tokens: Optional[int] = None,
    format_json: bool = False,
) -> Optional[Dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/api/chat"
    opts: Dict[str, Any] = {"temperature": 0.1}
    if max_tokens is not None and max_tokens > 0:
        opts["num_predict"] = max_tokens
    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": opts,
    }
    if tools:
        body["tools"] = tools
    elif format_json:
        body["format"] = "json"
    return _http_post_json(url, body, timeout)


def _call_master_chat_plain(
    base_url: str,
    model: str,
    messages: List[Dict[str, Any]],
    timeout: float,
    *,
    max_tokens: Optional[int],
    use_openai_api: bool,
    reasoning_effort: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Master model chat without tools: plain text (no json_object response_format)."""
    if use_openai_api:
        return _ollama_openai_completions_request(
            base_url,
            model,
            messages,
            None,
            timeout,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
            omit_response_format=True,
        )
    return _ollama_native_chat_request(
        base_url, model, messages, None, timeout, max_tokens=max_tokens,
    )


def _routing_response_message(data: Dict[str, Any], use_openai_api: bool) -> Dict[str, Any]:
    if use_openai_api:
        ch = data.get("choices") or []
        if not ch:
            return {}
        return ch[0].get("message") or {}
    return data.get("message") or {}


def _message_text_for_decision(msg: Dict[str, Any]) -> str:
    """Merge text fields: OpenAI-compat Qwen often leaves `content` empty and uses `reasoning`."""
    chunks: List[str] = []
    for key in ("content", "thinking", "reasoning"):
        s = (msg.get(key) or "").strip()
        if s:
            chunks.append(s)
    return "\n\n".join(chunks)


# Master header / models that echo instructions may include stray `{` before the real JSON object.
_EVENT_TYPE_JSON_START = re.compile(r"\{\s*\"event_type\"\s*:", re.IGNORECASE)


def _prepare_assistant_text_for_json(text: str) -> str:
    """Strip Qwen/DeepSeek think blocks and markdown fences so JSON can be parsed."""
    if not text:
        return ""
    t = text.strip()
    t = re.sub(r"`\s*think\s*[\s\S]*?`", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"<think>[\s\S]*?</think>", "", t, flags=re.IGNORECASE).strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", t, re.IGNORECASE)
    if fence:
        t = fence.group(1).strip()
    # Strip leading "Thinking Process:" / analysis blocks when JSON appears after (non-greedy to first {).
    t = re.sub(
        r"(?is)^\s*(Thinking\s+Process:|Analysis:|Reasoning:)\s*.*?(?=\{)",
        "",
        t,
        count=1,
    ).strip()
    # Real object usually ends with {"event_type": ...}; take last match so prompt echoes do not win.
    _et_matches = list(_EVENT_TYPE_JSON_START.finditer(t))
    if _et_matches:
        t = t[_et_matches[-1].start() :].strip()
    return t


_JSON_SCAN_MAX_CHARS = 32 * 1024  # belt-and-suspenders cap; we only scan the trailing slice
_JSON_DECODER = json.JSONDecoder()


def _cap_text_tail(text: str) -> str:
    return text if len(text) <= _JSON_SCAN_MAX_CHARS else text[-_JSON_SCAN_MAX_CHARS:]


def _scan_for_json_object(text: str, *required_keys: str) -> Optional[Dict[str, Any]]:
    """Try direct parse then brace-scan with JSONDecoder.raw_decode (string-aware, linear overall).

    Returns first dict containing any of required_keys.
    """
    text = _cap_text_tail(text)
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and any(k in obj for k in required_keys):
            return obj
    except json.JSONDecodeError:
        pass
    i = 0
    n = len(text)
    while i < n:
        pos = text.find("{", i)
        if pos < 0:
            break
        try:
            obj, end = _JSON_DECODER.raw_decode(text, pos)
        except json.JSONDecodeError:
            i = pos + 1
            continue
        if isinstance(obj, dict) and any(k in obj for k in required_keys):
            return obj
        i = end
    return None


def _scan_for_json_object_from_end(text: str, *required_keys: str) -> Optional[Dict[str, Any]]:
    """Prefer JSON near end of text (models often emit 'Thinking Process:' then the object)."""
    text = _cap_text_tail(text)
    pos = text.rfind("{")
    while pos >= 0:
        try:
            obj, _end = _JSON_DECODER.raw_decode(text, pos)
        except json.JSONDecodeError:
            pos = text.rfind("{", 0, pos)
            continue
        if isinstance(obj, dict) and any(k in obj for k in required_keys):
            return obj
        pos = text.rfind("{", 0, pos)
    return None


def _scan_for_json_object_near_event_type_key(text: str, *required_keys: str) -> Optional[Dict[str, Any]]:
    """Parse the JSON object whose first key is event_type (skips stray { inside thinking/analysis text)."""
    for m in reversed(list(_EVENT_TYPE_JSON_START.finditer(text))):
        obj = _scan_for_json_object(text[m.start() :], *required_keys)
        if obj:
            return obj
    return None


def _extract_decision_from_pseudo_tool_xml(text: str) -> Optional[Dict[str, Any]]:
    """Qwen sometimes ends `reasoning` with fake XML (e.g. <function=skip>) instead of JSON."""
    if not text:
        return None
    pat = re.compile(r"<function\s*=\s*(attach|skip|close)\s*>", re.IGNORECASE)
    matches = list(pat.finditer(text))
    if not matches:
        return None
    action = matches[-1].group(1).lower()
    tail = text[matches[-1].start():]
    eid_m = re.search(
        r"<parameter\s*=\s*event_id\s*>\s*([^<]+?)\s*</parameter>",
        tail,
        re.IGNORECASE | re.DOTALL,
    )
    event_id = eid_m.group(1).strip() if eid_m else None
    if action in ("attach", "close") and not event_id:
        return None
    return {"action": action, "event_id": event_id, "reason": ""}


def _extract_decision_json(content: str) -> Optional[Dict[str, Any]]:
    text = _prepare_assistant_text_for_json(content)
    if not text:
        return _extract_decision_from_pseudo_tool_xml((content or "").strip())
    result = _scan_for_json_object(text, "action")
    if result:
        return result
    return _extract_decision_from_pseudo_tool_xml(text) or _extract_decision_from_pseudo_tool_xml(
        (content or "").strip()
    )


def _iter_tool_calls(msg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse tool_calls; each item has id (str), name, args (dict)."""
    out: List[Dict[str, Any]] = []
    for tc in msg.get("tool_calls") or []:
        if not isinstance(tc, dict):
            continue
        cid = str(tc.get("id") or "")
        fn = tc.get("function")
        if isinstance(fn, dict) and fn.get("name"):
            name = str(fn.get("name") or "").strip()
            args = _parse_tool_arguments(fn.get("arguments"))
        elif tc.get("name"):
            name = str(tc.get("name") or "").strip()
            args = _parse_tool_arguments(tc.get("arguments"))
        else:
            continue
        if name:
            out.append({"id": cid, "name": name, "args": args})
    return out


def _find_open_event(events_db: Session, eid: str, monitor_id: int) -> Optional[Event]:
    if not eid:
        return None
    return events_db.query(Event).filter(
        Event.event_id == eid, Event.monitor_id == monitor_id, Event.status == "open"
    ).first()


def _dispatch_tool_calls(
    messages: List[Dict[str, Any]],
    msg: Dict[str, Any],
    use_openai_api: bool,
    events_db: Session,
    monitor_id: int,
    talkgroup: str,
    log_entry_id: int,
) -> bool:
    """Append assistant + tool result messages; returns True if any tool calls were dispatched."""
    tool_calls = msg.get("tool_calls") or []
    if not tool_calls:
        return False
    asst: Dict[str, Any] = {"role": "assistant", "tool_calls": tool_calls}
    c = msg.get("content")
    asst["content"] = c if c is not None else ""
    messages.append(asst)
    calls = _iter_tool_calls(msg)
    if not calls:
        logger.warning("LLM routing: tool_calls present but could not parse; sample=%s", str(tool_calls)[:500])
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") or {}
            name = (fn.get("name") or "") if isinstance(fn, dict) else ""
            args = _parse_tool_arguments(fn.get("arguments") if isinstance(fn, dict) else None)
            if not name:
                continue
            result = _execute_tool(name, args, events_db, monitor_id, talkgroup, log_entry_id)
            tid = str(tc.get("id") or "")
            if use_openai_api and tid:
                messages.append({"role": "tool", "tool_call_id": tid, "content": result})
            else:
                messages.append({"role": "tool", "content": result, "name": name})
    else:
        for call in calls:
            result = _execute_tool(
                call["name"], call["args"], events_db, monitor_id, talkgroup, log_entry_id
            )
            if use_openai_api:
                tid = call.get("id") or ""
                if not tid:
                    logger.warning("LLM routing: missing tool_call id for %s (OpenAI API)", call["name"])
                    messages.append({"role": "tool", "content": result, "name": call["name"]})
                else:
                    messages.append({"role": "tool", "tool_call_id": tid, "content": result})
            else:
                messages.append({"role": "tool", "content": result, "name": call["name"]})
    return True


def _append_tool_call_reprompt(messages: List[Dict[str, Any]], context: str) -> None:
    """Nudge model to call tools when it replied without tool_calls/decision."""
    messages.append(
        {
            "role": "user",
            "content": (
                "You skipped tool calls. Call the required tools now, then output JSON decision only. "
                f"Context: {context}."
            ),
        }
    )


def _validate_and_build_decision(
    decision: Dict[str, Any],
    events_db: Session,
    monitor_id: int,
) -> Optional[Dict[str, Any]]:
    """Master accepts only attach | skip | close (Worker opens new incidents)."""
    action = (decision.get("action") or "").lower().strip()
    if action not in ("attach", "skip", "close"):
        logger.warning("LLM routing: invalid action %s", action)
        return None
    eid = decision.get("event_id")
    if eid is not None and not isinstance(eid, str):
        eid = str(eid)
    if action in ("attach", "close"):
        if not _find_open_event(events_db, eid or "", monitor_id):
            logger.warning("LLM routing: %s target invalid %s", action, eid)
            return None
    return {
        "action": action,
        "event_id": eid if action in ("attach", "close") else None,
        "reason": (decision.get("reason") or "")[:500],
        "evt_type": "",
    }


def route_transcript_with_llm(
    *,
    monitor_id: int,
    monitor_name: str,
    talkgroup: str,
    transcript: str,
    entities: Dict[str, List[str]],
    log_entry_id: int,
    log_timestamp: Optional[Any],
    has_start_label: bool,
    start_labels: List[str],
    events_db: Session,
    worker_deferred: bool = False,
    primary_event_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Master router: {"action": "attach"|"skip"|"close", "event_id", "reason"} — new incidents are opened by Worker, not here.
    """
    settings = get_settings()
    ollama_cfg = getattr(settings.config, "incidents_ollama", None)
    pipe = settings.config.events_pipeline
    if not ollama_cfg or not getattr(ollama_cfg, "enabled", False):
        return None
    if not getattr(pipe, "llm_routing", False):
        return None

    base_url = (ollama_cfg.base_url or "http://localhost:11434").rstrip("/")
    model = incidents_ollama_master_model(ollama_cfg)
    timeout = _resolve_timeout(ollama_cfg)
    max_rounds = int(getattr(pipe, "llm_routing_max_tool_rounds", 12) or 12)
    use_openai_api = bool(getattr(pipe, "llm_routing_openai_api", True))
    routing_max_tokens = _resolve_max_tokens(pipe)
    routing_reasoning_effort = _resolve_reasoning_effort(pipe)
    log_raw = bool(getattr(pipe, "llm_routing_log_raw", False))
    stale_seconds = int(getattr(pipe, "master_llm_stale_seconds", 3600) or 3600)

    ts_str = ""
    if log_timestamp is not None:
        try:
            ts_str = log_timestamp.isoformat() if hasattr(log_timestamp, "isoformat") else str(log_timestamp)
        except Exception:
            ts_str = str(log_timestamp)

    system_time_str = ""
    if log_entry_id:
        logs_db = LogsSessionLocal()
        try:
            row = logs_db.query(LogEntry.created_at, LogEntry.timestamp).filter(
                LogEntry.id == log_entry_id, LogEntry.is_deleted == False
            ).first()
        finally:
            logs_db.close()
        if row:
            ca, ts = row[0], row[1]
            if ca is not None:
                try:
                    system_time_str = ca.isoformat() if hasattr(ca, "isoformat") else str(ca)
                except Exception:
                    system_time_str = str(ca)
            if not ts_str and ts is not None:
                try:
                    ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                except Exception:
                    ts_str = str(ts)

    primary_hint = (
        f"\nPrimary target event: {primary_event_id} — evaluate this event first for attach/close/skip."
        if primary_event_id else ""
    )
    worker_hint = (
        "\nNote: a Worker LLM already determined this span is NOT a new incident. Route it to an existing event or skip."
        if worker_deferred else ""
    )
    stale_hint = (
        f"\nStaleness rule: if `seconds_since_last_span` > {stale_seconds} on an event, "
        "prefer skip unless the transcript is a strong semantic match (same units, same location, or explicit scene continuity)."
        if stale_seconds > 0 else ""
    )

    system_builtin = (
        "You route public-safety radio spans to an active incident.\n"
        "An event is already open for this monitor. Your job is attach, skip, or close — never create.\n\n"

        "GROUNDING (read this first):\n"
        "- The JSON field \"transcript\" is the only authoritative text of this span. Base attach/skip/close "
        "on what those words actually mean (dispatch instruction, acknowledgment, scene update, noise, etc.).\n"
        "- The field \"ner_clues\" is machine NER output: wrong labels, noise, and missed phrases are common. "
        "Use it only as a hint when it agrees with the transcript; never let NER override plain English in "
        "the transcript.\n"
        "- Do NOT attach because ner_clues shows EVT_TYPE, LOC, or UNIT if the transcript itself does not "
        "support tying this transmission to that open event.\n"
        "- Your \"reason\" must reflect the transcript's meaning (paraphrase or short quote of what was "
        "said), not a restatement of NER tags or event headers.\n\n"

        "DEFAULT: skip. Attaching incorrectly pollutes incidents. Only attach when the transcript has "
        "clear evidence linking it to a specific open event (shared units, same location, direct "
        "reference to the incident, or explicit dispatch continuity).\n\n"

        "CRITICAL — 10-codes that are NOT incident-specific (do NOT attach based on these alone):\n"
        "  10-4/copy/roger = acknowledgment only\n"
        "  10-7 = off duty / out of service (generic, not scene-related)\n"
        "  10-8 = in service / available\n"
        "  10-9 = repeat / say again\n"
        "  10-42 = unit off duty for the day\n"
        "  \"clear\" / \"that's clear\" = often just radio acknowledgment, not incident resolved\n"
        "  \"Troop-C clear\" = dispatcher sign-off, never means incident resolved\n\n"

        "PROCESS:\n"
        "STEP 1: Read \"transcript\" only — decide what this transmission is actually doing (scene detail vs "
        "generic ack vs unrelated traffic). Then optionally glance at ner_clues for disambiguation, not "
        "as a decision shortcut.\n"
        "STEP 2: Call tools (get_recent_spans, list_open_events or get_event_snapshot) for context.\n"
        "STEP 3: Output ONLY this JSON:\n"
        '{"action":"attach"|"skip"|"close","event_id":"<id or null>","reason":"<10 words max>"}\n\n'

        "RULES:\n"
        "- attach: the transcript text semantically ties this span to one open event (same units/locations/"
        "incident thread), not merely because NER and an event header both mention a keyword.\n"
        "- close: scene clear, all units released, dispatch formally closes, or disregard issued — "
        "supported by words in the transcript.\n"
        "- skip: default for generic traffic, 10-codes without context, noise, junk, or VAD_REJECTED.\n"
        "- If NER found no entities AND transcript is under 10 words, skip unless a unit ID in the "
        "transcript exactly matches an open event's units field.\n"
        "- Your reason MUST reference words actually in the transcript. "
        "Never restate the event header as your reason; never cite NER field names as the reason.\n"
        f"{primary_hint}{worker_hint}{stale_hint}\n"
        "Do not narrate. Do not explain. Output only the JSON."
    )

    system = system_builtin

    # transcript first so the model sees ground truth before NER hints (JSON key order preserved).
    user_payload = {
        "transcript": transcript,
        "ner_clues": entities,
        "monitor_id": monitor_id,
        "monitor_name": monitor_name,
        "talkgroup": talkgroup,
        "log_entry_id": log_entry_id,
        "incident_time": ts_str,
        "system_time": system_time_str,
        "timestamp": ts_str,
        "primary_event_id": primary_event_id,
        "worker_deferred": worker_deferred,
        "pipeline": "master_router",
    }

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]
    reprompted_for_tools = False
    last_raw_blob = ""

    for round_i in range(max_rounds):
        if use_openai_api:
            data = _ollama_openai_completions_request(
                base_url, model, messages, ROUTING_TOOLS, timeout,
                max_tokens=routing_max_tokens,
                reasoning_effort=routing_reasoning_effort,
                tool_choice="auto" if _conversation_has_tool_results(messages) else "required",
            )
        else:
            if routing_reasoning_effort:
                logger.debug(
                    "llm_routing_reasoning_effort is ignored when llm_routing_openai_api is false (native /api/chat)"
                )
            data = _ollama_native_chat_request(
                base_url, model, messages, ROUTING_TOOLS, timeout, max_tokens=routing_max_tokens,
            )
        if not data:
            return None
        try:
            last_raw_blob = json.dumps(data, ensure_ascii=False, default=str)
        except TypeError:
            last_raw_blob = str(data)
        if log_raw:
            logger.info(
                "LLM routing raw response round=%s openai_api=%s len=%s: %s",
                round_i, use_openai_api, len(last_raw_blob),
                last_raw_blob[:_RAW_LOG_MAX] + ("…" if len(last_raw_blob) > _RAW_LOG_MAX else ""),
            )

        resp_msg = _routing_response_message(data, use_openai_api)
        if _dispatch_tool_calls(
            messages, resp_msg, use_openai_api, events_db, monitor_id, talkgroup, log_entry_id
        ):
            continue

        content_raw = _message_text_for_decision(resp_msg)
        if log_raw:
            logger.info(
                "LLM routing final assistant text (round=%s) len=%s: %s",
                round_i, len(content_raw),
                content_raw[:_RAW_LOG_MAX] + ("…" if len(content_raw) > _RAW_LOG_MAX else ""),
            )
        decision = _extract_decision_json(content_raw)
        if not decision:
            if not _conversation_has_tool_results(messages) and not reprompted_for_tools:
                reprompted_for_tools = True
                _append_tool_call_reprompt(messages, "master_router requires tool reads before deciding")
                continue
            preview = (content_raw[:800] + "…") if len(content_raw) > 800 else content_raw
            logger.warning("LLM routing: no JSON decision in assistant output: %r", preview)
            return None
        out = _validate_and_build_decision(decision, events_db, monitor_id)
        if out is not None:
            out["_llm_output"] = last_raw_blob
        return out

    logger.warning("LLM routing: max tool rounds exceeded")
    return None
