"""Asynchronous streaming client for Scanner Intelligence LLM queries."""
import json
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional
import httpx

from ..config import get_settings, chat_api_key, chat_base_url
from .chat_context import extract_cited_ids

logger = logging.getLogger(__name__)


async def stream_chat_completion(
    system_prompt: str,
    context_text: str,
    conversation_history: List[Dict[str, str]],
    user_prompt: str,
    meta_info: Dict[str, Any],
) -> AsyncGenerator[str, None]:
    """Stream response tokens from configured LLM provider using Server-Sent Events format."""
    settings = get_settings()
    cfg = settings.config.chat

    if not cfg.enabled:
        yield f"data: {json.dumps({'type': 'error', 'error': 'Scanner Intelligence chat is disabled in configuration.'})}\n\n"
        return

    api_key = chat_api_key(cfg)
    if not api_key:
        yield f"data: {json.dumps({'type': 'error', 'error': 'API key for chat provider is missing. Set OPENROUTER_API_KEY or GEMINI_API_KEY.'})}\n\n"
        return

    # Emit initial metadata event
    yield f"data: {json.dumps({'type': 'meta', **meta_info})}\n\n"

    full_response_text = ""

    try:
        if cfg.provider == "gemini":
            async for token in _stream_gemini(
                api_key=api_key,
                model=cfg.model,
                system_prompt=system_prompt,
                context_text=context_text,
                history=conversation_history,
                user_prompt=user_prompt,
                max_tokens=cfg.max_output_tokens,
                temperature=cfg.temperature,
            ):
                full_response_text += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        else:
            # Default: openrouter
            base_url = chat_base_url(cfg)
            async for token in _stream_openrouter(
                api_key=api_key,
                base_url=base_url,
                model=cfg.model,
                system_prompt=system_prompt,
                context_text=context_text,
                history=conversation_history,
                user_prompt=user_prompt,
                max_tokens=cfg.max_output_tokens,
                temperature=cfg.temperature,
            ):
                full_response_text += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

        # Parse citations
        cited_ids = extract_cited_ids(full_response_text)
        yield f"data: {json.dumps({'type': 'done', 'content': full_response_text, 'cited_log_ids': cited_ids})}\n\n"

    except httpx.HTTPStatusError as e:
        logger.error(f"Chat LLM HTTP status error: {e.response.status_code} - {e.response.text[:500]}")
        yield f"data: {json.dumps({'type': 'error', 'error': f'LLM API request failed: HTTP {e.response.status_code}'})}\n\n"
    except httpx.RequestError as e:
        logger.error(f"Chat LLM connection error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'error': f'Network error connecting to LLM provider: {str(e)}'})}\n\n"
    except Exception as e:
        logger.error(f"Unexpected chat streaming error: {e}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'error': f'Internal streaming error: {str(e)}'})}\n\n"


async def _stream_openrouter(
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    context_text: str,
    history: List[Dict[str, str]],
    user_prompt: str,
    max_tokens: int,
    temperature: float,
) -> AsyncGenerator[str, None]:
    """Stream from OpenRouter completions endpoint."""
    url = f"{base_url.rstrip('/')}/v1/chat/completions"

    messages: List[Dict[str, str]] = [
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

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/xxbubziexx/scanscribe",
        "X-Title": "ScanScribe Scanner Intelligence",
    }

    body = {
        "model": model,
        "messages": messages,
        "stream": True,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    timeout = httpx.Timeout(connect=15.0, read=90.0, write=15.0, pool=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, headers=headers, json=body) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        choices = chunk.get("choices") or []
                        if choices:
                            delta = choices[0].get("delta") or {}
                            content = delta.get("content") or ""
                            if content:
                                yield content
                    except json.JSONDecodeError:
                        continue


async def _stream_gemini(
    api_key: str,
    model: str,
    system_prompt: str,
    context_text: str,
    history: List[Dict[str, str]],
    user_prompt: str,
    max_tokens: int,
    temperature: float,
) -> AsyncGenerator[str, None]:
    """Stream from Google Gemini REST streaming endpoint."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:streamGenerateContent?alt=sse&key={api_key}"
    )

    contents: List[Dict[str, Any]] = []

    # Gemini system instruction
    sys_instruction = {
        "parts": [{"text": f"{system_prompt}\n\n=== RECENT RADIO LOG DATA ===\n{context_text}"}]
    }

    for msg in history:
        role = "user" if msg.get("role") == "user" else "model"
        content = msg.get("content", "")
        if content:
            contents.append({"role": role, "parts": [{"text": content}]})

    contents.append({"role": "user", "parts": [{"text": user_prompt}]})

    body = {
        "contents": contents,
        "systemInstruction": sys_instruction,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
    }

    headers = {"Content-Type": "application/json"}
    timeout = httpx.Timeout(connect=15.0, read=90.0, write=15.0, pool=15.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, headers=headers, json=body) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    try:
                        chunk = json.loads(data_str)
                        candidates = chunk.get("candidates") or []
                        if candidates:
                            content = candidates[0].get("content") or {}
                            parts = content.get("parts") or []
                            if parts:
                                text = parts[0].get("text") or ""
                                if text:
                                    yield text
                    except json.JSONDecodeError:
                        continue
