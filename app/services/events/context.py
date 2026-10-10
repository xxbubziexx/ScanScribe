"""Context building and heuristics for the events pipeline."""
import logging
import re
from typing import Dict, List, Optional

from ...config import get_settings
from ...models.event import SystemSetting
from ..ner_service import parse_list_field

logger = logging.getLogger(__name__)

_EMERGENCY_KEYWORD_RE = re.compile(
    r"\b(?:"
    r"helicopter|medevac|air\s*evac|airevac|lifeflight|flight|air\s*care|eta|"
    r"crash|accident|collision|mva|mvc|overturned|rollover|"
    r"fire|smoke|structure|alarm|flames|working\s+fire|brush\s+fire|"
    r"scene|en\s*route|enroute|responding|arriving|arrived|staged|staging|clearing|"
    r"entrapped|entrapment|extrication|pin-?in|pinned|"
    r"patient|patients|injury|injuries|unresponsive|cpr|overdose|cardiac|"
    r"transport|transporting|hospital|er|trauma|"
    r"command|downgrade|second\s+page|second\s+tone|position|"
    r"shooting|shots|robbery|assault|pursuit|custody|arrest|suspect|"
    r"traffic\s+stop|standby|abort|"
    r"ems|medic|engine|ladder|truck|rescue|squad|battalion|chief|deputy|officer|trooper"
    r")\b",
    re.IGNORECASE,
)

_STANDALONE_CHATTER_PARTS = (
    r"10[\s-]?4(?:\s+(?:copy|thanks|thank\s+you|roger))?"
    r"|copy(?:\s+that|\s+thanks|\s+thank\s+you)?"
    r"|copied"
    r"|that'?s\s+clear"
    r"|roger(?:\s+that)?"
    r"|thanks?(?:\s+you)?"
    r"|thank\s+you(?:\s+sir|\s+ma'?am)?"
    r"|have\s+a\s+good\s+(?:night|one|day|shift)"
    r"|good\s+(?:night|morning|afternoon|evening)"
    r"|central\s+\d+"
    r"|dispatch\s+\d+"
    r"|ok(?:ay)?"
    r"|affirmative"
    r"|negative"
    r"|check\s+mdt"
    r"|\d{1,3}[\s,]+(?:\d{2}[:.]?\d{2}|\d{4})"
    r"|(?:\d{2}[:.]\d{2})"
)

_STANDALONE_CHATTER_RE = re.compile(
    rf"^(?:\s*(?:{_STANDALONE_CHATTER_PARTS})[\s.,!?-]*)+$",
    re.IGNORECASE,
)


def sort_entities_together(parts: List[str]) -> List[str]:
    def is_numeric(s: str) -> bool:
        return bool(s and s[0].isdigit())

    alpha = sorted([x for x in parts if x and not is_numeric(x)])
    numeric = sorted([x for x in parts if x and is_numeric(x)])
    return alpha + numeric


def is_pure_chatter(
    transcript: str,
    entities: Optional[Dict[str, List[str]]] = None,
) -> bool:
    """Zero-token pre-filter to detect pure acknowledgments, pleasantries, or non-operational chatter."""
    if not transcript or not transcript.strip():
        return True

    text = transcript.strip()

    if _EMERGENCY_KEYWORD_RE.search(text):
        return False

    if _STANDALONE_CHATTER_RE.match(text):
        return True

    words = re.findall(r"\b\w+\b", text)
    if len(words) < 5:
        has_entities = False
        if entities:
            for k in ("UNIT", "STATUS", "LOC", "ADDRESS", "EVT_TYPE"):
                vals = entities.get(k)
                if vals and any(bool(v and str(v).strip()) for v in vals):
                    has_entities = True
                    break
        if not has_entities:
            return True

    return False


def build_header_from_entities(entities: Dict[str, List[str]], transcript: str) -> Dict[str, Optional[str]]:
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
        return ", ".join(sort_entities_together(out)) if out else "N/A"

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


def merge_list_field(existing_raw: Optional[str], new_values: List[str]) -> str:
    """Merge new values into existing CSV/JSON list field, dedup case-insensitively, sort."""
    existing = parse_list_field(existing_raw)
    seen = {u.strip().lower() for u in existing if u}
    out = [u for u in existing if u]
    for v in new_values:
        v = (v or "").strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return ", ".join(sort_entities_together(out)) if out else "N/A"


def get_global_prompt_rules(events_db=None) -> str:
    """Fetch global system prompt rules, checking DB SystemSetting first, then config.yml."""
    if events_db is not None:
        try:
            setting = (
                events_db.query(SystemSetting)
                .filter(SystemSetting.key == "global_prompt_rules")
                .first()
            )
            if setting and setting.value and setting.value.strip():
                return setting.value.strip()
        except Exception as e:
            logger.debug("Failed reading global_prompt_rules from DB: %s", e)

    cfg = getattr(get_settings().config, "events_pipeline", None)
    cfg_rules = getattr(cfg, "global_prompt_rules", "") if cfg else ""
    return (cfg_rules or "").strip()


# Aliases for backward compatibility
_sort_entities_together = sort_entities_together
_is_pure_chatter = is_pure_chatter
_build_header_from_entities = build_header_from_entities
_merge_list_field = merge_list_field
