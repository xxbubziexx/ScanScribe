"""Single-pass LLM router for public safety radio events using OpenRouter (OpenAI-compatible API)."""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx

from ..config import (
    get_settings,
    openrouter_api_key,
    openrouter_base_url,
    openrouter_model,
)

logger = logging.getLogger(__name__)

BROADCAST_TYPE_SLUGS = frozenset({
    "storm_warning",
    "cni_drivers",
    "road_debris",
    "attempt_to_locate",
})
WORKER_BROADCAST_EVENT_TYPE = "BROADCAST"


class OpenRouterRateLimitManager:
    """Tracks OpenRouter rate limit cooldowns and short-circuits calls during rate limiting."""

    _cooldown_until: float = 0.0
    _cooldown_reason: str = ""
    _limit_source: str = ""
    _last_log_ts: float = 0.0

    @classmethod
    def _save_to_db(cls, data: Dict[str, Any]) -> None:
        """Persist rate-limit state into events database so it survives container restarts."""
        try:
            from ..database import EventsSessionLocal
            from ..models.event import SystemSetting
            db = EventsSessionLocal()
            try:
                row = db.query(SystemSetting).filter(SystemSetting.key == "openrouter_rate_limit").first()
                if not row:
                    row = SystemSetting(key="openrouter_rate_limit", value=json.dumps(data))
                    db.add(row)
                else:
                    row.value = json.dumps(data)
                    row.updated_at = datetime.now(timezone.utc)
                db.commit()
            finally:
                db.close()
        except Exception as exc:
            logger.debug("OpenRouterRateLimitManager: could not persist to DB: %s", exc)

    @classmethod
    def _load_from_db(cls) -> Optional[Dict[str, Any]]:
        """Load persisted rate-limit state from events database."""
        try:
            from ..database import EventsSessionLocal
            from ..models.event import SystemSetting
            db = EventsSessionLocal()
            try:
                row = db.query(SystemSetting).filter(SystemSetting.key == "openrouter_rate_limit").first()
                if row and row.value:
                    return json.loads(row.value)
            finally:
                db.close()
        except Exception as exc:
            logger.debug("OpenRouterRateLimitManager: could not read from DB: %s", exc)
        return None

    @classmethod
    def _clear_in_db(cls) -> None:
        """Remove persisted rate-limit state from events database."""
        try:
            from ..database import EventsSessionLocal
            from ..models.event import SystemSetting
            db = EventsSessionLocal()
            try:
                row = db.query(SystemSetting).filter(SystemSetting.key == "openrouter_rate_limit").first()
                if row:
                    db.delete(row)
                    db.commit()
            finally:
                db.close()
        except Exception:
            pass

    @classmethod
    def is_rate_limited(cls) -> Tuple[bool, float, str]:
        """Return (is_limited, seconds_remaining, reason). Checks in-memory cache, DB, and config settings."""
        from ..config import rate_limiter_config
        rl_cfg = rate_limiter_config()
        if not getattr(rl_cfg, "enabled", True):
            return False, 0.0, ""

        now = time.time()
        if now < cls._cooldown_until:
            rem = cls._cooldown_until - now
            return True, rem, cls._cooldown_reason

        # If in-memory cooldown is expired/unset, inspect DB persistence
        db_state = cls._load_from_db()
        if db_state and db_state.get("cooldown_until"):
            try:
                until = float(db_state["cooldown_until"])
                if until > now:
                    cls._cooldown_until = until
                    cls._cooldown_reason = str(db_state.get("reason") or "Rate limit exceeded")
                    cls._limit_source = str(db_state.get("limit_source") or "")
                    return True, until - now, cls._cooldown_reason
                else:
                    auto_start = getattr(rl_cfg, "auto_start_events_after_timeout", True)
                    if not auto_start:
                        cls._cooldown_until = until
                        cls._cooldown_reason = "Rate limit timeout reached. Auto-start is disabled in config. Events routing remains paused until ScanScribe is restarted or reset."
                        return True, 0.0, cls._cooldown_reason
                    cls._clear_in_db()
                    cls._cooldown_until = 0.0
                    cls._cooldown_reason = ""
            except (ValueError, TypeError):
                cls._clear_in_db()

        # If in-memory cooldown has just expired:
        if cls._cooldown_until > 0.0 and now >= cls._cooldown_until:
            auto_start = getattr(rl_cfg, "auto_start_events_after_timeout", True)
            if not auto_start:
                cls._cooldown_reason = "Rate limit timeout reached. Auto-start is disabled in config. Events routing remains paused until ScanScribe is restarted or reset."
                return True, 0.0, cls._cooldown_reason
            cls._cooldown_until = 0.0
            cls._cooldown_reason = ""
            cls._clear_in_db()

        return False, 0.0, ""

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Return structured rate limit status for API and UI consumers."""
        from ..config import rate_limiter_config
        rl_cfg = rate_limiter_config()
        enabled = bool(getattr(rl_cfg, "enabled", True))
        auto_start = bool(getattr(rl_cfg, "auto_start_events_after_timeout", True))

        is_limited, rem, reason = cls.is_rate_limited()
        is_paused_waiting = bool(is_limited and rem <= 0.0)
        cooldown_until = cls._cooldown_until if is_limited else None
        cooldown_until_iso = None
        reset_formatted = None
        if is_limited and cooldown_until:
            dt = datetime.fromtimestamp(cooldown_until, timezone.utc)
            cooldown_until_iso = dt.isoformat()
            reset_formatted = dt.strftime("%Y-%m-%d %H:%M:%S UTC")

        return {
            "is_rate_limited": is_limited,
            "rate_limiter_enabled": enabled,
            "auto_start_events_after_timeout": auto_start,
            "is_paused_waiting_start": is_paused_waiting,
            "cooldown_until": cooldown_until,
            "cooldown_until_iso": cooldown_until_iso,
            "seconds_remaining": max(0.0, round(rem, 1)),
            "reason": reason if is_limited else None,
            "limit_source": cls._limit_source if is_limited else None,
            "reset_time_formatted": reset_formatted,
        }

    @classmethod
    def record_429(
        cls,
        status_code: int,
        headers: Any = None,
        body_text: str = "",
    ) -> float:
        """Parse 429 response headers and body to compute exact cooldown timestamp, persisting to DB."""
        from ..config import rate_limiter_config
        rl_cfg = rate_limiter_config()
        if not getattr(rl_cfg, "enabled", True):
            logger.info("OpenRouterRateLimitManager: rate limiter is disabled in configuration. Skipping cooldown.")
            return 0.0

        now = time.time()
        headers_dict = dict(headers) if headers else {}
        norm_headers = {str(k).lower(): str(v) for k, v in headers_dict.items()}

        wait_seconds: Optional[float] = None
        target_until: Optional[float] = None
        source = "rate_limit_429"
        reason = "Rate limit exceeded"

        # 1. Check Retry-After header (seconds)
        retry_after = norm_headers.get("retry-after")
        if retry_after:
            try:
                wait_seconds = float(retry_after)
                target_until = now + wait_seconds
                reason = f"Retry-After {int(wait_seconds)}s"
            except (ValueError, TypeError):
                pass

        # 2. Check X-RateLimit-Reset (epoch ms or epoch s) from headers or JSON metadata
        reset_val = norm_headers.get("x-ratelimit-reset") or norm_headers.get("x-rate-limit-reset")
        if body_text:
            try:
                data = json.loads(body_text)
                err = data.get("error", {})
                reason = err.get("message", reason)
                meta = err.get("metadata", {})
                source = meta.get("limit_source", source)
                meta_headers = meta.get("headers", {})
                if isinstance(meta_headers, dict):
                    norm_meta = {str(k).lower(): str(v) for k, v in meta_headers.items()}
                    if not reset_val:
                        reset_val = norm_meta.get("x-ratelimit-reset") or norm_meta.get("x-rate-limit-reset")
                    if not retry_after and norm_meta.get("retry-after"):
                        try:
                            wait_seconds = float(norm_meta["retry-after"])
                            target_until = now + wait_seconds
                            reason = f"Retry-After {int(wait_seconds)}s"
                        except (ValueError, TypeError):
                            pass
            except Exception:
                pass

        # 3. Regex fallback on raw body text if json parsing missed reset header
        if not reset_val and body_text:
            match = re.search(r'["\']?x-ratelimit-reset["\']?\s*[:=]\s*["\']?(\d+)', body_text, re.IGNORECASE)
            if match:
                reset_val = match.group(1)

        if reset_val:
            try:
                val = float(reset_val)
                # If milliseconds (e.g. 1789171200000)
                if val > 1e11:
                    val = val / 1000.0
                if val > now:
                    wait_seconds = val - now
                    target_until = val
                    dt_reset = datetime.fromtimestamp(val, timezone.utc)
                    reason = f"{reason} (resets at {dt_reset.strftime('%H:%M:%S UTC')})"
            except (ValueError, TypeError):
                pass

        # 4. Fallback: If free-tier daily limit detected, calculate seconds until next 00:00:00 UTC
        if wait_seconds is None:
            if "free-models-per-day" in body_text or source == "openrouter_free_tier_daily":
                source = "openrouter_free_tier_daily"
                dt_now = datetime.now(timezone.utc)
                tomorrow = (dt_now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                wait_seconds = (tomorrow - dt_now).total_seconds()
                target_until = tomorrow.timestamp()
                reason = "OpenRouter daily free-tier limit reached (resets at 00:00:00 UTC)"
            else:
                wait_seconds = 60.0
                target_until = now + 60.0
                reason = "Rate limit exceeded (cooling down 60s)"

        wait_seconds = max(5.0, min(86400.0, wait_seconds))
        cooldown_until = target_until if (target_until and target_until > now) else (now + wait_seconds)

        cls._cooldown_until = cooldown_until
        cls._cooldown_reason = reason
        cls._limit_source = source

        # Persist to DB
        cls._save_to_db({
            "is_rate_limited": True,
            "cooldown_until": cooldown_until,
            "cooldown_until_iso": datetime.fromtimestamp(cooldown_until, timezone.utc).isoformat(),
            "reason": reason,
            "limit_source": source,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

        rem_min = int(wait_seconds // 60)
        rem_sec = int(wait_seconds % 60)
        logger.warning(
            "OpenRouterRateLimitManager: rate limit 429 detected (%s). Events pipeline cooling down for %dm %ds (until %s).",
            reason,
            rem_min,
            rem_sec,
            datetime.fromtimestamp(cls._cooldown_until, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
        return wait_seconds

    @classmethod
    def reset(cls) -> None:
        """Manually clear rate limit cooldown in memory and in DB."""
        cls._cooldown_until = 0.0
        cls._cooldown_reason = ""
        cls._limit_source = ""
        cls._last_log_ts = 0.0
        cls._clear_in_db()

SYSTEM_PROMPT_TEMPLATE = """You are an expert 911 / Public Safety Dispatch Triage and Incident Routing Assistant.
Your task is to analyze an incoming radio transmission transcript for a specific public safety monitor (department/talkgroup) alongside any currently open incidents, and decide the appropriate routing action in a single step.

