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
    county: Optional[str] = None


# In-memory thread-safe cache: cleaned query -> (GeocodeResult or None, timestamp)
_cache_lock = threading.Lock()
_geocode_cache: Dict[str, Tuple[Optional[GeocodeResult], float]] = {}
CACHE_TTL_SECONDS = 86400 * 7  # 7 days for valid geocodes
NEGATIVE_CACHE_TTL_SECONDS = 3600  # 1 hour for failed lookups

# Rate limiting for Nominatim (1 request per second max per OSM policy)
_nominatim_lock = threading.Lock()
_last_nominatim_request_time: float = 0.0
NOMINATIM_MIN_INTERVAL: float = 1.0


DEFAULT_STATE = os.getenv("DEFAULT_GEO_STATE", "Missouri")
DEFAULT_GEO_REGION = os.getenv("DEFAULT_GEO_REGION", "Missouri")

STATE_TO_CODE: Dict[str, str] = {
    'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR', 'california': 'CA',
    'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE', 'florida': 'FL', 'georgia': 'GA',
    'hawaii': 'HI', 'idaho': 'ID', 'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA',
    'kansas': 'KS', 'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
    'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS', 'missouri': 'MO',
    'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV', 'new hampshire': 'NH', 'new jersey': 'NJ',
    'new mexico': 'NM', 'new york': 'NY', 'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH',
    'oklahoma': 'OK', 'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
    'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT', 'vermont': 'VT',
    'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV', 'wisconsin': 'WI', 'wyoming': 'WY',
}

US_STATES = set(STATE_TO_CODE.keys())
US_STATE_CODES = set(STATE_TO_CODE.values())


def has_state_context(text: str) -> bool:
    """Check if the text contains a recognized US state name or 2-letter abbreviation."""
    if not text:
        return False
    lower_text = text.lower()
    for st in US_STATES:
        if re.search(r'\b' + re.escape(st) + r'\b', lower_text):
            return True
    for code in US_STATE_CODES:
        if re.search(r',\s*' + code + r'(?:\b|\s*\d{5}|$)', text, flags=re.IGNORECASE):
            return True
        if re.search(r'\s+' + code + r'(?:\s+\d{5})?$', text, flags=re.IGNORECASE):
            return True
        if re.match(r'^' + code + r'$', text, flags=re.IGNORECASE):
            return True
    return False


def get_state_from_region(geo_region: Optional[str]) -> str:
    """Extract full state name from region, defaulting to DEFAULT_STATE."""
    if not geo_region:
        return DEFAULT_STATE
    lower = geo_region.lower()
    for st in US_STATES:
        if re.search(r'\b' + re.escape(st) + r'\b', lower):
            return st.title()
    for code in US_STATE_CODES:
        if re.search(r'(?:,\s*|\b)' + code + r'(?:\b|$)', geo_region, flags=re.IGNORECASE):
            # Map code back to full state name if possible
            for sname, scode in STATE_TO_CODE.items():
                if scode.lower() == code.lower():
                    return sname.title()
            return code.upper()
    return DEFAULT_STATE


def get_state_code(state_name_or_code: str) -> str:
    """Return 2-letter uppercase state code (defaults to 'MO')."""
    if not state_name_or_code:
        return 'MO'
    clean = state_name_or_code.strip().lower()
    if clean in STATE_TO_CODE:
        return STATE_TO_CODE[clean]
    clean_upper = state_name_or_code.strip().upper()
    if clean_upper in US_STATE_CODES:
        return clean_upper
    return 'MO'


def normalize_geo_region(geo_region: Optional[str]) -> str:
    """
    Ensure the region has state context (defaults to Missouri if no state specified).
    E.g. 'Iron County' -> 'Iron County, Missouri'
         'Cook County, IL' -> 'Cook County, IL'
         None -> 'Missouri'
    """
    if not geo_region or not geo_region.strip():
        return DEFAULT_GEO_REGION

    region = geo_region.strip().strip(',')
    if not has_state_context(region):
        return f"{region}, {DEFAULT_STATE}"
    return region


def extract_cross_street(raw: str) -> Tuple[str, Optional[str]]:
    """Extract and isolate cross street clause from raw location text."""
    if not raw:
        return "", None

    cross_patterns = [
        r'[,;\s]+(?:nearest\s+|closest\s+)?(?:cross(?:roads?|\s*streets?|\s*st)?|c/s|x-?streets?|x-?st|x/s|xs)(?:\s*(?:of|is|are|:))?\s+(.+)$',
        r'[,;\s]+cross\s+of\s+(.+)$',
        r'[,;\s]+cross\s+(.+)$',
    ]
    for pat in cross_patterns:
        m = re.search(pat, raw, flags=re.IGNORECASE)
        if m:
            cross = m.group(1).strip(' ,.-;/')
            primary = raw[:m.start()].strip(' ,.-;/')
            return primary, cross
    return raw, None



