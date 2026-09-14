"""Canonicalize NER entity strings for analytics (UNIT, LOC, EVT_TYPE, ADDRESS, STATUS, TIME).

Each rule turns variable raw NER output into a stable canonical form suitable for grouping
and counting. raw is preserved separately in EntityObservation so the dashboard can show
the original wording if needed.

Design notes:
- Pure functions; no DB, no settings.
- Conservative: when in doubt, return Title-Cased raw (never empty unless input is whitespace).
- Aliases live in this file for now (per Phase 1 decision); easy to lift to a DB table later
  without changing call sites.
"""
from __future__ import annotations

import re
from typing import Optional

_WS = re.compile(r"\s+")

SUPPORTED_LABELS = frozenset({"UNIT", "LOC", "ADDRESS", "EVT_TYPE", "STATUS", "TIME"})


def normalize_entity(label: str, raw: str) -> str:
    """Return clean unmutated entity span without heuristic dictionary rewrites."""
    if not raw:
        return ""
    cleaned = _WS.sub(" ", raw.strip().strip(".,;:\"'()"))
    if not cleaned or not any(c.isalnum() for c in cleaned):
        return ""
    return cleaned


def _normalize_time(raw: str) -> str:
    """Return clean time string."""
    return normalize_entity("TIME", raw)


def supported_labels() -> frozenset:
    """Labels supported in entity observations."""
    return SUPPORTED_LABELS
