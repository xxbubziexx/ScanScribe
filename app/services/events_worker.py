"""Events pipeline backward-compatible facade.

This module delegates all operational logic to the modular `app.services.events`
package while maintaining full backward-compatibility for existing imports,
scripts, and tests.
"""
from __future__ import annotations

import logging

from ..config import get_settings
from ..database import EventsSessionLocal, LogsSessionLocal
from ..models.event import (
    EntityObservation,
    Event,
    EventTranscriptLink,
    Monitor,
    SpanStore,
    SystemSetting,
)
from ..models.log_entry import LogEntry
from .events_common import event_work_lock, parse_json_list
from .events_debug import append_ner as debug_append_ner, append_pipeline_debug
from .events_router_engine import (
    BROADCAST_TYPE_SLUGS,
    WORKER_BROADCAST_EVENT_TYPE,
    EventsRouter,
)
from .websocket import websocket_manager

# Re-export everything from the sub-modules
from .events.cleanup import (
    async_cleanup_loop,
    auto_close_stale_events,
    start_event_cleanup_worker,
    utc_from_event_created,
    utc_from_log_timestamp,
)
from .events.context import (
    _EMERGENCY_KEYWORD_RE,
    _STANDALONE_CHATTER_PARTS,
    _STANDALONE_CHATTER_RE,
    build_header_from_entities,
    is_pure_chatter,
    merge_list_field,
    sort_entities_together,
)


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

from .events.incidents import (
    _async_geocode_worker,
    _bounded_executor,
    create_event_full,
    dispatch_geocoding_for_event,
    infer_broadcast_slug_from_transcript,
    summarize_event_attachments,
)
from .events.pipeline import (
    _MONITOR_FP_CHECK_INTERVAL,
    _last_fp_check,
    _monitor_index_cache,
    _monitor_index_lock,
    build_monitor_talkgroup_index,
    ensure_ner_model_loaded,
    get_matching_monitor_ids,
    invalidate_monitor_index_cache,
    normalize_talkgroup_key,
    process_transcript_for_monitor,
)
from .events.spans import (
    comma_join_parts,
    entities_json,
    entity_observations_from_entities,
    span_store_from_entities,
)

logger = logging.getLogger(__name__)

# Private aliases for backwards compatibility with tests and monkeypatches
_utc_from_log_timestamp = utc_from_log_timestamp
_utc_from_event_created = utc_from_event_created
_auto_close_stale_events = auto_close_stale_events
_async_cleanup_loop = async_cleanup_loop

_sort_entities_together = sort_entities_together
_is_pure_chatter = is_pure_chatter
_build_header_from_entities = build_header_from_entities
_merge_list_field = merge_list_field

_dispatch_geocoding_for_event = dispatch_geocoding_for_event
_infer_broadcast_slug_from_transcript = infer_broadcast_slug_from_transcript
_create_event_full = create_event_full

_normalize_talkgroup_key = normalize_talkgroup_key
_build_monitor_talkgroup_index = build_monitor_talkgroup_index

_comma_join_parts = comma_join_parts
_entities_json = entities_json
_span_store_from_entities = span_store_from_entities
_entity_observations_from_entities = entity_observations_from_entities
