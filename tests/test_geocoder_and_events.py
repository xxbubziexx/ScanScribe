"""Unit and integration tests for Geocoder Service and Events Command Center endpoints."""
import os
import pytest
from app.services.geocoder_service import (
    clean_location_string,
    build_geocoding_query,
    resolve_address_sync,
    _geocode_cache,
    _cache_lock,
    GeocodeResult,
)
from app.database import init_db, EventsSessionLocal
from app.models.event import Monitor, Event


def test_clean_location_string():
    # Preambles
    assert clean_location_string("at the corner of Main St and 1st Ave") == "Main St and 1st Ave"
    assert clean_location_string("the 500 block of Washington St") == "Washington St"
    assert clean_location_string("near 1200 Elm Street") == "1200 Elm Street"
    assert clean_location_string("in front of 400 Oak Ave") == "400 Oak Ave"
    assert clean_location_string("approx 750 Maple Rd") == "750 Maple Rd"

    # Intersections
    assert clean_location_string("Route 59 & 75th St") == "Route 59 and 75th St"
    assert clean_location_string("Main / 1st") == "Main and 1st"
    assert clean_location_string("Main @ 1st") == "Main and 1st"

    # Empty & Punctuation
    assert clean_location_string("") == ""
    assert clean_location_string('  "100 State St,"  ') == "100 State St"


def test_build_geocoding_query():
    assert build_geocoding_query("100 Main St", "Cook County, IL") == "100 Main St, Cook County, IL"
    assert build_geocoding_query("100 Main St, Cook County, IL", "Cook County, IL") == "100 Main St, Cook County, IL"
    assert build_geocoding_query("100 Main St", None) == "100 Main St"
    assert build_geocoding_query("", "Cook County, IL") == ""


def test_geocoder_caching():
    with _cache_lock:
        _geocode_cache.clear()

    # Pre-populate cache
    test_key = "123 fake st, springfield, il".lower()
    mock_res = GeocodeResult(latitude=39.7817, longitude=-89.6501, resolved_address="123 Fake St, Springfield, IL")
    with _cache_lock:
        _geocode_cache[test_key] = (mock_res, 9999999999.0)

    res = resolve_address_sync("123 Fake St", "Springfield, IL")
    assert res is not None
    assert res.latitude == 39.7817
    assert res.longitude == -89.6501
    assert res.resolved_address == "123 Fake St, Springfield, IL"


def test_monitor_geo_region_and_event_coordinates():
    os.makedirs("./data", exist_ok=True)
    os.makedirs("./logs", exist_ok=True)
    init_db()

    db = EventsSessionLocal()
    try:
        # Test monitor with geo_region
        mon = Monitor(
            name="Test Police Dispatch",
            talkgroup_ids='["POLICE_DISP"]',
            keyword_config='["EVT_TYPE"]',
            geo_region="Will County, IL",
        )
        db.add(mon)
        db.commit()
        db.refresh(mon)
        assert mon.id is not None
        assert mon.geo_region == "Will County, IL"

        # Test event with coordinates
        ev = Event(
            event_id="test_geo_evt_1",
            monitor_id=mon.id,
            status="open",
            event_type="Traffic Accident",
            location="Route 59 and 75th St",
            latitude=41.7500,
            longitude=-88.2000,
            resolved_address="IL-59 & 75th St, Naperville, IL",
            units="Squad 1, Squad 2",
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)

        assert ev.id is not None
        assert ev.latitude == 41.7500
        assert ev.longitude == -88.2000
        assert ev.resolved_address == "IL-59 & 75th St, Naperville, IL"

        # Cleanup
        db.delete(ev)
        db.delete(mon)
        db.commit()
    finally:
        db.close()
