"""Single-pass LLM router for public safety radio events using OpenRouter (OpenAI-compatible API)."""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

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

SYSTEM_PROMPT = """You are an expert 911 / Public Safety Dispatch Triage and Incident Routing Assistant.
Your task is to analyze an incoming radio transmission transcript for a specific public safety monitor (department/talkgroup) alongside any currently open incidents, and decide the appropriate routing action in a single step.

### Routing Actions:
1. "CREATE": The transcript describes a NEW, distinct emergency incident (e.g. structure fire, motor vehicle accident, medical emergency, robbery, shooting, brush fire, alarm, rescue) that is NOT already represented in the list of open incidents.
2. "ATTACH": The transcript is an update, continuation, status report, size-up, unit arrival, or response traffic belonging to one of the OPEN incidents. You MUST specify the exact "event_id" of that incident.
3. "CLOSE": The transcript explicitly concludes, clears, or terminates an active incident (e.g., "Command terminated, all units clear", "False alarm, scene cleared", "Patient refused transport, Medic 3 back in service", "Fire is out, returning to quarters"). You MUST specify the exact "event_id" of that incident.
4. "BROADCAST": The transcript is a general non-incident broadcast or administrative announcement (e.g., severe weather warning / tornado watch, road debris / hazard alert, CNI driver alert, attempt to locate / BOLO).
5. "SKIP": The transcript is uninformative routine radio chatter, unit status checks (e.g., just a unit number like "22"), brief acknowledgments ("10-4"), time checks ("93, 2140"), static / garbled noise, or unrelated administrative traffic. **CRITICAL: You MUST select SKIP for all meaningless chatter, EVEN IF the unit is currently assigned to an open incident.**

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
- **CRITICAL RULE ON CHATTER**: Do NOT attach meaningless chatter (e.g., "93, 2140", "22", "10-4", "Check MDT") to open incidents just because the unit matches. You MUST choose "SKIP". Attaching chatter resets the timer and prevents incidents from closing.
- **CRITICAL RULE ON UNAFFILIATED UNITS**: Do NOT attach a new unit (especially one going "10-8" or "in service") to an active incident unless that specific unit was ALREADY assigned to that incident. If unit 22 goes "10-8" but unit 22 is not on the open Traffic Stop, choose SKIP.
- If a transmission provides a meaningful update (location, status, patient condition) that matches the units, location, or nature of an active OPEN incident, choose "ATTACH".
- If a unit announces they are "10-8", "in service", or "clearing the scene" AND they belong to the open incident, choose "CLOSE" if they are the primary/last unit, or "ATTACH" if other units remain.
- Clean and normalize unit identifiers (e.g. "Engine 4", "Ladder 12", "Medic 2", "Squad 3", "Unit 102") and addresses (e.g. "124 Main St", "I-35 Mile Marker 200").
- If the monitor has NO open incidents and the transmission is not an incident (or just static / non-emergency), choose "SKIP".
- Output ONLY the JSON object. Do not include markdown preamble.
"""


def _clean_and_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Clean markdown code fences and parse JSON object."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    m = re.search(r"(\{.*\})", cleaned, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return None


def build_user_prompt(
    monitor_name: str,
    talkgroup: str,
    transcript: str,
    entities: Optional[Dict[str, List[str]]] = None,
    open_incidents: Optional[List[Dict[str, Any]]] = None,
    recent_spans: Optional[List[str]] = None,
) -> str:
    """Build the single-pass prompt context."""
    user_content: List[str] = [
        f"Department/Monitor: {monitor_name or 'Default'}",
        f"Talkgroup: {talkgroup or 'Unknown'}",
        f"Current Transmission Transcript:\n\"{transcript}\"",
    ]

    if entities:
        ent_lines = []
        for k in sorted(entities.keys()):
            v = entities[k]
            if v:
                ent_lines.append(f"  - {k}: {', '.join(v)}")
        if ent_lines:
            user_content.append("Extracted Named Entities (NER):\n" + "\n".join(ent_lines))

    if open_incidents:
        inc_lines = []
        for inc in open_incidents:
            eid = inc.get("event_id")
            etype = inc.get("event_type") or "Unknown Type"
            loc = inc.get("location") or "Unknown Location"
            units_str = inc.get("units") or "None"
            sdetail = inc.get("status_detail") or "Active"
            transcripts = inc.get("recent_transcripts") or []
            t_summary = f" | Recent: {'; '.join(transcripts[-2:])}" if transcripts else ""
            inc_lines.append(
                f"- Event ID: {eid} | Type: {etype} | Location: {loc} | Units: {units_str} | Status: {sdetail}{t_summary}"
            )
        user_content.append("Currently Open Incidents on this Monitor:\n" + "\n".join(inc_lines))
    else:
        user_content.append("Currently Open Incidents on this Monitor: None (Idle)")

    if recent_spans:
        span_lines = [f"  - \"{s}\"" for s in recent_spans[-3:] if s]
        if span_lines:
            user_content.append("Recent Transmissions Context:\n" + "\n".join(span_lines))

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
        recent_spans: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Synchronously evaluate transcript and return routing decision."""
        settings = get_settings()
        cfg = getattr(settings.config, "openrouter", None) or getattr(settings.config, "incidents_ollama", None)
        
        api_key = openrouter_api_key(cfg)
        base_url = openrouter_base_url(cfg)
        model = openrouter_model(cfg)
        timeout_s = float(getattr(cfg, "timeout_seconds", 30) or 30)
        temperature = float(getattr(cfg, "temperature", 0.0) or 0.0)

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
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
            "max_tokens": 1024,
        }

        t0 = time.perf_counter()
        raw_text = ""
        error_msg = ""

        try:
            with httpx.Client(timeout=timeout_s) as client:
                response = client.post(url, headers=headers, json=payload)
                if response.status_code == 400 and "response_format" in response.text:
                    # Retry without response_format if model/provider rejects it
                    payload.pop("response_format", None)
                    response = client.post(url, headers=headers, json=payload)
                
                response.raise_for_status()
                res_data = response.json()
                choices = res_data.get("choices") or []
                if choices:
                    raw_text = choices[0].get("message", {}).get("content", "") or ""
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
