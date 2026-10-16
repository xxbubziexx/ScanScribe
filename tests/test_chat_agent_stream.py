"""Agentic streaming loop tests using a mocked LLM transport (no network)."""
import asyncio
import json
from datetime import datetime, timedelta

import httpx
import pytest

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.models.log_entry import LogEntry
from app.services import chat_streamer
from app.services.agent_tools import ToolContext
from app.services.chat_streamer import AssistantTrace, stream_chat_completion

MARK = "zq9stream"
TG = "ZQ9_STREAM_TEST_TG"


def _sse(*chunks) -> bytes:
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks)
    return body.encode()


def _install_transport(monkeypatch, handler):
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(chat_streamer.httpx, "AsyncClient", factory)


@pytest.fixture
def chat_cfg(monkeypatch):
    cfg = get_settings().config.chat
    monkeypatch.setattr(cfg, "enabled", True)
    monkeypatch.setattr(cfg, "api_key", "test-key")
    monkeypatch.setattr(cfg, "provider", "openrouter")
    monkeypatch.setattr(cfg, "model", "test/model")
    monkeypatch.setattr(cfg, "max_tool_iterations", 3)
    monkeypatch.setattr(cfg, "reasoning_enabled", True)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("CHAT_OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CHAT_GEMINI_API_KEY", "test-key")
    return cfg


@pytest.fixture(scope="module")
def seeded_tx():
    init_db()
    now = datetime.now()
    db = SessionLocal()
    try:
        entry = LogEntry(
            filename="stream_test.mp3",
            timestamp=now - timedelta(seconds=30),
            log_date=now.strftime("%Y-%m-%d"),
            transcript=f"Engine 9 on scene at the rollover {MARK}",
            talkgroup=TG,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        tx_id = entry.id
    finally:
        db.close()
    yield tx_id
    db = SessionLocal()
    try:
        db.query(LogEntry).filter(LogEntry.talkgroup == TG).delete()
        db.commit()
    finally:
        db.close()


def _ctx() -> ToolContext:
    now = datetime.now()
    return ToolContext(scope_start=now - timedelta(hours=1), scope_end=now + timedelta(minutes=1), scope_desc="Past 1 Hour")


def _collect(**kwargs):
    async def run():
        events = []
        async for chunk in stream_chat_completion(**kwargs):
            assert chunk.startswith("data: ")
            events.append(json.loads(chunk[6:].strip()))
        return events

    return asyncio.run(run())


def _stream_kwargs(tool_ctx):
    return dict(
        system_prompt="sys",
        context_text="ctx",
        conversation_history=[],
        user_prompt="what happened",
        meta_info={"time_desc": "Past 1 Hour"},
        tool_ctx=tool_ctx,
    )


def test_openrouter_agent_loop_emits_thinking_tool_and_answer(monkeypatch, chat_cfg, seeded_tx):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            payload = _sse(
                {"choices": [{"delta": {"reasoning": "Need to search the log. "}}]},
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_abc",
                                        "function": {"name": "search_transcripts", "arguments": '{"query": "zq9'},
                                    }
                                ]
                            }
                        }
                    ]
                },
                {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": 'stream"}'}}]}}]},
            ) + b"data: [DONE]\n\n"
        else:
            payload = _sse(
                {"choices": [{"delta": {"content": f"Engine 9 was on scene [TX-{seeded_tx}]."}}]},
            ) + b"data: [DONE]\n\n"
        return httpx.Response(200, content=payload, headers={"content-type": "text/event-stream"})

    _install_transport(monkeypatch, handler)
    events = _collect(**_stream_kwargs(_ctx()))
    kinds = [e["type"] for e in events]

    assert kinds[0] == "meta"
    assert "thinking" in kinds
    assert kinds.index("tool_call") < kinds.index("tool_result") < kinds.index("token")
    assert kinds[-1] == "done"

    call = next(e for e in events if e["type"] == "tool_call")
    assert call["tool"] == "search_transcripts"
    assert call["arguments"] == {"query": "zq9stream"}
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["status"] == "ok" and result["count"] == 1
    assert events[-1]["cited_log_ids"] == [seeded_tx]

    assert len(requests) == 2
    assert "tools" in requests[0] and requests[0]["reasoning"] == {"effort": chat_cfg.reasoning_effort}
    tool_msgs = [m for m in requests[1]["messages"] if m["role"] == "tool"]
    assert len(tool_msgs) == 1 and tool_msgs[0]["tool_call_id"] == "call_abc"
    assert f"[TX-{seeded_tx} " in tool_msgs[0]["content"]


