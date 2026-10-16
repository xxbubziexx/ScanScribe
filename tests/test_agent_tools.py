"""Tests for Scanner Intelligence agent tools (read-only, bounded, ASR-aware)."""
import asyncio
import json
from datetime import datetime, timedelta

import pytest

from app.database import SessionLocal, init_db
from app.models.event import EntityObservation, Event, EventTranscriptLink, Monitor, SpanStore
from app.models.log_entry import LogEntry
from app.services.agent_tools import (
    ToolContext,
    TOOL_REGISTRY,
    execute_tool,
    gemini_tool_declarations,
    openai_tool_declarations,
)

MARK = "zq9marker"
TG = "ZQ9_AGENT_TEST_TG"


def _ctx() -> ToolContext:
    now = datetime.now()
    return ToolContext(scope_start=now - timedelta(hours=1), scope_end=now + timedelta(minutes=1), scope_desc="Past 1 Hour")


def _run(name, args):
    result, elapsed_ms = asyncio.run(execute_tool(name, args, _ctx()))
    assert elapsed_ms >= 0
    return result


@pytest.fixture(scope="module")
def seeded():
    init_db()
    now = datetime.now()
    db = SessionLocal()
    ids = {}
    try:
        rows = [
            ("a", now - timedelta(seconds=90), "Engine 4 en route to the do all street rollover " + MARK),
            ("b", now - timedelta(seconds=60), "Medic 12 requesting a tent fifty " + MARK),
            ("c", now - timedelta(seconds=30), "Dispatch copies ten four " + MARK),
            ("deleted", now - timedelta(seconds=20), "Deleted traffic should never appear " + MARK),
        ]
        for key, ts, text in rows:
            entry = LogEntry(
                filename=f"agent_test_{key}.mp3",
                timestamp=ts,
                log_date=ts.strftime("%Y-%m-%d"),
                transcript=text,
                talkgroup=TG,
                is_deleted=(key == "deleted"),
            )
            db.add(entry)
            db.flush()
            ids[key] = entry.id

        monitor = Monitor(name="ZQ9 Agent Monitor", talkgroup_ids="[]")
        db.add(monitor)
        db.flush()
        event = Event(
            event_id="zq9-agent-event",
            monitor_id=monitor.id,
            status="open",
            event_type="Vehicle Rollover",
            location=f"Duval and Main {MARK}",
            units=json.dumps(["Engine 4"]),
            summary="Rollover with Engine 4 responding.",
        )
        db.add(event)
        db.flush()
        db.add(EventTranscriptLink(event_id=event.id, log_entry_id=ids["a"]))

        span = SpanStore(monitor_id=monitor.id, talkgroup=TG, transcript=f"Unit 112 en route to 1155 Walton Dr {MARK}", log_entry_id=ids["a"])
        db.add(span)
        db.flush()
        db.add(EntityObservation(span_store_id=span.id, monitor_id=monitor.id, talkgroup=TG, log_entry_id=ids["a"], ts=now - timedelta(seconds=90), label="UNIT", canonical="UNIT 112", raw="unit 112"))
        db.add(EntityObservation(span_store_id=span.id, monitor_id=monitor.id, talkgroup=TG, log_entry_id=ids["a"], ts=now - timedelta(seconds=90), label="ADDRESS", canonical="1155 WALTON DR", raw="1155 walton dr"))
        db.commit()

        ids["monitor"] = monitor.id
        ids["event"] = event.id
        ids["span"] = span.id
    finally:
        db.close()

    yield ids

    db = SessionLocal()
    try:
        db.query(EntityObservation).filter(EntityObservation.monitor_id == ids["monitor"]).delete()
        db.query(SpanStore).filter(SpanStore.monitor_id == ids["monitor"]).delete()
        db.query(EventTranscriptLink).filter(EventTranscriptLink.event_id == ids["event"]).delete()
        db.query(Event).filter(Event.id == ids["event"]).delete()
        db.query(Monitor).filter(Monitor.id == ids["monitor"]).delete()
        db.query(LogEntry).filter(LogEntry.talkgroup == TG).delete()
        db.commit()
    finally:
        db.close()


def test_search_matches_and_excludes_deleted(seeded):
    res = _run("search_transcripts", {"query": MARK})
    assert not res.is_error
    assert res.count == 3
    assert f"[TX-{seeded['a']} " in res.content
    assert f"[TX-{seeded['deleted']} " not in res.content
    assert seeded["a"] in res.cited_ids


def test_search_match_all_vs_any(seeded):
    any_res = _run("search_transcripts", {"query": f"{MARK} medic", "match": "any"})
    all_res = _run("search_transcripts", {"query": f"{MARK} medic", "match": "all"})
    assert any_res.count == 3
    assert all_res.count == 1
    assert f"[TX-{seeded['b']} " in all_res.content


def test_search_escapes_like_wildcards(seeded):
    res = _run("search_transcripts", {"query": "zq9%"})
    assert res.count == 0


def test_search_empty_result_warns_about_asr(seeded):
    res = _run("search_transcripts", {"query": "qqqnomatchqqq"})
    assert res.count == 0
    assert "does not prove" in res.content


def test_search_talkgroup_filter(seeded):
    hit = _run("search_transcripts", {"query": MARK, "talkgroup": "agent_test_tg"})
    miss = _run("search_transcripts", {"query": MARK, "talkgroup": "NO_SUCH_TG"})
    assert hit.count == 3
    assert miss.count == 0


