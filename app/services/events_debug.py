"""Debug log for Events pipeline (NER / LLM routing). Stored in scanscribe_events.db so it works across API workers."""
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from ..config import (
    get_settings,
    incidents_ollama_master_model,
    incidents_ollama_worker_model,
)
from ..database import EventsSessionLocal
from ..models.event import PipelineDebugLog

logger = logging.getLogger(__name__)

_DEBUG_DB_MAX = 600
_PRUNE_EVERY = 50  # amortize prune cost across N inserts
_prune_lock = threading.Lock()
_prune_counter = 0


def _json_serializable(obj: Any) -> Any:
    """Convert numpy/torch types to native Python for JSON."""
    try:
        import numpy as np
        if isinstance(obj, (np.floating, np.integer)):
            return float(obj) if isinstance(obj, np.floating) else int(obj)
    except ImportError:
        pass
    if hasattr(obj, "item"):  # numpy scalar
        return obj.item()
    if isinstance(obj, dict):
        return {k: _json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_serializable(x) for x in obj]
    return obj


_TRUNC_MAX = 8000


def _trunc(s: Optional[str], n: int = _TRUNC_MAX) -> str:
    if not s:
        return ""
    return s[:n] + ("..." if len(s) > n else "")


def _prune_old(db) -> None:
    n = db.query(func.count(PipelineDebugLog.id)).scalar() or 0
    if n <= _DEBUG_DB_MAX:
        return
    keep = (
        db.query(PipelineDebugLog.id)
        .order_by(PipelineDebugLog.id.desc())
        .limit(_DEBUG_DB_MAX)
        .subquery()
    )
    db.query(PipelineDebugLog).filter(PipelineDebugLog.id.notin_(keep)).delete(synchronize_session=False)
    db.commit()


def _maybe_prune(db) -> None:
    """Run _prune_old at most every _PRUNE_EVERY inserts to avoid COUNT+DELETE on the hot path."""
    global _prune_counter
    with _prune_lock:
        _prune_counter += 1
        should_prune = _prune_counter >= _PRUNE_EVERY
        if should_prune:
            _prune_counter = 0
    if should_prune:
        _prune_old(db)


def _debug_model_for_action(action: str) -> str:
    """Return configured LLM model for worker/master actions, else empty."""
    a = (action or "").strip().lower()
    if not a:
        return ""
    settings = get_settings()
    ollama_cfg = getattr(settings.config, "incidents_ollama", None)
    if ollama_cfg is None:
        return ""
    if a.startswith("worker_"):
        return incidents_ollama_worker_model(ollama_cfg)
    if a.startswith("master_"):
        return incidents_ollama_master_model(ollama_cfg)
    return ""


def append_pipeline_debug(
    monitor_id: int,
    log_entry_id: int,
    action: str,
    event_id: str,
    duration_ms: float,
    entities: dict,
    error: str = "",
    raw_output: List[dict] = None,
    transcript: str = "",
    llm_output: str = "",
) -> None:
    try:
        raw_str = json.dumps(_json_serializable(raw_output or []), indent=2)
    except (TypeError, ValueError):
        raw_str = str(raw_output)[:8000]
    row = {
        "ts": time.time(),
        "llm_model": _debug_model_for_action(action),
        "monitor_id": monitor_id,
        "log_entry_id": log_entry_id,
        "action": action,
        "event_id": event_id,
        "duration_ms": round(duration_ms, 1),
        "transcript": _trunc(transcript or "", 4000),
        "entities": json.dumps(_json_serializable(entities or {}), indent=2),
        "raw_output": _trunc(raw_str, 8000),
        "llm_output": _trunc(llm_output or "", 12000),
        "error": error[:500] if error else "",
    }
    try:
        payload = json.dumps(row, default=str)
    except (TypeError, ValueError) as e:
        logger.warning("events_debug: could not serialize row: %s", e)
        return
    db = EventsSessionLocal()
    try:
        db.add(PipelineDebugLog(payload_json=payload))
        db.commit()
        _maybe_prune(db)
    except Exception as e:
        logger.warning("events_debug: persist failed: %s", e)
        db.rollback()
    finally:
        db.close()


def append_ner(
    monitor_id: int,
    log_entry_id: int,
    action: str,
    event_id: str,
    duration_ms: float,
    entities: dict,
    error: str = "",
    raw_output: List[dict] = None,
    transcript: str = "",
    llm_output: str = "",
) -> None:
    """Backward-compatible alias for older call sites."""
    append_pipeline_debug(
        monitor_id=monitor_id,
        log_entry_id=log_entry_id,
        action=action,
        event_id=event_id,
        duration_ms=duration_ms,
        entities=entities,
        error=error,
        raw_output=raw_output,
        transcript=transcript,
        llm_output=llm_output,
    )


def get_recent(limit: int = 80) -> List[Dict[str, Any]]:
    """Return last N entries (newest first)."""
    lim = max(1, min(int(limit or 80), 200))
    db = EventsSessionLocal()
    try:
        rows = (
            db.query(PipelineDebugLog)
            .order_by(PipelineDebugLog.id.desc())
            .limit(lim)
            .all()
        )
        out: List[Dict[str, Any]] = []
        for r in rows:
            try:
                item = json.loads(r.payload_json)
                if "llm_model" not in item:
                    item["llm_model"] = item.get("role", "")
                out.append(item)
            except (json.JSONDecodeError, TypeError):
                continue
        return out
    except Exception as e:
        logger.warning("events_debug: read failed: %s", e)
        return []
    finally:
        db.close()


def clear_all() -> int:
    """Delete all debug rows. Returns number removed."""
    db = EventsSessionLocal()
    try:
        removed = db.query(PipelineDebugLog).delete(synchronize_session=False)
        db.commit()
        return int(removed or 0)
    except Exception as e:
        logger.warning("events_debug: clear failed: %s", e)
        db.rollback()
        return 0
    finally:
        db.close()