### Routing Actions:
1. "CREATE": The transcript describes a NEW, distinct emergency incident (e.g. structure fire, motor vehicle accident, medical emergency, robbery, shooting, brush fire, alarm, rescue) that is NOT already represented in the list of open incidents.
2. "ATTACH": The transcript is an operational update, continuation, status report, size-up, unit arrival, command directive, or resource coordination belonging to one of the OPEN incidents. You MUST specify the exact "event_id" of that incident.
3. "CLOSE": The transcript explicitly concludes, clears, or terminates an active incident (e.g., "Command terminated, all units clear", "False alarm, scene cleared", "Patient refused transport, Medic 3 back in service", "Fire is out, returning to quarters"). You MUST specify the exact "event_id" of that incident.
4. "BROADCAST": The transcript is a formal, department-wide / all-units bulletin broadcast across the entire talkgroup for situational awareness, belonging strictly to one of 4 types: "storm_warning", "cni_drivers", "road_debris", "attempt_to_locate". You MUST specify the exact "broadcast_type" slug. Do NOT select BROADCAST for individual unit traffic, plate checks, or administrative messages.
5. "SKIP": The transcript is routine radio chatter without operational value (e.g., standalone acknowledgments like "10-4", "copy", "that's clear", "thanks", standalone unit callouts like "Central 42", mic checks, time checks like "93, 2140"), static / garbled noise, routine patrol traffic, or unrelated traffic by non-incident units.

