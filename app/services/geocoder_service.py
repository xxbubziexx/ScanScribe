"""Address resolution and geocoding engine for public safety incidents.

Supports:
- OpenStreetMap Nominatim (default, free with courtesy rate limiting and user-agent)
- Google Maps Geocoding API (configured via GOOGLE_MAPS_API_KEY or GEOCODE_API_KEY)
- Mapbox Geocoding API (configured via MAPBOX_ACCESS_TOKEN or GEOCODE_API_KEY)
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
import time
from typing import Dict, NamedTuple, Optional, Tuple
from urllib.parse import quote_plus
import httpx

logger = logging.getLogger(__name__)


class GeocodeResult(NamedTuple):
    latitude: float
    longitude: float
    resolved_address: str


# In-memory thread-safe cache: cleaned query -> (GeocodeResult or None, timestamp)
_cache_lock = threading.Lock()
_geocode_cache: Dict[str, Tuple[Optional[GeocodeResult], float]] = {}
CACHE_TTL_SECONDS = 86400 * 7  # 7 days for valid geocodes
NEGATIVE_CACHE_TTL_SECONDS = 3600  # 1 hour for failed lookups

# Rate limiting for Nominatim (1 request per second max per OSM policy)
_nominatim_lock = threading.Lock()
_last_nominatim_request_time: float = 0.0
NOMINATIM_MIN_INTERVAL: float = 1.0


def clean_location_string(raw: str) -> str:
    """
    Clean raw location text extracted from NER or LLM triage.
    Removes common radio speech preambles like 'at the corner of', 'block of', etc.
    """
    if not raw:
        return ""

    text = raw.strip()

    # Remove quotes, brackets, and extra punctuation
    text = re.sub(r'["\'`\[\]]', '', text)

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)

    # Common speech preamble prefixes to strip
    preambles = [
        r'^(?:at\s+)?(?:the\s+)?corner\s+of\s+',
        r'^(?:at\s+)?(?:the\s+)?intersection\s+of\s+',
        r'^(?:in\s+)?(?:the\s+)?(?:area|vicinity)\s+of\s+',
        r'^(?:in\s+front\s+of|behind|across\s+from|near|at|by|off\s+of|off)\s+',
        r'^(?:the\s+)?\d+\s+hundred\s+block\s+of\s+',
        r'^(?:the\s+)?\d+\s+block\s+of\s+',
        r'^(?:approx(?:imately)?\s+)?',
    ]
    for pattern in preambles:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()

    # Standardize intersection delimiters (&, /, @, at -> and)
    text = re.sub(r'\s+[@/]\s+', ' and ', text)
    text = re.sub(r'\s*&\s*', ' and ', text)
    text = re.sub(r'\s+(?:at|and)\s+', ' and ', text, flags=re.IGNORECASE)
    
    # Handle "cross of X and Y" or "crossroads"
    text = re.sub(r'\bcross(?:roads?)?\s+of\b', '', text, flags=re.IGNORECASE).strip()

    # Remove trailing/leading punctuation
    text = text.strip(' ,.-;/')
    return text

def build_fallback_queries(raw_location: str, geo_region: Optional[str] = None) -> list[str]:
    """
    Generate progressively simpler queries. Nominatim is highly strict.
    If '100 Main St, County Jail' fails, we fallback to '100 Main St'.
    """
    queries = []
    
    # 1. The full cleaned query
    full = build_geocoding_query(raw_location, geo_region)
    if full:
        queries.append(full)
        
    cleaned = clean_location_string(raw_location)
    
    # 2. If it contains a comma (e.g. "104 South College Street, Arcadia"), try just the first part
    if ',' in cleaned:
        first_part = cleaned.split(',')[0].strip()
        fallback = build_geocoding_query(first_part, geo_region)
        if fallback and fallback not in queries:
            queries.append(fallback)
            
    # 3. If it contains an intersection ("and"), try just the first street
    if ' and ' in cleaned.lower():
        first_street = re.split(r'\s+and\s+', cleaned, flags=re.IGNORECASE)[0].strip()
        fallback = build_geocoding_query(first_street, geo_region)
        if fallback and fallback not in queries:
            queries.append(fallback)
            
    # 4. If it contains mid-sentence descriptors ("near", "just south of", "around"), try the part BEFORE it
    descriptor_match = re.search(r'\s+(?:near|just\s+(?:north|south|east|west)\s+of|around|past|towards?)\s+', cleaned, flags=re.IGNORECASE)
    if descriptor_match:
        before_desc = cleaned[:descriptor_match.start()].strip()
        fallback = build_geocoding_query(before_desc, geo_region)
        if fallback and fallback not in queries:
            queries.append(fallback)

    # 5. Try stripping highway directional jargon (e.g. "Highway 6732 Leadington exit southbound")
    if re.search(r'\s+(?:exit|southbound|northbound|eastbound|westbound)', cleaned, flags=re.IGNORECASE):
        no_dirs = re.sub(r'\s+(?:exit|southbound|northbound|eastbound|westbound).*$', '', cleaned, flags=re.IGNORECASE).strip()
        fallback = build_geocoding_query(no_dirs, geo_region)
        if fallback and fallback not in queries:
            queries.append(fallback)

    # 6. If it has hyphenated block numbers (e.g. "209-04 State Highway U"), strip the suffix
    if re.match(r'^\d+-\d+\s+', cleaned):
        de_hyphenated = re.sub(r'^(\d+)-\d+\s+', r'\1 ', cleaned)
        fallback = build_geocoding_query(de_hyphenated, geo_region)
        if fallback and fallback not in queries:
            queries.append(fallback)
            
    return queries


def build_geocoding_query(raw_location: str, geo_region: Optional[str] = None) -> str:
    """
    Format a complete query string by appending region context if needed.
    Example: '100 Main St' + 'Cook County, IL' -> '100 Main St, Cook County, IL'
    """
    cleaned = clean_location_string(raw_location)
    if not cleaned:
        return ""

    if not geo_region or not geo_region.strip():
        return cleaned

    region = geo_region.strip().strip(',')
    # If the cleaned text already includes the region or state, don't duplicate
    if region.lower() in cleaned.lower():
        return cleaned

    return f"{cleaned}, {region}"


def get_configured_provider() -> str:
    """
    Determine which geocoder provider to use.
    Can be explicitly set with GEOCODE_PROVIDER=nominatim|google|mapbox
    or auto-detected from available API keys.
    """
    explicit = os.getenv("GEOCODE_PROVIDER", "").strip().lower()
    if explicit in {"nominatim", "google", "mapbox"}:
        return explicit

    if os.getenv("GOOGLE_MAPS_API_KEY") or (os.getenv("GEOCODE_API_KEY") and explicit == "google"):
        return "google"
    if os.getenv("MAPBOX_ACCESS_TOKEN") or (os.getenv("GEOCODE_API_KEY") and explicit == "mapbox"):
        return "mapbox"

    return "nominatim"


def _geocode_nominatim_sync(query: str, timeout: float = 8.0) -> Optional[GeocodeResult]:
    """Geocode query using OpenStreetMap Nominatim with courtesy rate limiting."""
    global _last_nominatim_request_time

    with _nominatim_lock:
        now = time.time()
        elapsed = now - _last_nominatim_request_time
        if elapsed < NOMINATIM_MIN_INTERVAL:
            time.sleep(NOMINATIM_MIN_INTERVAL - elapsed)
        _last_nominatim_request_time = time.time()

    url = f"https://nominatim.openstreetmap.org/search?q={quote_plus(query)}&format=jsonv2&limit=1&addressdetails=1"
    headers = {
        "User-Agent": "ScanScribe-Geocoder/1.0 (Public Safety Scanner Audio Transcription; github.com/scanscribe)",
        "Accept": "application/json",
    }

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning("Nominatim HTTP %s for query '%s': %s", resp.status_code, query, resp.text[:200])
                return None
            data = resp.json()
            if not data or not isinstance(data, list) or len(data) == 0:
                logger.info("Nominatim returned no matches for '%s'", query)
                return None

            first = data[0]
            lat = float(first.get("lat"))
            lon = float(first.get("lon"))
            display_name = first.get("display_name", query)
            return GeocodeResult(latitude=lat, longitude=lon, resolved_address=display_name)
    except Exception as exc:
        logger.warning("Nominatim geocoding failed for '%s': %s", query, exc)
        return None


def _geocode_google_sync(query: str, timeout: float = 8.0) -> Optional[GeocodeResult]:
    """Geocode query using Google Maps Geocoding API."""
    api_key = os.getenv("GOOGLE_MAPS_API_KEY") or os.getenv("GEOCODE_API_KEY") or ""
    if not api_key:
        logger.warning("Google geocoding requested but GOOGLE_MAPS_API_KEY is not set")
        return None

    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={quote_plus(query)}&key={api_key}"
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                logger.warning("Google Geocoding HTTP %s for '%s'", resp.status_code, query)
                return None
            data = resp.json()
            status = data.get("status")
            if status != "OK" or not data.get("results"):
                logger.info("Google Geocoding status=%s for '%s'", status, query)
                return None

            first = data["results"][0]
            loc = first.get("geometry", {}).get("location", {})
            lat = float(loc.get("lat"))
            lon = float(loc.get("lng"))
            formatted_address = first.get("formatted_address", query)
            return GeocodeResult(latitude=lat, longitude=lon, resolved_address=formatted_address)
    except Exception as exc:
        logger.warning("Google geocoding failed for '%s': %s", query, exc)
        return None


def _geocode_mapbox_sync(query: str, timeout: float = 8.0) -> Optional[GeocodeResult]:
    """Geocode query using Mapbox Geocoding API."""
    access_token = os.getenv("MAPBOX_ACCESS_TOKEN") or os.getenv("GEOCODE_API_KEY") or ""
    if not access_token:
        logger.warning("Mapbox geocoding requested but MAPBOX_ACCESS_TOKEN is not set")
        return None

    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{quote_plus(query)}.json?access_token={access_token}&limit=1"
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                logger.warning("Mapbox Geocoding HTTP %s for '%s'", resp.status_code, query)
                return None
            data = resp.json()
            features = data.get("features", [])
            if not features:
                logger.info("Mapbox Geocoding returned no features for '%s'", query)
                return None

            first = features[0]
            center = first.get("center", [])
            if len(center) < 2:
                return None
            lon, lat = float(center[0]), float(center[1])
            place_name = first.get("place_name", query)
            return GeocodeResult(latitude=lat, longitude=lon, resolved_address=place_name)
    except Exception as exc:
        logger.warning("Mapbox geocoding failed for '%s': %s", query, exc)
        return None


def resolve_address_sync(
    raw_location: str,
    geo_region: Optional[str] = None,
    provider: Optional[str] = None,
    timeout: float = 8.0,
) -> Optional[GeocodeResult]:
    """
    Synchronously resolves a location string to coordinates and standardized address.
    Checks memory cache first.
    """
    if not raw_location or not raw_location.strip():
        return None

    queries_to_try = build_fallback_queries(raw_location, geo_region)
    if not queries_to_try:
        return None

    now = time.time()
    selected_provider = provider or get_configured_provider()
    
    for query in queries_to_try:
        cache_key = query.lower()

        with _cache_lock:
            cached = _geocode_cache.get(cache_key)
            if cached is not None:
                res, ts = cached
                ttl = CACHE_TTL_SECONDS if res is not None else NEGATIVE_CACHE_TTL_SECONDS
                if now - ts < ttl:
                    # If we found a cached hit, return it. If it's a cached miss, try next fallback
                    if res is not None:
                        return res
                    continue

        logger.info("Geocoding query '%s' with provider '%s'", query, selected_provider)

        result: Optional[GeocodeResult] = None
        if selected_provider == "google":
            result = _geocode_google_sync(query, timeout=timeout)
        elif selected_provider == "mapbox":
            result = _geocode_mapbox_sync(query, timeout=timeout)
        else:
            result = _geocode_nominatim_sync(query, timeout=timeout)

        # Fallback to Nominatim if proprietary provider failed and was not nominatim
        if result is None and selected_provider != "nominatim":
            logger.info("Falling back to Nominatim for '%s'", query)
            result = _geocode_nominatim_sync(query, timeout=timeout)

        with _cache_lock:
            _geocode_cache[cache_key] = (result, now)

        if result:
            logger.info("Geocoded '%s' -> (%f, %f) '%s'", query, result.latitude, result.longitude, result.resolved_address)
            return result
        else:
            logger.info("Failed to geocode '%s', trying fallback if available", query)

    return None


async def resolve_address(
    raw_location: str,
    geo_region: Optional[str] = None,
    provider: Optional[str] = None,
    timeout: float = 8.0,
) -> Optional[GeocodeResult]:
    """
    Asynchronously resolves a location string by offloading to a worker thread.
    """
    return await asyncio.to_thread(
        resolve_address_sync,
        raw_location,
        geo_region,
        provider,
        timeout,
    )
