"""Parse 24-hour TIME NER entities into concrete datetimes for grounding.

The NER model now emits TIME mentions in 24h form ("14:30", "1430", "1430 hours"). This module
combines that with the LogEntry's date to produce a timezone-aware datetime usable as
`Event.incident_at` (when a single, unambiguous TIME is present) and as router prompt context.

Timezone: host system local (per user choice). Falls back to UTC if the host has no tzinfo.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timezone
from typing import Optional

from .entity_normalize import _normalize_time  # canonical "HH:MM" extractor

logger = logging.getLogger(__name__)

# Same shapes accepted by entity_normalize._normalize_time, but kept here so we can return
# the (hour, minute) tuple directly instead of round-tripping through a string.
_RAW_PATTERNS = [
    re.compile(r"^(?P<h>[01]?\d|2[0-3]):(?P<m>[0-5]\d)$"),
    re.compile(r"^(?P<h>[01]?\d|2[0-3])\.(?P<m>[0-5]\d)$"),
    re.compile(r"^(?P<h>[01]\d|2[0-3])(?P<m>[0-5]\d)\s*(?:h|hrs|hours)?$", re.IGNORECASE),
]


def _host_tz():
    """Local timezone of the running container/host; UTC if not detectable."""
    try:
        local = datetime.now().astimezone().tzinfo
        return local if local is not None else timezone.utc
    except Exception:
        return timezone.utc


def parse_24h_time(raw: str, log_date: Optional[date] = None) -> Optional[datetime]:
    """Combine a raw 24h NER TIME value with log_date → timezone-aware datetime in host TZ.

    Returns None if raw cannot be parsed as a clean HH:MM time. log_date defaults to today.
    """
    if not raw:
        return None
    s = re.sub(r"^(at|@)\s+", "", raw.strip().lower()).strip()
    h = m = None
    for pat in _RAW_PATTERNS:
        match = pat.match(s)
        if match:
            try:
                h = int(match.group("h"))
                m = int(match.group("m"))
            except (TypeError, ValueError):
                continue
            break
    if h is None or m is None or not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    d = log_date or datetime.now().date()
    try:
        return datetime.combine(d, time(hour=h, minute=m), tzinfo=_host_tz())
    except Exception as e:
        logger.debug("parse_24h_time: combine failed raw=%r log_date=%s: %s", raw, log_date, e)
        return None


def canonical_24h(raw: str) -> str:
    """Return canonical 'HH:MM' for a raw TIME entity (delegates to entity_normalize)."""
    return _normalize_time(raw)
