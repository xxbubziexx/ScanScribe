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

# ---------------------------------------------------------------------------
# UNIT
# ---------------------------------------------------------------------------
# Common radio-unit shorthand → expanded canonical form.
_UNIT_PREFIX_ALIASES = {
    "e": "Engine",
    "eng": "Engine",
    "engine": "Engine",
    "sq": "Squad",
    "squad": "Squad",
    "btl": "Battalion",
    "batt": "Battalion",
    "battalion": "Battalion",
    "lad": "Ladder",
    "lad.": "Ladder",
    "ladder": "Ladder",
    "med": "Medic",
    "medic": "Medic",
    "amb": "Ambulance",
    "ambulance": "Ambulance",
    "tk": "Tanker",
    "tnk": "Tanker",
    "tanker": "Tanker",
    "rsq": "Rescue",
    "rescue": "Rescue",
    "ch": "Chief",
    "chf": "Chief",
    "chief": "Chief",
    "tpr": "Trooper",
    "trooper": "Trooper",
    "dep": "Deputy",
    "deputy": "Deputy",
    "ofc": "Officer",
    "officer": "Officer",
    "u": "Unit",
    "unit": "Unit",
    "car": "Car",
}

# "E4" / "E-4" / "E 4" / "Eng 4" → ("e", "4"); preserves alphanumeric tails like 12U-1771.
_UNIT_PREFIX_NUMBER = re.compile(r"^([A-Za-z]+\.?)[\s\-]*([0-9][\w\-]*)$")


def _normalize_unit(raw: str) -> str:
    s = _WS.sub(" ", (raw or "").strip())
    if not s:
        return ""
    m = _UNIT_PREFIX_NUMBER.match(s)
    if m:
        prefix, number = m.group(1).lower().rstrip("."), m.group(2)
        expanded = _UNIT_PREFIX_ALIASES.get(prefix)
        if expanded:
            return f"{expanded} {number}"
    # Multi-word units: Title Case each word; preserve internal hyphens/digits.
    return " ".join(p[:1].upper() + p[1:].lower() if p.isalpha() else p for p in s.split(" "))


# ---------------------------------------------------------------------------
# LOC (streets, intersections, named places like Walmart, Dollar General)
# ---------------------------------------------------------------------------
# Lowercase key → canonical Title Case (extend as new businesses/landmarks show up).
_LOC_ALIASES = {
    "walmart": "Walmart",
    "wal-mart": "Walmart",
    "wal mart": "Walmart",
    "dollar general": "Dollar General",
    "dg": "Dollar General",
    "family dollar": "Family Dollar",
    "dollar tree": "Dollar Tree",
    "target": "Target",
    "kroger": "Kroger",
    "publix": "Publix",
    "walgreens": "Walgreens",
    "cvs": "CVS",
    "mcdonald's": "McDonald's",
    "mcdonalds": "McDonald's",
}

# Street-suffix abbreviations → canonical full form for consistent grouping.
_STREET_SUFFIXES = {
    "ave": "Avenue",
    "av": "Avenue",
    "avenue": "Avenue",
    "blvd": "Boulevard",
    "boulevard": "Boulevard",
    "st": "Street",
    "street": "Street",
    "rd": "Road",
    "road": "Road",
    "hwy": "Highway",
    "highway": "Highway",
    "dr": "Drive",
    "drive": "Drive",
    "ln": "Lane",
    "lane": "Lane",
    "ct": "Court",
    "court": "Court",
    "pl": "Place",
    "place": "Place",
    "pkwy": "Parkway",
    "parkway": "Parkway",
    "ter": "Terrace",
    "terrace": "Terrace",
    "cir": "Circle",
    "circle": "Circle",
    "trl": "Trail",
    "trail": "Trail",
    "way": "Way",
}

_INTERSECTION_SPLIT = re.compile(r"\s+(?:&|and|at|/|@|\bx\b)\s+", re.IGNORECASE)


def _titlecase_word(w: str) -> str:
    if not w:
        return w
    if w.isupper() and len(w) <= 4:
        return w  # likely an initialism (CVS, NW)
    return w[:1].upper() + w[1:].lower()


def _normalize_street(text: str) -> str:
    parts = [p for p in re.split(r"\s+", text.strip()) if p]
    if not parts:
        return ""
    last = parts[-1].lower().rstrip(".")
    if last in _STREET_SUFFIXES:
        parts[-1] = _STREET_SUFFIXES[last]
    return " ".join(_titlecase_word(p) for p in parts)


def _normalize_loc(raw: str) -> str:
    s = _WS.sub(" ", (raw or "").strip())
    if not s:
        return ""
    low = s.lower()
    # Direct business/landmark alias.
    if low in _LOC_ALIASES:
        return _LOC_ALIASES[low]
    # Intersection: canonicalize each side, sort alphabetically so "5th & Main" == "Main & 5th".
    if _INTERSECTION_SPLIT.search(s):
        sides = [_normalize_street(side) for side in _INTERSECTION_SPLIT.split(s) if side.strip()]
        sides = [s2 for s2 in sides if s2]
        if len(sides) >= 2:
            return " & ".join(sorted(sides, key=str.lower))
    return _normalize_street(s)


# ---------------------------------------------------------------------------
# ADDRESS (numbered house addresses only)
# ---------------------------------------------------------------------------
_ADDRESS_HOUSE = re.compile(r"^\s*(\d+[A-Za-z]?)\s+(.+?)\s*$")


