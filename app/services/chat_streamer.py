"""Asynchronous streaming client for Scanner Intelligence LLM queries.

Supports a bounded agentic tool-calling loop (OpenRouter / OpenAI-style and Gemini native),
reasoning ("thinking") streams, and plain single-turn streaming when no tool context is given.
All network I/O uses ``httpx.AsyncClient``; tool bodies run off-loop via ``agent_tools.execute_tool``.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx

from ..config import get_settings, chat_api_key, chat_base_url
from .agent_tools import (
    ToolContext,
    ToolResult,
    execute_tool,
    gemini_tool_declarations,
    openai_tool_declarations,
)
from .chat_context import extract_cited_ids

logger = logging.getLogger(__name__)

StreamEvent = Dict[str, Any]
_TIMEOUT = httpx.Timeout(connect=15.0, read=90.0, write=15.0, pool=15.0)

_ITERATION_LIMIT_NOTICE = (
    "Tool call limit reached. Do not call any more tools. Write the final answer now using only the "
    "transmissions already retrieved, state clearly what could not be confirmed, and keep ASR uncertainty in mind."
)


class ChatStreamError(Exception):
    """Provider reported an error inside an otherwise successful stream."""


@dataclass
class _ToolCall:
    """One model-requested tool invocation, normalized across providers."""

    call_id: str
    name: str
    args: Dict[str, Any]
    parse_error: Optional[str] = None
    raw_part: Optional[Dict[str, Any]] = None  # Gemini functionCall part (carries thoughtSignature)


@dataclass
class AssistantTrace:
    """Accumulates one assistant turn from SSE events so the route can persist it losslessly."""

    text: str = ""
    thought: str = ""
    cited_ids: List[int] = field(default_factory=list)
    _calls: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def consume(self, payload: StreamEvent) -> None:
        kind = payload.get("type")
        if kind == "token":
            self.text += payload.get("content", "")
        elif kind == "thinking":
            self.thought += payload.get("content", "")
        elif kind == "tool_call":
            self._calls[payload["call_id"]] = {
                "call_id": payload["call_id"],
                "tool": payload.get("tool", ""),
                "arguments": payload.get("arguments") or {},
                "status": "running",
                "summary": None,
                "count": None,
                "duration_ms": None,
            }
        elif kind == "tool_result":
            record = self._calls.get(payload.get("call_id", ""))
            if record is not None:
                record["status"] = payload.get("status", "ok")
                record["summary"] = payload.get("summary")
                record["count"] = payload.get("count")
                record["duration_ms"] = payload.get("duration_ms")
        elif kind == "done":
            self.cited_ids = payload.get("cited_log_ids") or []

    @property
    def tool_calls(self) -> List[Dict[str, Any]]:
        return list(self._calls.values())


def _sse(payload: StreamEvent) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def stream_chat_completion(
    system_prompt: str,
    context_text: str,
    conversation_history: List[Dict[str, str]],
    user_prompt: str,
    meta_info: Dict[str, Any],
    tool_ctx: Optional[ToolContext] = None,
) -> AsyncGenerator[str, None]:
    """Stream response events from the configured LLM provider using Server-Sent Events format.

    When ``tool_ctx`` is provided the model is offered the agent tool registry and a bounded
    tool-calling loop runs; otherwise a single plain completion is streamed.
    """
    settings = get_settings()
    cfg = settings.config.chat

    if not cfg.enabled:
        yield _sse({"type": "error", "error": "Scanner Intelligence chat is disabled in configuration."})
        return

    api_key = chat_api_key(cfg)
    if not api_key:
        yield _sse({"type": "error", "error": "API key for chat provider is missing. Set OPENROUTER_API_KEY or GEMINI_API_KEY."})
        return

    yield _sse({"type": "meta", **meta_info})

    full_response_text = ""
    tools_used = False
    max_iters = max(0, int(cfg.max_tool_iterations)) if tool_ctx is not None else 0

    try:
        if cfg.provider == "gemini":
            events = _agent_loop_gemini(
                api_key=api_key,
                model=cfg.model,
                system_prompt=system_prompt,
                context_text=context_text,
                history=conversation_history,
                user_prompt=user_prompt,
                max_tokens=cfg.max_output_tokens,
                temperature=cfg.temperature,
                reasoning=cfg.reasoning_enabled,
                reasoning_effort=cfg.reasoning_effort,
                tool_ctx=tool_ctx,
                max_iters=max_iters,
            )
        else:
            events = _agent_loop_openrouter(
                api_key=api_key,
                base_url=chat_base_url(cfg),
                model=cfg.model,
                system_prompt=system_prompt,
                context_text=context_text,
                history=conversation_history,
                user_prompt=user_prompt,
                max_tokens=cfg.max_output_tokens,
                temperature=cfg.temperature,
                reasoning=cfg.reasoning_enabled,
                reasoning_effort=cfg.reasoning_effort,
                tool_ctx=tool_ctx,
                max_iters=max_iters,
            )

        async for event in events:
            kind = event.get("type")
            if kind == "token":
                full_response_text += event.get("content", "")
            elif kind == "tool_call":
                tools_used = True
            yield _sse(event)

        if tools_used and not full_response_text.strip():
            yield _sse({"type": "error", "error": "The model finished tool use without producing an answer. Try rephrasing or retry."})
            return

        cited_ids = extract_cited_ids(full_response_text)
        yield _sse({"type": "done", "content": full_response_text, "cited_log_ids": cited_ids})

    except httpx.HTTPStatusError as e:
        logger.error(f"Chat LLM HTTP status error: {e.response.status_code} - {_safe_response_text(e.response)}")
        yield _sse({"type": "error", "error": f"LLM API request failed: HTTP {e.response.status_code}"})
    except httpx.RequestError as e:
        logger.error(f"Chat LLM connection error: {type(e).__name__}")
        yield _sse({"type": "error", "error": f"Network error connecting to LLM provider: {type(e).__name__}"})
    except ChatStreamError as e:
        logger.error(f"Chat LLM stream error: {e}")
        yield _sse({"type": "error", "error": f"LLM provider error: {e}"})
    except Exception as e:
        logger.error(f"Unexpected chat streaming error: {e}", exc_info=True)
        yield _sse({"type": "error", "error": f"Internal streaming error: {str(e)}"})


def _safe_response_text(response: httpx.Response) -> str:
    try:
        return response.text[:500]
    except httpx.ResponseNotRead:
        return "<body not read>"


async def _dispatch_calls(
    calls: List[_ToolCall],
    tool_ctx: ToolContext,
    results_out: List[ToolResult],
) -> AsyncGenerator[StreamEvent, None]:
    """Run requested tools sequentially (keeps SQLite load low), emitting tool_call/tool_result events."""
    for call in calls:
        yield {"type": "tool_call", "call_id": call.call_id, "tool": call.name, "arguments": call.args}
        if call.parse_error:
            result = ToolResult(content=call.parse_error, summary="Invalid arguments", is_error=True)
            elapsed_ms = 0
        else:
            result, elapsed_ms = await execute_tool(call.name, call.args, tool_ctx)
        results_out.append(result)
        yield {
            "type": "tool_result",
            "call_id": call.call_id,
            "tool": call.name,
            "status": "error" if result.is_error else "ok",
            "summary": result.summary,
            "count": result.count,
            "duration_ms": elapsed_ms,
        }


# --------------------------------------------------------------------------- #
# OpenRouter / OpenAI-compatible
# --------------------------------------------------------------------------- #


async def _agent_loop_openrouter(
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    context_text: str,
    history: List[Dict[str, str]],
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    reasoning: bool,
    reasoning_effort: str,
    tool_ctx: Optional[ToolContext],
    max_iters: int,
) -> AsyncGenerator[StreamEvent, None]:
    """OpenRouter completion loop: stream a turn, run requested tools, feed results back, repeat."""
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/xxbubziexx/scanscribe",
        "X-Title": "ScanScribe Scanner Intelligence",
    }

    messages: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": f"{system_prompt}\n\n=== RECENT RADIO LOG DATA ===\n{context_text}",
        }
    ]
    for msg in history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_prompt})

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for iteration in range(max_iters + 1):
            offer_tools = tool_ctx is not None and iteration < max_iters
            if tool_ctx is not None and not offer_tools:
                messages.append({"role": "user", "content": _ITERATION_LIMIT_NOTICE})

            body: Dict[str, Any] = {
                "model": model,
                "messages": messages,
                "stream": True,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if offer_tools:
                body["tools"] = openai_tool_declarations()
                body["tool_choice"] = "auto"
            if reasoning:
                body["reasoning"] = {"effort": reasoning_effort}

            turn_text = ""
            calls: List[_ToolCall] = []
            reasoning_details: List[Any] = []
            async for kind, value in _openrouter_turn(client, url, headers, body):
                if kind == "text":
                    turn_text += value
                    yield {"type": "token", "content": value}
                elif kind == "thinking":
                    yield {"type": "thinking", "content": value}
                elif kind == "reasoning_details":
                    reasoning_details.extend(value)
                elif kind == "tool_calls":
                    calls = value

            if not calls or tool_ctx is None:
                return

            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": turn_text or None,
                "tool_calls": [
                    {
                        "id": c.call_id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": json.dumps(c.args)},
                    }
                    for c in calls
                ],
            }
            if reasoning_details:
                assistant_msg["reasoning_details"] = reasoning_details
            messages.append(assistant_msg)

            results: List[ToolResult] = []
            async for event in _dispatch_calls(calls, tool_ctx, results):
                yield event
            for call, result in zip(calls, results):
                messages.append({"role": "tool", "tool_call_id": call.call_id, "content": result.content})


async def _openrouter_turn(
    client: httpx.AsyncClient,
    url: str,
    headers: Dict[str, str],
    body: Dict[str, Any],
) -> AsyncGenerator[Tuple[str, Any], None]:
    """Stream one OpenRouter turn, yielding ('text'|'thinking'|'reasoning_details'|'tool_calls', value)."""
    acc: Dict[int, Dict[str, Any]] = {}
    async with client.stream("POST", url, headers=headers, json=body) as response:
        if response.status_code >= 400:
            await response.aread()
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            if chunk.get("error"):
                err = chunk["error"]
                raise ChatStreamError(err.get("message", "unknown error") if isinstance(err, dict) else str(err))
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}

            thinking = delta.get("reasoning") or delta.get("reasoning_content") or ""
            if thinking:
                yield "thinking", thinking
            details = delta.get("reasoning_details")
            if details:
                yield "reasoning_details", details
            content = delta.get("content") or ""
            if content:
                yield "text", content

            for tc in delta.get("tool_calls") or []:
                slot = acc.setdefault(tc.get("index", 0), {"id": None, "name": "", "args": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["name"] += fn["name"]
                if fn.get("arguments"):
                    slot["args"] += fn["arguments"]

    if acc:
        calls: List[_ToolCall] = []
        for idx in sorted(acc):
            slot = acc[idx]
            args: Dict[str, Any] = {}
            parse_error: Optional[str] = None
            try:
                parsed = json.loads(slot["args"] or "{}")
                if isinstance(parsed, dict):
                    args = parsed
                else:
                    parse_error = "Tool arguments must be a JSON object."
            except json.JSONDecodeError:
                parse_error = "Tool arguments were not valid JSON."
            calls.append(
                _ToolCall(
                    call_id=slot["id"] or f"call_{idx}",
                    name=slot["name"],
                    args=args,
                    parse_error=parse_error,
                )
            )
        yield "tool_calls", calls


# --------------------------------------------------------------------------- #
# Gemini native
# --------------------------------------------------------------------------- #


def _gemini_supports_thinking(model: str) -> bool:
    return "gemini-2.5" in model or "gemini-3" in model


async def _agent_loop_gemini(
    api_key: str,
    model: str,
    system_prompt: str,
    context_text: str,
    history: List[Dict[str, str]],
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    reasoning: bool,
    reasoning_effort: str,
    tool_ctx: Optional[ToolContext],
    max_iters: int,
) -> AsyncGenerator[StreamEvent, None]:
    """Gemini completion loop with native function calling and thought summaries."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:streamGenerateContent?alt=sse"
    )
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}

    sys_instruction = {
        "parts": [{"text": f"{system_prompt}\n\n=== RECENT RADIO LOG DATA ===\n{context_text}"}]
    }

    contents: List[Dict[str, Any]] = []
    for msg in history:
        role = "user" if msg.get("role") == "user" else "model"
        content = msg.get("content", "")
        if content:
            contents.append({"role": role, "parts": [{"text": content}]})
    contents.append({"role": "user", "parts": [{"text": user_prompt}]})

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for iteration in range(max_iters + 1):
            offer_tools = tool_ctx is not None and iteration < max_iters
            if tool_ctx is not None and not offer_tools:
                contents.append({"role": "user", "parts": [{"text": _ITERATION_LIMIT_NOTICE}]})

            generation_config: Dict[str, Any] = {"maxOutputTokens": max_tokens, "temperature": temperature}
            if reasoning and _gemini_supports_thinking(model):
                generation_config["thinkingConfig"] = {"includeThoughts": True}

            body: Dict[str, Any] = {
                "contents": contents,
                "systemInstruction": sys_instruction,
                "generationConfig": generation_config,
            }
            if offer_tools:
                body["tools"] = gemini_tool_declarations()

            model_parts: List[Dict[str, Any]] = []
            calls: List[_ToolCall] = []
            async for kind, value in _gemini_turn(client, url, headers, body, iteration):
                if kind == "text":
                    yield {"type": "token", "content": value}
                elif kind == "thinking":
                    yield {"type": "thinking", "content": value}
                elif kind == "parts":
                    model_parts = value
                elif kind == "tool_calls":
                    calls = value

            if not calls or tool_ctx is None:
                return

            contents.append({"role": "model", "parts": model_parts})
            results: List[ToolResult] = []
            async for event in _dispatch_calls(calls, tool_ctx, results):
                yield event
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {"functionResponse": {"name": call.name, "response": {"result": result.content}}}
                        for call, result in zip(calls, results)
                    ],
                }
            )