### Output Schema:
You MUST respond with a single valid JSON object strictly adhering to this schema:
{
  "action": "CREATE" | "ATTACH" | "CLOSE" | "BROADCAST" | "SKIP",
  "event_id": "<string event_id of the matching open incident if ATTACH or CLOSE, else null>",
  "reason": "<concise 1-2 sentence explanation of your routing decision>",
  "event_type": "<standard title for the incident type if CREATE or if refining an existing incident, e.g. 'Structure Fire', 'Traffic Collision', 'Medical Emergency', or null>",
  "broadcast_type": "<'storm_warning' | 'cni_drivers' | 'road_debris' | 'attempt_to_locate' if action is BROADCAST, else null>",
  "location": "<normalized physical location/address/intersection mentioned in transcript, or null>",
  "units": ["<list of responding unit identifiers mentioned, e.g. 'Engine 4', 'Medic 2', 'Battalion 1'>"],
  "status_detail": "<current operational status/phase if mentioned, e.g. 'Dispatched', 'En route', 'On scene', 'Under control', 'Cleared', or null>"
}

### Guidelines:
- **STATION BROADCASTS vs. ROUTINE PATROL TRAFFIC (CRITICAL NEGATIVE RULES)**:
  "BROADCAST" is STRICTLY reserved for department-wide broadcasts announced across the channel for general officer awareness (e.g., "All units copy CNI driver...", "All cars BOLO for stolen vehicle...").
  NEVER classify any of the following as BROADCAST:
  a) **Plate Checks / 10-28**: An officer calling in a phonetic license plate (e.g., "John Frank 2 Henry 1 Robert", "Mary 7 Charles 4 David") is routine patrol traffic / traffic stop. Choose SKIP (or CREATE if tracking traffic stops). NEVER label this as attempt_to_locate or BROADCAST.
  b) **Person / Warrant Checks / 10-27 / 10-29**: An officer running a subject's name, DOB, or warrant status is routine patrol traffic. Choose SKIP. NEVER label this as attempt_to_locate or BROADCAST.
  c) **MDT Dispatches / Station Messages**: Transmissions like "Check your MDT for theft / road hazard", "sent you a 21", or "call Brianna reference dog in pound" are administrative messages to specific units. Choose SKIP. NEVER label these as BROADCAST.
  d) **Active Scene Searches**: An officer on scene saying "attempting to locate female" is an operational update to an active call. Choose ATTACH, NEVER BROADCAST.
  e) **Scene Logistics & Hazards**: Helicopter standby, clearing road blockage, or staging. Choose ATTACH to the open incident, NEVER BROADCAST.