def normalize_county(name: str) -> str:
    """Standardize county names for comparison (e.g. 'St. Francois' -> 'saintfrancois')."""
    n = name.lower()
    n = re.sub(r'\bst\.?\b', 'saint', n)
    n = re.sub(r'\bste\.?\b', 'sainte', n)
    n = re.sub(r'\bcounty\b', '', n).strip()
    return re.sub(r'[^a-z0-9]', '', n)


def is_within_geo_region(resolved_address: str, resolved_county: Optional[str], geo_region: Optional[str]) -> bool:
    """
    Strictly verify that a geocoded address is within the monitor's locked jurisdiction.
    Prevents rural state-wide fallback searches from pinning in unrelated counties (e.g. Joplin / Carthage).
    """
    if not geo_region or not geo_region.strip():
        return True

    # Extract county from geo_region if present (e.g. 'St. Francois County, Missouri' -> 'saintfrancois')
    m = re.search(r'([A-Za-z.\s\-]+)\s+County', geo_region, flags=re.IGNORECASE)
    if m:
        target_county = normalize_county(m.group(1))
        if resolved_county:
            res_c = normalize_county(resolved_county)
            if target_county == res_c:
                return True
            if res_c and target_county != res_c:
                return False

        norm_display = normalize_county(resolved_address)
        return target_county in norm_display

    # Non-county geo_region (e.g. city or region name)
    first_part = geo_region.split(',')[0].strip().lower()
    return bool(re.search(r'\b' + re.escape(first_part) + r'\b', resolved_address.lower()))


def resolve_landmark_alias(raw_location: str) -> str:
    """
    Check if a raw location string matches a known local business, restaurant, or landmark alias.
    Maps local names (like 'Lady Queen' -> '523 Center St, Bismarck, MO') so free OSM can geocode them.
    """
    if not raw_location or not raw_location.strip():
        return raw_location

    loc_clean = raw_location.strip().lower()
    
    # Check custom user landmarks configured in config.yml first
    try:
        from ..config import get_settings
        settings = get_settings()
        cfg_landmarks = getattr(settings.config, "landmarks", None) or {}
        if isinstance(cfg_landmarks, dict):
            for k, v in cfg_landmarks.items():
                alias = k.lower().strip()
                if alias == loc_clean or re.search(r'\b' + re.escape(alias) + r'\b', loc_clean):
                    return str(v).strip()
    except Exception as e:
        logger.error(f"Failed to load custom landmarks from config: {e}")

    # Common built-in Missouri landmarks
    built_in = {
        "lady queen": "523 Center St, Bismarck, MO",
        "lady queene": "523 Center St, Bismarck, MO",
        "lady queen drive in": "523 Center St, Bismarck, MO",
        "lady queene drive in": "523 Center St, Bismarck, MO",
        "mineral area college": "5270 Flat River Rd, Park Hills, MO",
        "mac college": "5270 Flat River Rd, Park Hills, MO",
        "mac campus": "5270 Flat River Rd, Park Hills, MO",
    }
    if loc_clean in built_in:
        return built_in[loc_clean]

    # Also check if any alias is contained in the string
    for alias_key, alias_addr in built_in.items():
        if re.search(r'\b' + re.escape(alias_key) + r'\b', loc_clean):
            return alias_addr

    return raw_location

