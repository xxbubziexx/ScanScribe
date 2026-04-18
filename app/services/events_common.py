"""Shared helpers for events pipeline."""
import json
import threading
from collections import defaultdict
from contextlib import contextmanager
from typing import Dict, Iterator, List, Optional


_event_work_locks: Dict[int, threading.Lock] = {}
_event_work_registry_lock = threading.Lock()


def _get_or_create_event_work_lock(event_db_id: int) -> threading.Lock:
    with _event_work_registry_lock:
        lock = _event_work_locks.get(event_db_id)
        if lock is None:
            lock = threading.Lock()
            _event_work_locks[event_db_id] = lock
    return lock


def try_acquire_event_work_lock(event_db_id: int) -> Optional[threading.Lock]:
    """Non-blocking per-event_id lock covering all Master writes (header + summary + foreground attach/close).

    Returns the acquired Lock on success (caller MUST `.release()` when done), or None if
    another worker already holds it (caller should skip its run to avoid stomping DB writes).
    """
    lock = _get_or_create_event_work_lock(event_db_id)
    return lock if lock.acquire(blocking=False) else None


@contextmanager
def event_work_lock(event_db_id: int) -> Iterator[None]:
    """Blocking per-event_id lock. Use for foreground attach/close commits that must not race
    background header/summary runs."""
    lock = _get_or_create_event_work_lock(event_db_id)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def parse_json_list(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        out = json.loads(raw)
        return [str(x).strip() for x in out] if isinstance(out, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def merge_entities_from_link_json_strings(entities_json_strings: List[Optional[str]]) -> Dict[str, List[str]]:
    """Merge NER entity dicts from JSON strings (e.g. EventTranscriptLink.entities_json values)."""
    merged: Dict[str, List[str]] = defaultdict(list)
    for raw in entities_json_strings:
        if not raw:
            continue
        try:
            ent = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(ent, dict):
            continue
        for k, v in ent.items():
            if isinstance(v, list):
                for x in v:
                    s = (str(x) if x is not None else "").strip()
                    if s:
                        merged[str(k)].append(s)
    return dict(merged)