- **OPERATIONAL UPDATES (MANDATORY ATTACHES)**:
  If an open incident exists, the following transmissions are vital operational updates and MUST be ATTACHED to the corresponding open incident (NEVER classify these as chatter or SKIP):
  a) **Unit Status Reports**: Units assigned to, responding to, or clearing an incident stating their operational status (e.g., "en route", "responding", "arriving", "on scene", "staged", "clearing", "transporting").
  b) **Incident Logistics & Command Directives**: Dispatch, command directives, and emergency resource coordination (e.g., apparatus positioning such as "position on Lambeth", second page / tone requests, EMS downgrade, aeromedical / helicopter standby, availability, weather flight aborts, or flight ETAs).
  c) **Patient & Hazard Updates**: Clinical or scene hazard conditions (e.g., entrapment, vehicle overturned, number of injuries/patients, fire/smoke conditions, hazard warnings).
- **ROUTINE CHATTER (SKIP)**:
  Reserve "SKIP" strictly for non-operational traffic:
  - Standalone acknowledgments with no operational content (e.g., "10-4", "Copy", "That's clear", "Thanks", "Roger", "Have a good night").
  - Standalone unit callouts without any report (e.g., "Central 42", "Engine 1 Central").
  - Unrelated traffic by non-incident units (e.g., an unaffiliated unit going 10-8 / in service).
  - Static, mic clicks, or time checks (e.g., "93, 2140").
- **CRITICAL RULE ON UNAFFILIATED UNITS**: Do NOT attach a new unit (especially one going "10-8" or "in service") to an active incident unless that specific unit was ALREADY assigned to that incident or is explicitly dispatched/responding to it.
- **CHANNEL CONTEXT & DIALOGUE CONTINUITY**: Review the "Recent Channel Transmissions" to understand ongoing conversations, unit acknowledgments, dispatch responses, and status changes on this monitor:
  - If a transmission is an operational response (e.g., "en route", "on scene", "traffic stop", "subject in custody") directly tied to a dispatch or dialogue seen in the recent transmissions context, use that sequence to correctly ATTACH to the corresponding open incident or CREATE if the incident was just initiated.
  - If a transmission is uninformative chatter or routine mic checks without operational action (e.g., "93, 2140", standalone "10-4"), you MUST select SKIP.
