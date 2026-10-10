"""Events pipeline service package."""
from .cleanup import (
    auto_close_stale_events,
    start_event_cleanup_worker,
    utc_from_event_created,
    utc_from_log_timestamp,
)
from .context import (
    build_header_from_entities,
    get_global_prompt_rules,
    is_pure_chatter,
    merge_list_field,
    sort_entities_together,
)
from .incidents import (
    create_event_full,
    dispatch_geocoding_for_event,
    infer_broadcast_slug_from_transcript,
    summarize_event_attachments,
)
from .pipeline import (
    build_monitor_talkgroup_index,
    ensure_ner_model_loaded,
    get_matching_monitor_ids,
    invalidate_monitor_index_cache,
    normalize_talkgroup_key,
    process_transcript_for_monitor,
)
from .spans import (
    comma_join_parts,
    entities_json,
    entity_observations_from_entities,
    span_store_from_entities,
)

__all__ = [
    # Cleanup
    "auto_close_stale_events",
    "start_event_cleanup_worker",
    "utc_from_event_created",
    "utc_from_log_timestamp",
    # Context
    "build_header_from_entities",
    "get_global_prompt_rules",
    "is_pure_chatter",
    "merge_list_field",
    "sort_entities_together",
    # Incidents
    "create_event_full",
    "dispatch_geocoding_for_event",
    "infer_broadcast_slug_from_transcript",
    "summarize_event_attachments",
    # Pipeline
    "build_monitor_talkgroup_index",
    "ensure_ner_model_loaded",
    "get_matching_monitor_ids",
    "invalidate_monitor_index_cache",
    "normalize_talkgroup_key",
    "process_transcript_for_monitor",
    # Spans
    "comma_join_parts",
    "entities_json",
    "entity_observations_from_entities",
    "span_store_from_entities",
]