def _append_text_part(parts: List[Dict[str, Any]], part: Dict[str, Any]) -> None:
    """Keep model history compact: merge adjacent plain text parts, preserve signed parts verbatim."""
    text = part.get("text", "")
    if parts and "text" in parts[-1] and "thoughtSignature" not in parts[-1] and "thoughtSignature" not in part:
        parts[-1]["text"] += text
    else:
        parts.append(dict(part))


async def _gemini_turn(
    client: httpx.AsyncClient,
    url: str,
    headers: Dict[str, str],
    body: Dict[str, Any],
    iteration: int,
) -> AsyncGenerator[Tuple[str, Any], None]:
    """Stream one Gemini turn, yielding ('text'|'thinking'|'parts'|'tool_calls', value)."""
    model_parts: List[Dict[str, Any]] = []
    calls: List[_ToolCall] = []
    async with client.stream("POST", url, headers=headers, json=body) as response:
        if response.status_code >= 400:
            await response.aread()
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                chunk = json.loads(line[6:].strip())
            except json.JSONDecodeError:
                continue
            if chunk.get("error"):
                err = chunk["error"]
                raise ChatStreamError(err.get("message", "unknown error") if isinstance(err, dict) else str(err))
            candidates = chunk.get("candidates") or []
            if not candidates:
                continue
            for part in (candidates[0].get("content") or {}).get("parts") or []:
                if part.get("thought") is True:
                    if part.get("text"):
                        yield "thinking", part["text"]
                    continue
                fn_call = part.get("functionCall")
                if fn_call:
                    args = fn_call.get("args")
                    calls.append(
                        _ToolCall(
                            call_id=fn_call.get("id") or f"call_{iteration}_{len(calls)}",
                            name=fn_call.get("name", ""),
                            args=args if isinstance(args, dict) else {},
                            parse_error=None if isinstance(args, (dict, type(None))) else "Tool arguments must be a JSON object.",
                            raw_part=part,
                        )
                    )
                    model_parts.append(dict(part))
                elif "text" in part:
                    if part["text"]:
                        yield "text", part["text"]
                    _append_text_part(model_parts, part)

    yield "parts", model_parts
    if calls:
        yield "tool_calls", calls