- Review each incident under "Currently Open Incidents on this Monitor" (including Type, Location, Units, Status, and running Summary narrative) to determine whether the incoming transmission is part of an ongoing event.
- If a transmission provides a meaningful update (location, status, patient condition) that matches the units, location, or nature of an active OPEN incident, choose "ATTACH".
- If a unit announces they are "10-8", "in service", or "clearing the scene" AND they belong to the open incident, choose "CLOSE" if they are the primary/last unit, or "ATTACH" if other units remain.
- Clean and normalize unit identifiers (e.g. "Engine 4", "Ladder 12", "Medic 2", "Squad 3", "Unit 102") and addresses (e.g. "124 Main St", "I-35 Mile Marker 200").
- If the monitor has NO open incidents and the transmission is not an incident (or just static / non-emergency), choose "SKIP".
- Output ONLY the JSON object. Do not include markdown preamble.
"""
SYSTEM_PROMPT = SYSTEM_PROMPT_TEMPLATE


def build_system_prompt(
    known_units: Optional[str] = None,
    global_rules: Optional[str] = None,
) -> str:
    """Build the system prompt, injecting monitor-specific Known Units, Prefix Rules, and Global Area / 10-Code Rules."""
    prompt = SYSTEM_PROMPT_TEMPLATE.strip()

    if global_rules and global_rules.strip():
        rules_block = (
            "\n\n### Global Area & Operational Rules (AUTHORITATIVE GROUND TRUTH):\n"
            "The following jurisdiction context, 10-codes, and regional operational rules are defined for this system:\n"
            f"[{global_rules.strip()}]\n"
            "- You MUST apply these 10-codes, terminology definitions, and area rules when analyzing transcripts and deciding routing actions."
        )
        prompt += rules_block

    if known_units and known_units.strip():
        units_block = (
            "\n\n### Known Unit Identifiers & Prefix Rules (AUTHORITATIVE GROUND TRUTH):\n"
            "The following unit callsigns and prefix naming conventions are strictly defined for this monitor:\n"
            f"[{known_units.strip()}]\n"
            "- You MUST prioritize and normalize unit designations against these established identifiers.\n"
            "- Do NOT invent, hallucinate, or misattribute unit callsigns that conflict with this list.\n"
            "- When extracting the 'units' array, map noisy or phonetically transcribed callsigns to their matching known unit form."
        )
        prompt += units_block

    return prompt



def _clean_and_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Clean markdown code fences, repair partial JSON, and parse JSON object."""
    if not text:
        return None
    cleaned = text.strip()

    # 1. Check for markdown code fences
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if blocks:
        for b in reversed(blocks):
            try:
                data = json.loads(b)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

    # 2. Direct JSON parse
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 3. Regex search for complete { ... } block
    start_idx = cleaned.find("{")
    end_idx = cleaned.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        try:
            data = json.loads(cleaned[start_idx:end_idx+1])
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # 4. Heuristic repair if token limit cut off the closing braces
    idx = cleaned.find("{")
    while idx != -1:
        snippet = cleaned[idx:]
        for suffix in ["}", "\n}", "\"\n}", "\"}\n}", "\"}}", "\"}]\n}"]:
            try:
                data = json.loads(snippet + suffix)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        idx = cleaned.find("{", idx + 1)

    # 5. Text fallback parser for verbose reasoning models
    t_lower = cleaned.lower()
    action = "SKIP"
    matches = re.findall(r'\baction\b.{0,40}?\b(create|attach|close|broadcast|skip)\b', t_lower, flags=re.DOTALL)
    if matches:
        action = matches[-1].upper()
    
    first_line = cleaned.split('\n')[0][:200]
    return {
        "action": action,
        "event_id": None,
        "reason": f"Heuristic recovery from text: {first_line}",
        "event_type": None,
        "broadcast_type": None,
        "location": None,
        "units": [],
        "status_detail": None,
    }


def build_user_prompt(
    monitor_name: str,
    talkgroup: str,
    transcript: str,
    entities: Optional[Dict[str, List[str]]] = None,
    open_incidents: Optional[List[Dict[str, Any]]] = None,
    recent_spans: Optional[List[Union[str, Dict[str, Any]]]] = None,
    known_units: Optional[str] = None,
) -> str:
    """Build the single-pass prompt context."""
    user_content: List[str] = [
        f"Department/Monitor: {monitor_name or 'Default'}",
        f"Current Talkgroup: {talkgroup or 'Unknown'}",
    ]

    if open_incidents:
        inc_lines = []
        for inc in open_incidents:
            eid = inc.get("event_id")
            etype = inc.get("event_type") or "Unknown Type"
            loc_val = (inc.get("location") or "").strip()
            res_val = (inc.get("resolved_address") or "").strip()
            if res_val and loc_val and res_val.lower() != loc_val.lower():
                loc = f"{res_val} (Spoken: {loc_val})"
            elif res_val:
                loc = res_val
            elif loc_val:
                loc = loc_val
            else:
                loc = "Unknown Location"
            units_str = inc.get("units") or "None"
            sdetail = inc.get("status_detail") or "Active"
            summary_val = inc.get("summary")
            summary_part = f" | Summary: \"{summary_val.strip()}\"" if summary_val and summary_val.strip() else ""
            transcripts = inc.get("recent_transcripts") or []
            t_summary = f" | Recent: {'; '.join(transcripts[-2:])}" if transcripts else ""
            inc_lines.append(
                f"- Event ID: {eid} | Type: {etype} | Location: {loc} | Units: {units_str} | Status: {sdetail}{summary_part}{t_summary}"
            )
        user_content.append("Currently Open Incidents on this Monitor:\n" + "\n".join(inc_lines))
    else:
        user_content.append("Currently Open Incidents on this Monitor: None (Idle)")

    if recent_spans:
        spans_to_render = recent_spans[-8:]
        span_lines = []
        n_spans = len(spans_to_render)
        for i, item in enumerate(spans_to_render):
            t_offset = n_spans - i
            if isinstance(item, dict):
                t_str = f"({item['time']}) " if item.get("time") else ""
                tg_str = f"[{item['talkgroup']}] " if item.get("talkgroup") else ""
                meta_parts = []
                if item.get("units"):
                    meta_parts.append(f"Units: {item['units']}")
                if item.get("location"):
                    meta_parts.append(f"Loc: {item['location']}")
                meta_str = f" | {', '.join(meta_parts)}" if meta_parts else ""
                span_lines.append(f"  [T-{t_offset}] {t_str}{tg_str}\"{item.get('transcript', '')}\"{meta_str}")
            elif isinstance(item, str) and item.strip():
                span_lines.append(f"  [T-{t_offset}] \"{item.strip()}\"")
        if span_lines:
            user_content.append(
                "Recent Channel Transmissions (Sequential Context on this Monitor - Oldest to Most Recent):\n"
                + "\n".join(span_lines)
            )
        else:
            user_content.append("Recent Channel Transmissions: None (Channel was quiet)")
    else:
        user_content.append("Recent Channel Transmissions: None (Channel was quiet)")

    user_content.append(
        f">>> CURRENT TRANSMISSION TO EVALUATE <<<\n"
        f"Talkgroup: {talkgroup or 'Unknown'}\n"
        f"Transcript: \"{transcript}\""
    )

    if entities:
        ent_lines = []
        for k in sorted(entities.keys()):
            v = entities[k]
            if v:
                ent_lines.append(f"  - {k}: {', '.join(v)}")
        if ent_lines:
            user_content.append("Extracted Named Entities for Current Transmission (NER):\n" + "\n".join(ent_lines))

    return "\n\n".join(user_content)


