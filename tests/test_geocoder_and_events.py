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
    assert clean_location_string("cross of Wood Lane and Main St") == "Wood Lane and Main St"
    assert clean_location_string("crossroads of Wood Lane and Main St") == "Wood Lane and Main St"

    # Cross street stripping from primary addresses
    assert clean_location_string("9007 Crossman Road cross of Wood Lane") == "9007 Crossman Road"
    assert clean_location_string("9007 Crossman Road cross street Wood Lane") == "9007 Crossman Road"
    assert clean_location_string("9007 Crossman Road, cross of Wood Lane") == "9007 Crossman Road"
    assert clean_location_string("9007 Crossman Road c/s Wood Lane") == "9007 Crossman Road"
    assert clean_location_string("9007 Crossman Road cross streets Wood Lane and Main St") == "9007 Crossman Road"

    # Intersections
    assert clean_location_string("Route 59 & 75th St") == "Route 59 and 75th St"
    assert clean_location_string("Main / 1st") == "Main and 1st"
    assert clean_location_string("Main @ 1st") == "Main and 1st"

    # Empty & Punctuation
    assert clean_location_string("") == ""
    assert clean_location_string('  "100 State St,"  ') == "100 State St"


def test_build_geocoding_query():
    # Context appending
    assert build_geocoding_query("100 Main St", "Cook County, IL") == "100 Main St, Cook County, IL"
    assert build_geocoding_query("100 Main St, Cook County, IL", "Cook County, IL") == "100 Main St, Cook County, IL"
    assert build_geocoding_query("100 Main St, Chicago, IL", None) == "100 Main St, Chicago, IL"
    assert build_geocoding_query("12834 Springtown Road", None) == "12834 Springtown Road, Missouri"
    assert build_geocoding_query("14588 State Highway U", "Iron County") == "14588 State Highway U, Iron County, Missouri"
    assert build_geocoding_query("14588 State Highway U", "Iron County, Missouri") == "14588 State Highway U, Iron County, Missouri"
    assert build_geocoding_query("9007 Crossman Road cross of Wood Lane", "St. Francois County") == "9007 Crossman Road, St. Francois County, Missouri"
    assert build_geocoding_query("", "Cook County, IL") == ""


def test_build_fallback_queries():
    from app.services.geocoder_service import build_fallback_queries

    # 1. House number stripping
    springtown_fallbacks = build_fallback_queries("12834 Springtown Road", None)
    assert "12834 Springtown Road, Missouri" in springtown_fallbacks
    assert "Springtown Road, Missouri" in springtown_fallbacks

    # 2. Lettered / numbered highway variants
    hwy_fallbacks = build_fallback_queries("14588 State Highway U", None)
    assert "14588 State Highway U, Missouri" in hwy_fallbacks
    assert "14588 MO-U, Missouri" in hwy_fallbacks
    assert "14588 Highway U, Missouri" in hwy_fallbacks
    assert "State Highway U, Missouri" in hwy_fallbacks
    assert "MO-U, Missouri" in hwy_fallbacks
    assert "Highway U, Missouri" in hwy_fallbacks

    # 3. Cross street fallbacks
    cross_fallbacks = build_fallback_queries("9007 Crossman Road cross of Wood Lane", "St. Francois County, Missouri")
    assert "9007 Crossman Road, St. Francois County, Missouri" in cross_fallbacks
    assert "Crossman Road, St. Francois County, Missouri" in cross_fallbacks
    assert "Crossman Road and Wood Lane, St. Francois County, Missouri" in cross_fallbacks
    assert "Wood Lane, St. Francois County, Missouri" in cross_fallbacks

    # 4. State route prioritization: 'MO 8' and 'MO-8' must appear before 'Highway 8'
    hwy8_fallbacks = build_fallback_queries("12834 Highway 8", "Washington County, Missouri")
    mo_8_idx = hwy8_fallbacks.index("12834 MO 8, Washington County, Missouri")
    mo_dash_8_idx = hwy8_fallbacks.index("12834 MO-8, Washington County, Missouri")
    raw_hwy_8_idx = hwy8_fallbacks.index("12834 Highway 8, Washington County, Missouri")
    assert mo_8_idx < raw_hwy_8_idx, "MO 8 variant must be queried before raw Highway 8"
    assert mo_dash_8_idx < raw_hwy_8_idx, "MO-8 variant must be queried before raw Highway 8"


def test_get_state_from_region():
    from app.services.geocoder_service import get_state_from_region, has_state_context

    assert get_state_from_region("Washington County, Missouri") == "Missouri"
    assert get_state_from_region("Washington County, MO") == "Missouri"
    assert get_state_from_region("Washington County") == "Missouri"
    assert get_state_from_region("Cook County, IL") == "Illinois"
    assert get_state_from_region("Harris County, Texas") == "Texas"
    assert get_state_from_region(None) == "Missouri"

    # has_state_context
    assert has_state_context("Washington County, Missouri") is True
    assert has_state_context("Washington County") is False
    assert has_state_context("100 Main St, Chicago, IL") is True
    assert has_state_context("12834 Springtown Road") is False


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


def test_event_updated_at_and_feed_ordering():
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import func

    os.makedirs("./data", exist_ok=True)
    os.makedirs("./logs", exist_ok=True)
    init_db()

    db = EventsSessionLocal()
    try:
        mon = Monitor(
            name="Feed Order Test Dispatch",
            talkgroup_ids='["ORDER_TEST"]',
            keyword_config='["EVT_TYPE"]',
        )
        db.add(mon)
        db.commit()
        db.refresh(mon)

        now = datetime.now(timezone.utc)
        # Event A: created 2 hours ago
        ev_a = Event(
            event_id="order_test_ev_a",
            monitor_id=mon.id,
            status="open",
            event_type="Structure Fire",
            created_at=now - timedelta(hours=2),
            updated_at=now - timedelta(hours=2),
        )
        # Event B: created 1 hour ago
        ev_b = Event(
            event_id="order_test_ev_b",
            monitor_id=mon.id,
            status="open",
            event_type="Medical Emergency",
            created_at=now - timedelta(hours=1),
            updated_at=now - timedelta(hours=1),
        )
        db.add_all([ev_a, ev_b])
        db.commit()
        db.refresh(ev_a)
        db.refresh(ev_b)

        # Initial query sorted by updated_at descending: ev_b (1h ago) before ev_a (2h ago)
        res = (
            db.query(Event)
            .filter(Event.monitor_id == mon.id)
            .order_by(func.coalesce(Event.updated_at, Event.created_at).desc(), Event.id.desc())
            .all()
        )
        assert [e.event_id for e in res] == ["order_test_ev_b", "order_test_ev_a"]

        # Now simulate a new span being attached to Event A
        ev_a.updated_at = datetime.now(timezone.utc)
        db.commit()

        # Query again: ev_a has a new span and must now be at the very top!
        res_after = (
            db.query(Event)
            .filter(Event.monitor_id == mon.id)
            .order_by(func.coalesce(Event.updated_at, Event.created_at).desc(), Event.id.desc())
            .all()
        )
        assert [e.event_id for e in res_after] == ["order_test_ev_a", "order_test_ev_b"]

        # Cleanup
        db.delete(ev_a)
        db.delete(ev_b)
        db.delete(mon)
        db.commit()
    finally:
        db.close()