def test_iteration_cap_removes_tools_and_forces_answer(monkeypatch, chat_cfg, seeded_tx):
    monkeypatch.setattr(chat_cfg, "max_tool_iterations", 1)
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if "tools" in body:
            payload = _sse(
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_loop",
                                        "function": {"name": "get_talkgroup_activity", "arguments": "{}"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ) + b"data: [DONE]\n\n"
        else:
            payload = _sse({"choices": [{"delta": {"content": "Final answer."}}]}) + b"data: [DONE]\n\n"
        return httpx.Response(200, content=payload)

    _install_transport(monkeypatch, handler)
    events = _collect(**_stream_kwargs(_ctx()))

    assert len(requests) == 2
    assert "tools" in requests[0] and "tools" not in requests[1]
    assert "Tool call limit reached" in requests[1]["messages"][-1]["content"]
    assert events[-1]["type"] == "done" and events[-1]["content"] == "Final answer."


def test_invalid_tool_arguments_surface_as_error_result_and_loop_continues(monkeypatch, chat_cfg):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            payload = _sse(
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_bad",
                                        "function": {"name": "search_transcripts", "arguments": "{not json"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ) + b"data: [DONE]\n\n"
        else:
            payload = _sse({"choices": [{"delta": {"content": "Could not search."}}]}) + b"data: [DONE]\n\n"
        return httpx.Response(200, content=payload)

    _install_transport(monkeypatch, handler)
    events = _collect(**_stream_kwargs(_ctx()))
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["status"] == "error"
    assert events[-1]["type"] == "done"


def test_no_tool_ctx_streams_plain_completion(monkeypatch, chat_cfg):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, content=_sse({"choices": [{"delta": {"content": "Plain."}}]}) + b"data: [DONE]\n\n")

    _install_transport(monkeypatch, handler)
    events = _collect(**_stream_kwargs(None))
    assert "tools" not in seen
    assert [e["type"] for e in events] == ["meta", "token", "done"]


def test_http_error_is_reported_without_leaking_key(monkeypatch, chat_cfg):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    _install_transport(monkeypatch, handler)
    events = _collect(**_stream_kwargs(_ctx()))
    assert events[-1]["type"] == "error"
    assert "429" in events[-1]["error"]
    assert "test-key" not in json.dumps(events)


def test_gemini_agent_loop_preserves_signature_and_uses_header_key(monkeypatch, chat_cfg, seeded_tx):
    monkeypatch.setattr(chat_cfg, "provider", "gemini")
    monkeypatch.setattr(chat_cfg, "model", "gemini-2.5-flash")
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert "key=" not in str(request.url)
        assert request.headers["x-goog-api-key"] == "test-key"
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            payload = _sse(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"text": "Searching for the rollover.", "thought": True},
                                    {
                                        "functionCall": {"name": "search_transcripts", "args": {"query": MARK}},
                                        "thoughtSignature": "sig-123",
                                    },
                                ]
                            }
                        }
                    ]
                }
            )
        else:
            payload = _sse({"candidates": [{"content": {"parts": [{"text": f"Found it [TX-{seeded_tx}]."}]}}]})
        return httpx.Response(200, content=payload)

    _install_transport(monkeypatch, handler)
    events = _collect(**_stream_kwargs(_ctx()))
    kinds = [e["type"] for e in events]
    assert "thinking" in kinds and "tool_call" in kinds and kinds[-1] == "done"

    assert requests[0]["generationConfig"]["thinkingConfig"] == {"includeThoughts": True}
    assert requests[0]["tools"][0]["functionDeclarations"]
    model_turn = next(c for c in requests[1]["contents"] if c["role"] == "model")
    assert any(p.get("thoughtSignature") == "sig-123" for p in model_turn["parts"])
    assert not any(p.get("thought") for p in model_turn["parts"])
    fn_resp = requests[1]["contents"][-1]["parts"][0]["functionResponse"]
    assert fn_resp["name"] == "search_transcripts"
    assert f"[TX-{seeded_tx} " in fn_resp["response"]["result"]


def test_assistant_trace_collects_turn():
    trace = AssistantTrace()
    for event in [
        {"type": "thinking", "content": "a "},
        {"type": "thinking", "content": "b"},
        {"type": "tool_call", "call_id": "c1", "tool": "search_transcripts", "arguments": {"query": "x"}},
        {"type": "tool_result", "call_id": "c1", "status": "ok", "summary": "2 match(es)", "count": 2, "duration_ms": 5},
        {"type": "token", "content": "Answer "},
        {"type": "token", "content": "[TX-1]"},
        {"type": "done", "cited_log_ids": [1]},
    ]:
        trace.consume(event)
    assert trace.thought == "a b"
    assert trace.text == "Answer [TX-1]"
    assert trace.cited_ids == [1]
    assert trace.tool_calls == [
        {
            "call_id": "c1",
            "tool": "search_transcripts",
            "arguments": {"query": "x"},
            "status": "ok",
            "summary": "2 match(es)",
            "count": 2,
            "duration_ms": 5,
        }
    ]