class EventsRouter:
    """Single-pass OpenRouter LLM router for public safety events."""

    @classmethod
    def route_transcript(
        cls,
        *,
        monitor_name: str,
        talkgroup: str,
        transcript: str,
        entities: Optional[Dict[str, List[str]]] = None,
        open_incidents: Optional[List[Dict[str, Any]]] = None,
        recent_spans: Optional[List[Union[str, Dict[str, Any]]]] = None,
        known_units: Optional[str] = None,
        global_rules: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synchronously evaluate transcript and return routing decision."""
        settings = get_settings()
        cfg = getattr(settings.config, "openrouter", None) or getattr(settings.config, "incidents_ollama", None)
        
        api_key = openrouter_api_key(cfg)
        base_url = openrouter_base_url(cfg)
        model = openrouter_model(cfg)
        timeout_s = float(getattr(cfg, "timeout_seconds", 30) or 30)
        temperature = float(getattr(cfg, "temperature", 0.0) or 0.0)

        # Check rate-limit cooldown before attempting any HTTP request
        is_limited, rem, reason = OpenRouterRateLimitManager.is_rate_limited()
        if is_limited:
            now = time.time()
            if now - OpenRouterRateLimitManager._last_log_ts > 60.0:
                OpenRouterRateLimitManager._last_log_ts = now
                logger.info(
                    "EventsRouter: rate-limit cooldown active (~%dm remaining, %s). Skipping routing call.",
                    int(rem // 60),
                    reason,
                )
            return {
                "action": "SKIP",
                "event_id": None,
                "reason": f"Rate-limit cooldown active (~{int(rem)}s remaining)",
                "event_type": None,
                "broadcast_type": None,
                "location": None,
                "units": [],
                "status_detail": None,
                "raw_llm_output": "",
                "duration_ms": 0.0,
                "error": "rate_limit_cooldown",
            }

        if not api_key:
            logger.warning("EventsRouter: OPENROUTER_API_KEY is not set. Cannot call LLM router.")
            return {
                "action": "SKIP",
                "event_id": None,
                "reason": "OPENROUTER_API_KEY is not configured",
                "event_type": None,
                "broadcast_type": None,
                "location": None,
                "units": [],
                "status_detail": None,
                "raw_llm_output": "",
                "duration_ms": 0.0,
                "error": "OPENROUTER_API_KEY missing",
            }

        user_prompt = build_user_prompt(
            monitor_name=monitor_name,
            talkgroup=talkgroup,
            transcript=transcript,
            entities=entities,
            open_incidents=open_incidents,
            recent_spans=recent_spans,
            known_units=known_units,
        )

        url = f"{base_url.rstrip('/')}/chat/completions"
        if not base_url.endswith("/v1") and not base_url.endswith("/api"):
            url = f"{base_url.rstrip('/')}/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://scanscribe.local",
            "X-Title": "ScanScribe",
        }

        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": build_system_prompt(known_units=known_units, global_rules=global_rules)},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
            "max_tokens": 2048,
            "include_reasoning": False,
            "reasoning": {
                "effort": "none",
                "exclude": True,
            },
        }

        t0 = time.perf_counter()
        raw_text = ""
        error_msg = ""

        try:
            with httpx.Client(timeout=timeout_s) as client:
                response = client.post(url, headers=headers, json=payload)
                if response.status_code == 400 and any(k in response.text for k in ("response_format", "reasoning", "include_reasoning")):
                    # Retry without response_format and reasoning if model/provider rejects them
                    payload.pop("response_format", None)
                    payload.pop("reasoning", None)
                    payload.pop("include_reasoning", None)
                    response = client.post(url, headers=headers, json=payload)
                
                response.raise_for_status()
                res_data = response.json()
                choices = res_data.get("choices") or []
                if choices:
                    msg = choices[0].get("message", {}) or {}
                    raw_text = (msg.get("content") or "").strip()
                    if not raw_text:
                        raw_text = (msg.get("reasoning") or msg.get("reasoning_content") or "").strip()

                # If OpenRouter returns an empty string with 200 OK, retry once without reasoning / response_format
                if response.is_success and not raw_text:
                    logger.warning("EventsRouter: empty completion with 200 OK; retrying once without reasoning and response_format")
                    retry_payload: Dict[str, Any] = {
                        "model": model,
                        "messages": payload["messages"],
                        "temperature": temperature,
                        "max_tokens": 2048,
                    }
                    retry_resp = client.post(url, headers=headers, json=retry_payload)
                    if retry_resp.is_success:
                        retry_data = retry_resp.json()
                        retry_choices = retry_data.get("choices") or []
                        if retry_choices:
                            retry_msg = retry_choices[0].get("message", {}) or {}
                            raw_text = (retry_msg.get("content") or "").strip()
                            if not raw_text:
                                raw_text = (retry_msg.get("reasoning") or retry_msg.get("reasoning_content") or "").strip()
        except httpx.HTTPStatusError as e:
            resp_body = e.response.text[:500] if e.response is not None else ""
            error_msg = f"HTTP {e.response.status_code}: {resp_body}"
            logger.error("EventsRouter HTTP call failed (%s): %s", e.response.status_code, resp_body)
            if e.response is not None and e.response.status_code == 429:
                OpenRouterRateLimitManager.record_429(
                    status_code=429,
                    headers=e.response.headers,
                    body_text=e.response.text,
                )
        except Exception as e:
            error_msg = str(e)
            logger.error("EventsRouter HTTP call failed: %s", e)

        duration_ms = (time.perf_counter() - t0) * 1000

        if error_msg or not raw_text:
            return {
                "action": "SKIP",
                "event_id": None,
                "reason": f"LLM routing failed: {error_msg or 'empty response'}",
                "event_type": None,
                "broadcast_type": None,
                "location": None,
                "units": [],
                "status_detail": None,
                "raw_llm_output": raw_text,
                "duration_ms": duration_ms,
                "error": error_msg,
            }

        parsed = _clean_and_parse_json(raw_text)
        if not parsed:
            return {
                "action": "SKIP",
                "event_id": None,
                "reason": "Failed to parse valid JSON from LLM response",
                "event_type": None,
                "broadcast_type": None,
                "location": None,
                "units": [],
                "status_detail": None,
                "raw_llm_output": raw_text,
                "duration_ms": duration_ms,
                "error": "JSON parse error",
            }

        action = str(parsed.get("action") or "").strip().upper()
        if action not in ("CREATE", "ATTACH", "CLOSE", "BROADCAST", "SKIP"):
            if parsed.get("create") is True:
                action = "CREATE"
            elif parsed.get("attach") is True:
                action = "ATTACH"
            elif parsed.get("close") is True:
                action = "CLOSE"
            elif parsed.get("broadcast") is True:
                action = "BROADCAST"
            else:
                action = "SKIP"

        event_id = parsed.get("event_id")
        if event_id is not None:
            event_id = str(event_id).strip()
            if event_id.lower() in ("null", "none", ""):
                event_id = None

        reason = str(parsed.get("reason") or "").strip()
        event_type = parsed.get("event_type")
        if event_type:
            event_type = str(event_type).strip()

        broadcast_type = parsed.get("broadcast_type")
        if broadcast_type:
            broadcast_type = str(broadcast_type).strip().lower()
            if broadcast_type not in BROADCAST_TYPE_SLUGS:
                broadcast_type = None

        location = parsed.get("location")
        if location:
            location = str(location).strip()

        raw_units = parsed.get("units")
        units_list: List[str] = []
        if isinstance(raw_units, list):
            units_list = [str(u).strip() for u in raw_units if str(u).strip()]
        elif isinstance(raw_units, str) and raw_units.strip():
            units_list = [u.strip() for u in raw_units.split(",") if u.strip()]

        status_detail = parsed.get("status_detail")
        if status_detail:
            status_detail = str(status_detail).strip()

        return {
            "action": action,
            "event_id": event_id,
            "reason": reason,
            "event_type": event_type,
            "broadcast_type": broadcast_type,
            "location": location,
            "units": units_list,
            "status_detail": status_detail,
            "raw_llm_output": raw_text,
            "duration_ms": duration_ms,
            "error": None,
        }

    @classmethod
    def generate_event_summary(
        cls,
        *,
        event_type: Optional[str],
        location: Optional[str],
        units: Optional[str],
        status_detail: Optional[str],
        status: Optional[str] = "open",
        attachments: List[Dict[str, Any]],
        current_summary: Optional[str] = None,
        global_rules: Optional[str] = None,
    ) -> Optional[str]:
        """Generate a cumulative 1-3 sentence operational summary for an event header based on all attachments."""
        if not attachments:
            return current_summary

        is_limited, rem, reason = OpenRouterRateLimitManager.is_rate_limited()
        if is_limited:
            return current_summary

        settings = get_settings()
        cfg = getattr(settings.config, "openrouter", None) or getattr(settings.config, "incidents_ollama", None)

        api_key = openrouter_api_key(cfg)
        base_url = openrouter_base_url(cfg)
        model = openrouter_model(cfg)
        timeout_s = float(getattr(cfg, "timeout_seconds", 30) or 30)

        if not api_key:
            logger.warning("EventsRouter.generate_event_summary: OPENROUTER_API_KEY not configured.")
            return current_summary

        user_prompt = build_summary_user_prompt(
            event_type=event_type,
            location=location,
            units=units,
            status_detail=status_detail,
            status=status,
            attachments=attachments,
        )

        summary_sys = SUMMARY_SYSTEM_PROMPT
        if global_rules and global_rules.strip():
            summary_sys += (
                "\n\n### Global Area & Operational Rules (AUTHORITATIVE GROUND TRUTH):\n"
                "The following jurisdiction context, 10-codes, and regional operational rules are defined for this system:\n"
                f"[{global_rules.strip()}]\n"
                "- Use these definitions to accurately interpret radio shorthand, codes, and locations in the transcripts."
            )

        url = f"{base_url.rstrip('/')}/chat/completions"
        if not base_url.endswith("/v1") and not base_url.endswith("/api"):
            url = f"{base_url.rstrip('/')}/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://scanscribe.local",
            "X-Title": "ScanScribe",
        }

        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": summary_sys},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 512,
            "include_reasoning": False,
            "reasoning": {
                "effort": "none",
                "exclude": True,
            },
        }

        try:
            with httpx.Client(timeout=timeout_s) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                res_data = response.json()
                choices = res_data.get("choices") or []
                if choices:
                    raw_text = choices[0].get("message", {}).get("content", "") or ""
                    cleaned = re.sub(r'<(?:think|thought|reasoning)>.*?</(?:think|thought|reasoning)>', '', raw_text, flags=re.DOTALL | re.IGNORECASE).strip()
                    cleaned = re.sub(r'^(?:Here is (?:the|a) (?:concise )?summary:?|Summary:)\s*', '', cleaned, flags=re.IGNORECASE)
                    cleaned = cleaned.strip().strip('"\'“”`')
                    if cleaned:
                        return cleaned
        except httpx.HTTPStatusError as e:
            resp_body = e.response.text[:500] if e.response is not None else ""
            logger.error("EventsRouter summary call failed (%s): %s", e.response.status_code, resp_body)
            if e.response is not None and e.response.status_code == 429:
                OpenRouterRateLimitManager.record_429(
                    status_code=429,
                    headers=e.response.headers,
                    body_text=e.response.text,
                )
        except Exception as e:
            logger.error("EventsRouter summary call failed: %s", e)

        return current_summary


SUMMARY_SYSTEM_PROMPT = """You are an expert 911 / Public Safety Incident Communications Officer.
Your task is to write a concise, objective, and factual 1 to 3 sentence operational summary of an incident based on the chronological sequence of radio transmissions attached to it.

Guidelines:
- State the nature of the incident, the location, key responding units, and the current operational status or outcome.
- Synthesize the narrative progression (e.g. initial dispatch -> unit arrival/findings -> current action or resolution).
- Be concise, professional, and factual. Do not speculate or invent details not present in the transcripts.
- Output ONLY the plain text summary (no markdown formatting, no quotes, no conversational preamble)."""


def build_summary_user_prompt(
    *,
    event_type: Optional[str],
    location: Optional[str],
    units: Optional[str],
    status_detail: Optional[str],
    status: Optional[str] = "open",
    attachments: List[Dict[str, Any]],
) -> str:
    """Build user prompt for event header summarization from chronological attachments."""
    lines = [
        f"Incident Type: {event_type or 'Unknown Type'}",
        f"Location: {location or 'Unknown Location'}",
        f"Assigned Units: {units or 'None listed'}",
        f"Operational Status: {status_detail or 'Active'} ({status or 'open'})",
        "",
        "Chronological Radio Transmissions (Attachments):",
    ]
    if attachments:
        for idx, att in enumerate(attachments, 1):
            time_part = f"({att['time']}) " if att.get("time") else ""
            tg_part = f"[{att['talkgroup']}] " if att.get("talkgroup") else ""
            transcript = att.get("transcript") or ""
            lines.append(f"[{idx}] {time_part}{tg_part}\"{transcript}\"")
    else:
        lines.append("[No attached radio transmissions]")

    lines.append("")
    lines.append("Provide a concise 1-3 sentence operational summary for the event header:")
    return "\n".join(lines)

