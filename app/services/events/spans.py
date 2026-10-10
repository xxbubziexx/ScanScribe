"""Span persistence and entity observation extraction."""
from datetime import datetime, timezone
import json
import logging
from typing import Dict, List, Optional

from ...models.event import EntityObservation, SpanStore
from ..entity_normalize import supported_labels as _entity_supported_labels

logger = logging.getLogger(__name__)


def comma_join_parts(parts: List[str]) -> Optional[str]:
    out = [((p or "").strip()) for p in parts if (p or "").strip()]
    return ", ".join(out) if out else None


def entities_json(entities: Dict[str, List[str]]) -> Optional[str]:
    if not entities:
        return None
    try:
        return json.dumps(entities)
    except (TypeError, ValueError):
        return None


def span_store_from_entities(
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
        evt_type=comma_join_parts(entities.get("EVT_TYPE", [])),
        units=comma_join_parts(entities.get("UNIT", [])),
        locations=comma_join_parts(entities.get("LOC", [])),
        addresses=comma_join_parts(entities.get("ADDRESS", [])),
        status=comma_join_parts(entities.get("STATUS", [])),
        time_mentions=comma_join_parts(entities.get("TIME", [])),
        log_entry_id=log_entry_id,
    )


def entity_observations_from_entities(
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
            cleaned_span = raw.strip().strip(".,;:\"'()")
            if not cleaned_span or not any(c.isalnum() for c in cleaned_span):
                continue
            out.append(
                EntityObservation(
                    span_store_id=span_store_id,
                    monitor_id=monitor_id,
                    talkgroup=talkgroup or None,
                    log_entry_id=log_entry_id,
                    ts=ts or datetime.now(timezone.utc),
                    label=label,
                    canonical=cleaned_span[:500],
                    raw=cleaned_span[:500],
                )
            )
    return out


# Aliases for backward compatibility
_comma_join_parts = comma_join_parts
_entities_json = entities_json
_span_store_from_entities = span_store_from_entities
_entity_observations_from_entities = entity_observations_from_entities