def test_search_invalid_arguments_return_errors(seeded):
    assert _run("search_transcripts", {"query": MARK, "limit": 0}).is_error
    assert _run("search_transcripts", {}).is_error
    bad_time = _run("search_transcripts", {"query": MARK, "start_time": "last tuesday"})
    assert bad_time.is_error and "ISO 8601" in bad_time.content
    reversed_window = _run(
        "search_transcripts",
        {"query": MARK, "start_time": "2026-10-14T18:00", "end_time": "2026-10-14T17:00"},
    )
    assert reversed_window.is_error


def test_surrounding_marks_target_and_neighbors(seeded):
    res = _run("get_surrounding_transmissions", {"tx_id": seeded["b"], "window_seconds": 120})
    assert not res.is_error
    assert f">> [TX-{seeded['b']} " in res.content
    assert f"[TX-{seeded['a']} " in res.content
    assert f"[TX-{seeded['c']} " in res.content
    assert f"[TX-{seeded['deleted']} " not in res.content


def test_surrounding_missing_transmission(seeded):
    res = _run("get_surrounding_transmissions", {"tx_id": 2_000_000_000})
    assert res.is_error
    assert "not found" in res.content


def test_incident_records_query_and_links(seeded):
    res = _run("get_incident_records", {"query": MARK, "status": "open", "hours": 24})
    assert not res.is_error
    assert res.count == 1
    assert "Vehicle Rollover" in res.content
    assert f"[TX-{seeded['a']}]" in res.content
    closed = _run("get_incident_records", {"query": MARK, "status": "closed"})
    assert closed.count == 0


def test_talkgroup_activity(seeded):
    res = _run("get_talkgroup_activity", {"query": "agent_test", "hours": 1})
    assert not res.is_error
    assert res.count == 1
    assert f"{TG}: 3 transmission(s)" in res.content


def test_lookup_ner_entities_query_unit(seeded):
    res = _run("lookup_ner_entities", {"query": "112", "label": "UNIT"})
    assert not res.is_error
    assert res.count >= 1
    assert "UNIT: 'UNIT 112'" in res.content
    assert f"[TX-{seeded['a']}" in res.content
    assert seeded["a"] in res.cited_ids


def test_lookup_ner_entities_query_address(seeded):
    res = _run("lookup_ner_entities", {"query": "walton", "label": "ADDRESS"})
    assert not res.is_error
    assert res.count >= 1
    assert "ADDRESS: '1155 WALTON DR'" in res.content
    assert f"[TX-{seeded['a']}" in res.content


def test_lookup_ner_entities_aggregation(seeded):
    res = _run("lookup_ner_entities", {"label": "UNIT"})
    assert not res.is_error
    assert res.count >= 1
    assert "'UNIT 112'" in res.content


def test_lookup_ner_entities_empty(seeded):
    res = _run("lookup_ner_entities", {"query": "nonexistent_unit_9999"})
    assert not res.is_error
    assert res.count == 0
    assert "No NER entity observations found" in res.content


def test_unknown_tool_is_reported_not_raised():
    res = _run("drop_all_tables", {})
    assert res.is_error
    assert "Unknown tool" in res.content


def test_provider_declarations_are_schema_safe():
    openai_names = {t["function"]["name"] for t in openai_tool_declarations()}
    gemini_decls = gemini_tool_declarations()[0]["functionDeclarations"]
    assert openai_names == set(TOOL_REGISTRY) == {d["name"] for d in gemini_decls}
    for decl in gemini_decls:
        blob = json.dumps(decl["parameters"])
        # Gemini rejects these JSON-schema keywords
        for banned in ("anyOf", "additionalProperties", '"default"', '"title"'):
            assert banned not in blob


def test_scope_time_range_preset(seeded):
    ctx = ToolContext()
    assert not ctx.is_scoped
    res, _ = asyncio.run(execute_tool("scope_time_range", {"preset": "today"}, ctx))
    assert not res.is_error
    assert ctx.is_scoped
    assert ctx.scope_start is not None
    assert "TIME SCOPE ESTABLISHED" in res.content
    assert res.count >= 3


def test_scope_time_range_explicit_iso(seeded):
    ctx = ToolContext()
    now = datetime.now()
    start_iso = (now - timedelta(hours=2)).isoformat()
    end_iso = (now + timedelta(minutes=5)).isoformat()
    res, _ = asyncio.run(execute_tool("scope_time_range", {"start_time": start_iso, "end_time": end_iso}, ctx))
    assert not res.is_error
    assert ctx.is_scoped
    assert "TIME SCOPE ESTABLISHED" in res.content


def test_unscoped_query_is_refused(seeded):
    ctx = ToolContext()
    assert not ctx.is_scoped
    # search_transcripts without scope must refuse
    res, _ = asyncio.run(execute_tool("search_transcripts", {"query": "Engine"}, ctx))
    assert res.is_error
    assert "REFUSED: No active time scope" in res.content

    # lookup_ner_entities without scope must refuse
    res_ner, _ = asyncio.run(execute_tool("lookup_ner_entities", {"query": "112"}, ctx))
    assert res_ner.is_error
    assert "REFUSED: No active time scope" in res_ner.content

    # Scope the context first
    scope_res, _ = asyncio.run(execute_tool("scope_time_range", {"preset": "today"}, ctx))
    assert not scope_res.is_error

    # Now search succeeds
    res_after, _ = asyncio.run(execute_tool("search_transcripts", {"query": "Engine"}, ctx))
    assert not res_after.is_error
    assert res_after.count >= 1