def clean_location_string(raw: str) -> str:
    """
    Clean raw location text extracted from NER or LLM triage.
    Removes cross streets attached to primary addresses, radio speech preambles,
    and standardizes intersection delimiters.
    """
    if not raw:
        return ""

    # First extract cross street if present at the end/mid
    primary, _ = extract_cross_street(raw)
    text = primary.strip()

    # Remove quotes, brackets, and extra punctuation
    text = re.sub(r'["\'`\[\]]', '', text)

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)

    # Common speech preamble prefixes to strip
    preambles = [
        r'^(?:at\s+)?(?:the\s+)?cross(?:roads?)?\s+of\s+',
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

    # Remove trailing/leading punctuation
    text = text.strip(' ,.-;/')
    return text


def strip_house_number(location_text: str) -> Optional[str]:
    """Strip leading house number or range (e.g. '12834 Springtown Road' -> 'Springtown Road')."""
    match = re.match(r'^\d+[-\w]*\s+(.+)$', location_text.strip())
    if match:
        return match.group(1).strip()
    return None


def strip_directional_indicators(text: str) -> str:
    """
    Strips directional prefixes or suffixes from road/highway names.
    E.g. 'Southbound US Highway 67' -> 'US Highway 67'
         'Northbound 67' -> '67'
         'Highway 32 Eastbound' -> 'Highway 32'
         'SB Hwy 67' -> 'Hwy 67'
         'NB Route OO' -> 'Route OO'
    """
    if not text:
        return ""
    t = text.strip()
    t = re.sub(r'^(?:southbound|northbound|eastbound|westbound|sb|nb|eb|wb)\s+', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s+(?:southbound|northbound|eastbound|westbound|sb|nb|eb|wb)$', '', t, flags=re.IGNORECASE)
    return t.strip()


def generate_highway_variants(location_text: str, state_code: str = 'MO') -> list[str]:
    """
    Generate naming variants for rural lettered routes, state highways, and county roads.
    In Missouri, lettered highways like 'State Highway U' are indexed in OSM as 'MO-U', 'MO U',
    'Highway U', or 'Route U'.
    """
    variants: list[str] = []

    # County Road variants: CR 202, County Road 202, Co Rd 202
    cr_pattern = r'\b(?:County\s+Road|Co\s+Rd|CR)\s+(\d+|[A-Za-z]{1,2})\b'
    m_cr = re.search(cr_pattern, location_text, flags=re.IGNORECASE)
    if m_cr:
        cr_id = m_cr.group(1).upper()
        prefix = location_text[:m_cr.start()].strip()
        suffix = location_text[m_cr.end():].strip()
        cr_forms = [
            f"County Road {cr_id}",
            f"CR {cr_id}",
            f"Co Rd {cr_id}",
        ]
        for crf in cr_forms:
            parts = [p for p in [prefix, crf, suffix] if p]
            var = " ".join(parts).strip()
            if var and var not in variants and var.lower() != location_text.lower():
                variants.append(var)
        return variants

    # Match: State Highway U, Highway U, Route U, State Route U, MO-U, MO 32, etc.
    pattern = r'\b(?:(?:State|US|U\.S\.|I|MO|[A-Z]{2})\s+)?(?:Highway|Hwy|Route|State\s+Route|State\s+Road|MO)\s+([A-Za-z]{1,2}|\d{1,3})\b'
    m = re.search(pattern, location_text, flags=re.IGNORECASE)
    if m:
        route_id = m.group(1).upper()
        prefix = location_text[:m.start()].strip()
        suffix = location_text[m.end():].strip()

        route_forms = [
            f"{state_code}-{route_id}",
            f"{state_code} {route_id}",
            f"Highway {route_id}",
            f"State Highway {route_id}",
            f"Route {route_id}",
            f"State Route {route_id}",
        ]
        if route_id.isdigit():
            route_forms.append(f"US-{route_id}")
            route_forms.append(f"US Highway {route_id}")
            route_forms.append(f"I-{route_id}")

        for rf in route_forms:
            parts = [p for p in [prefix, rf, suffix] if p]
            var = " ".join(parts).strip()
            if var and var not in variants and var.lower() != location_text.lower():
                variants.append(var)

    return variants


def build_geocoding_query(raw_location: str, geo_region: Optional[str] = None) -> str:
    """
    Format a complete query string by appending region/state context.
    Ensures Missouri or configured state context is present if not already in location.
    Example: '12834 Springtown Road' + None -> '12834 Springtown Road, Missouri'
             '100 Main St' + 'Cook County, IL' -> '100 Main St, Cook County, IL'
    """
    cleaned = clean_location_string(raw_location)
    if not cleaned:
        return ""

    if geo_region and geo_region.strip():
        region = normalize_geo_region(geo_region)
    else:
        if has_state_context(cleaned):
            region = ""
        else:
            region = DEFAULT_STATE

    if not region:
        return cleaned

    if region.lower() in cleaned.lower():
        return cleaned

    return f"{cleaned}, {region}"


def build_fallback_queries(raw_location: str, geo_region: Optional[str] = None) -> list[str]:
    """
    Generate progressively simpler queries with rural address fallbacks.
    1. Full cleaned primary query with full geo_region
    2. Lettered / numbered highway variants (e.g. '14588 MO-U, Missouri')
    3. Primary query and variants with state-only context (if county was in region)
    4. House number stripped -> road-only queries (e.g. 'Springtown Road, Missouri')
    5. Cross street fallbacks (intersections and cross road queries)
    6. Comma-separated parts & mid-sentence descriptors stripped
    """
    queries: list[str] = []

    state_name = get_state_from_region(geo_region)
    state_code = get_state_code(state_name)
    has_county_in_region = bool(geo_region and 'county' in geo_region.lower())

    def add_query(loc: str, region: Optional[str]):
        if not loc or not loc.strip():
            return
        q = build_geocoding_query(loc, region)
        if q and q not in queries:
            queries.append(q)

    aliased_raw = resolve_landmark_alias(raw_location)
    primary_raw, cross_street = extract_cross_street(aliased_raw)
    cleaned_primary = clean_location_string(primary_raw)
    if not cleaned_primary:
        return queries

    # 1. Full cleaned primary query with full geo_region
    add_query(cleaned_primary, geo_region)

    # 1b. Directional stripped queries (e.g. 'Southbound US Highway 67' -> 'US Highway 67')
    dir_stripped = strip_directional_indicators(cleaned_primary)
    if dir_stripped and dir_stripped.lower() != cleaned_primary.lower():
        add_query(dir_stripped, geo_region)
        for hwy_var in generate_highway_variants(dir_stripped, state_code):
            add_query(hwy_var, geo_region)
        if has_county_in_region:
            add_query(dir_stripped, state_name)
            for hwy_var in generate_highway_variants(dir_stripped, state_code):
                add_query(hwy_var, state_name)

    # 2. Highway variants with house number
    for hwy_var in generate_highway_variants(cleaned_primary, state_code):
        add_query(hwy_var, geo_region)

    # 3. Strip house number -> road-only queries WITH full geo_region
    road_only = strip_house_number(cleaned_primary)
    if road_only:
        add_query(road_only, geo_region)
        for hwy_var in generate_highway_variants(road_only, state_code):
            add_query(hwy_var, geo_region)

    # 4. State-only context fallbacks (DANGEROUS for generic streets, so we do it last)
    # This happens if Nominatim fails to map the county name properly.
    if has_county_in_region:
        add_query(cleaned_primary, state_name)
        for hwy_var in generate_highway_variants(cleaned_primary, state_code):
            add_query(hwy_var, state_name)
        
        if road_only:
            add_query(road_only, state_name)
            for hwy_var in generate_highway_variants(road_only, state_code):
                add_query(hwy_var, state_name)

    # 5. Cross street fallbacks (if cross street was extracted from raw input)
    if cross_street:
        cleaned_cross = clean_location_string(cross_street)
        if cleaned_cross:
            base_road = road_only or cleaned_primary
            if ' and ' not in base_road.lower() and ' and ' not in cleaned_cross.lower():
                add_query(f"{base_road} and {cleaned_cross}", geo_region)
                if has_county_in_region:
                    add_query(f"{base_road} and {cleaned_cross}", state_name)
            add_query(cleaned_cross, geo_region)
            if has_county_in_region:
                add_query(cleaned_cross, state_name)

    # 6. Comma-separated parts (e.g. "104 South College Street, Arcadia")
    if ',' in cleaned_primary:
        first_part = cleaned_primary.split(',')[0].strip()
        add_query(first_part, geo_region)
        first_part_no_num = strip_house_number(first_part)
        if first_part_no_num:
            add_query(first_part_no_num, geo_region)
            if has_county_in_region:
                add_query(first_part_no_num, state_name)

    # 7. Intersection: if it contains "and", try the first street alone
    if ' and ' in cleaned_primary.lower():
        first_street = re.split(r'\s+and\s+', cleaned_primary, flags=re.IGNORECASE)[0].strip()
        add_query(first_street, geo_region)
        if has_county_in_region:
            add_query(first_street, state_name)

    # 8. Mid-sentence descriptors ("near", "just south of", "around")
    desc_match = re.search(r'\s+(?:near|just\s+(?:north|south|east|west)\s+of|around|past|towards?)\s+', cleaned_primary, flags=re.IGNORECASE)
    if desc_match:
        before_desc = cleaned_primary[:desc_match.start()].strip()
        add_query(before_desc, geo_region)
        if has_county_in_region:
            add_query(before_desc, state_name)

    # 9. Strip directional exit jargon (e.g. "Highway 67 Leadington exit southbound")
    if re.search(r'\s+(?:exit|southbound|northbound|eastbound|westbound)', cleaned_primary, flags=re.IGNORECASE):
        no_dirs = re.sub(r'\s+(?:exit|southbound|northbound|eastbound|westbound).*$', '', cleaned_primary, flags=re.IGNORECASE).strip()
        add_query(no_dirs, geo_region)

    # 10. Hyphenated block numbers (e.g. "209-04 State Highway U")
    if re.match(r'^\d+-\d+\s+', cleaned_primary):
        de_hyphenated = re.sub(r'^(\d+)-\d+\s+', r'\1 ', cleaned_primary)
        add_query(de_hyphenated, geo_region)

    return queries


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
            address_obj = first.get("address", {})
            county = address_obj.get("county") or address_obj.get("city") or None
            return GeocodeResult(latitude=lat, longitude=lon, resolved_address=display_name, county=county)
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
            if geo_region and not is_within_geo_region(result.resolved_address, result.county, geo_region):
                logger.warning(
                    "Geocode rejected out-of-jurisdiction match: '%s' (county: %s) does not match monitor geo_region '%s'",
                    result.resolved_address,
                    result.county,
                    geo_region,
                )
                result = None
            else:
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


def reverse_geocode_sync(lat: float, lon: float, timeout: float = 8.0) -> Optional[str]:
    """
    Reverse geocodes coordinates (lat, lon) using OpenStreetMap Nominatim.
    Returns human-friendly formatted address string.
    """
    global _last_nominatim_request_time
    with _nominatim_lock:
        now = time.time()
        elapsed = now - _last_nominatim_request_time
        if elapsed < NOMINATIM_MIN_INTERVAL:
            time.sleep(NOMINATIM_MIN_INTERVAL - elapsed)
        _last_nominatim_request_time = time.time()

    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=jsonv2&addressdetails=1"
    headers = {"User-Agent": "ScanScribe-Geocoder/1.0"}
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                addr = data.get("address") or {}
                road = addr.get("road")
                house_number = addr.get("house_number")
                city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("hamlet") or addr.get("municipality")
                state = addr.get("state")
                postcode = addr.get("postcode")
                county = addr.get("county")

                parts = []
                if house_number and road:
                    parts.append(f"{house_number} {road}")
                elif road:
                    parts.append(road)

                if city:
                    parts.append(city)
                elif county:
                    parts.append(county)

                if state:
                    if postcode:
                        parts.append(f"{state} {postcode}")
                    else:
                        parts.append(state)

                if parts:
                    return ", ".join(parts)
                return data.get("display_name")
    except Exception as e:
        logger.error("Reverse geocoding failed for (%f, %f): %s", lat, lon, e)
    return None


def search_address_candidates(
    query: str,
    geo_region: Optional[str] = None,
    limit: int = 5,
    timeout: float = 8.0,
) -> list[dict]:
    """
    Search OpenStreetMap Nominatim for address suggestions matching query.
    Scoped to monitor's geo_region.
    """
    global _last_nominatim_request_time
    if not query or not query.strip():
        return []

    aliased = resolve_landmark_alias(query.strip())
    q = build_geocoding_query(aliased, geo_region)

    with _nominatim_lock:
        now = time.time()
        elapsed = now - _last_nominatim_request_time
        if elapsed < NOMINATIM_MIN_INTERVAL:
            time.sleep(NOMINATIM_MIN_INTERVAL - elapsed)
        _last_nominatim_request_time = time.time()

    url = f"https://nominatim.openstreetmap.org/search?q={quote_plus(q)}&format=jsonv2&addressdetails=1&limit={limit}"
    headers = {"User-Agent": "ScanScribe-Geocoder/1.0"}
    candidates = []
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                results = resp.json()
                for item in results:
                    lat_str = item.get("lat")
                    lon_str = item.get("lon")
                    if lat_str is None or lon_str is None:
                        continue
                    lat = float(lat_str)
                    lon = float(lon_str)
                    display_name = item.get("display_name", "")
                    addr = item.get("address", {})
                    county = addr.get("county", "")

                    if geo_region and not is_within_geo_region(display_name, county, geo_region):
                        continue

                    house_num = addr.get("house_number")
                    road = addr.get("road")
                    city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("hamlet") or addr.get("municipality")

                    short_label = ""
                    if house_num and road:
                        short_label = f"{house_num} {road}"
                    elif road:
                        short_label = road
                    else:
                        short_label = item.get("name") or display_name.split(",")[0]

                    if city:
                        short_label = f"{short_label}, {city}"

                    candidates.append({
                        "latitude": lat,
                        "longitude": lon,
                        "label": short_label,
                        "display_name": display_name,
                        "road": road or "",
                        "city": city or "",
                        "county": county,
                        "type": item.get("type", ""),
                    })
    except Exception as e:
        logger.error("Address candidate search failed for '%s': %s", query, e)
    return candidates