def _normalize_address(raw: str) -> str:
    s = _WS.sub(" ", (raw or "").strip())
    if not s:
        return ""
    m = _ADDRESS_HOUSE.match(s)
    if not m:
        # Not a clean "<number> <street>" form — fall back to street normalize so the row is still usable.
        return _normalize_street(s)
    number, rest = m.group(1).upper(), _normalize_street(m.group(2))
    return f"{number} {rest}".strip()


# ---------------------------------------------------------------------------
# EVT_TYPE
# ---------------------------------------------------------------------------
_EVT_TYPE_ALIASES = {
    "mva": "Motor Vehicle Accident",
    "mvc": "Motor Vehicle Accident",
    "mvi": "Motor Vehicle Accident",
    "mvas": "Motor Vehicle Accident",
    "auto accident": "Motor Vehicle Accident",
    "vehicle accident": "Motor Vehicle Accident",
    "struct fire": "Structure Fire",
    "structure fire": "Structure Fire",
    "house fire": "Structure Fire",
    "residential fire": "Structure Fire",
    "veh fire": "Vehicle Fire",
    "vehicle fire": "Vehicle Fire",
    "car fire": "Vehicle Fire",
    "brush fire": "Brush Fire",
    "grass fire": "Brush Fire",
    "ems call": "EMS Call",
    "medical call": "EMS Call",
    "medical": "EMS Call",
    "traffic stop": "Traffic Stop",
    "t stop": "Traffic Stop",
    "domestic": "Domestic Disturbance",
    "domestic dispute": "Domestic Disturbance",
    "alarm": "Alarm",
    "fire alarm": "Fire Alarm",
    "burglar alarm": "Burglar Alarm",
    "atl": "Attempt To Locate",
    "attempt to locate": "Attempt To Locate",
}


def _normalize_evt_type(raw: str) -> str:
    s = _WS.sub(" ", (raw or "").strip()).lower()
    if not s:
        return ""
    if s in _EVT_TYPE_ALIASES:
        return _EVT_TYPE_ALIASES[s]
    # Strip trailing words like "call" / "report" that hurt grouping.
    stripped = re.sub(r"\b(call|report|incident)$", "", s).strip()
    if stripped in _EVT_TYPE_ALIASES:
        return _EVT_TYPE_ALIASES[stripped]
    return " ".join(_titlecase_word(w) for w in s.split(" "))


# ---------------------------------------------------------------------------
# STATUS (operational status verbs)
# ---------------------------------------------------------------------------
_STATUS_ALIASES = {
    "enroute": "en route",
    "en-route": "en route",
    "en route": "en route",
    "on scene": "on scene",
    "onscene": "on scene",
    "on-scene": "on scene",
    "arrived": "on scene",
    "arrive": "on scene",
    "clear": "clear",
    "clr": "clear",
    "cleared": "clear",
    "in service": "in service",
    "inservice": "in service",
    "out of service": "out of service",
    "out service": "out of service",
    "available": "in service",
    "10-8": "in service",
    "10-7": "out of service",
    "10-23": "on scene",
    "10-97": "on scene",
    "10-42": "out of service",
}


def _normalize_status(raw: str) -> str:
    s = _WS.sub(" ", (raw or "").strip()).lower()
    if not s:
        return ""
    return _STATUS_ALIASES.get(s, s)


# ---------------------------------------------------------------------------
# TIME (24-hour mentions)
# ---------------------------------------------------------------------------
# 1430, 14:30, 14.30, 1430h, 1430 hours
_TIME_PATTERNS = [
    re.compile(r"^(?P<h>[01]?\d|2[0-3]):(?P<m>[0-5]\d)$"),
    re.compile(r"^(?P<h>[01]?\d|2[0-3])\.(?P<m>[0-5]\d)$"),
    re.compile(r"^(?P<h>[01]\d|2[0-3])(?P<m>[0-5]\d)\s*(?:h|hrs|hours)?$", re.IGNORECASE),
]


def _normalize_time(raw: str) -> str:
    s = _WS.sub(" ", (raw or "").strip().lower())
    if not s:
        return ""
    # Allow leading "at " etc.
    s = re.sub(r"^(at|@)\s+", "", s).strip()
    for pat in _TIME_PATTERNS:
        m = pat.match(s)
        if m:
            return f"{int(m.group('h')):02d}:{m.group('m')}"
    # Unparseable; preserve the raw text so dashboards can still bucket by literal value.
    return s


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_NORMALIZERS = {
    "UNIT": _normalize_unit,
    "LOC": _normalize_loc,
    "ADDRESS": _normalize_address,
    "EVT_TYPE": _normalize_evt_type,
    "STATUS": _normalize_status,
    "TIME": _normalize_time,
}


def normalize_entity(label: str, raw: str) -> str:
    """Return canonical form of a NER entity for analytics grouping. Empty string if unparseable.

    Unknown labels pass through with whitespace collapsed + Title Case so callers don't have
    to guard each insert.
    """
    if not raw:
        return ""
    fn = _NORMALIZERS.get((label or "").upper())
    if fn is None:
        return _WS.sub(" ", raw.strip())
    return fn(raw)


def supported_labels() -> frozenset:
    """Labels this module knows how to canonicalize."""
    return frozenset(_NORMALIZERS.keys())
