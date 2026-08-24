"""Summarization providers (Gemini / OpenRouter) for Insights hour summaries."""

import json
import logging
import urllib.request
import urllib.error
from typing import List, Dict, Any

from ..config import get_settings, hourly_summaries_api_key, hourly_summaries_base_url

logger = logging.getLogger(__name__)


def _gemini_generate_text(prompt: str) -> str:
    """Call Google Gemini API (REST) and return generated text."""
    settings = get_settings()
    cfg = settings.config.hourly_summaries

    if not cfg.enabled:
        raise RuntimeError("Hourly Summaries API is disabled (hourly_summaries.enabled=false)")
    api_key = hourly_summaries_api_key(cfg)
    if not api_key:
        raise RuntimeError(
            "Gemini API key is missing (set GEMINI_API_KEY env var or hourly_summaries.api_key in config.yml)"
        )
    if not cfg.model:
        raise RuntimeError("Hourly Summaries model is missing (hourly_summaries.model)")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{cfg.model}:generateContent?key={api_key}"
    )

    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                ]
            }
        ],
        "generationConfig": {
            "maxOutputTokens": getattr(cfg, "max_output_tokens", 8192) or 8192,
        }
    }

    req = urllib.request.Request(
        url=url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = ""

        safe_url = f"https://generativelanguage.googleapis.com/v1beta/models/{cfg.model}:generateContent"
        msg = f"Gemini request failed: HTTP {e.code} {e.reason} for {safe_url}"
        if err_body:
            msg += f" | response: {err_body[:800]}"

        if e.code == 404:
            msg += (
                " | hint: try setting hourly_summaries.model to a concrete variant like "
                "'gemini-1.5-flash-001' (or list available models via "
                "GET https://generativelanguage.googleapis.com/v1beta/models)."
            )

        raise RuntimeError(msg) from e
    except Exception as e:
        raise RuntimeError(f"Gemini request failed: {e}") from e

    try:
        data = json.loads(raw)
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError(f"No candidates returned: {raw[:500]}")
        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []
        if not parts:
            raise RuntimeError(f"No content parts returned: {raw[:500]}")
        text = parts[0].get("text")
        if not text:
            raise RuntimeError(f"No text returned: {raw[:500]}")
        return text.strip()
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Gemini response parse failed: {e}") from e


def _openrouter_generate_text(prompt: str) -> str:
    """Call OpenRouter chat completions API and return generated text."""
    settings = get_settings()
    cfg = settings.config.hourly_summaries

    if not cfg.enabled:
        raise RuntimeError("Hourly Summaries API is disabled (hourly_summaries.enabled=false)")
    api_key = hourly_summaries_api_key(cfg)
    if not api_key:
        raise RuntimeError(
            "OpenRouter API key is missing (set OPENROUTER_API_KEY env var or hourly_summaries.api_key in config.yml)"
        )
    if not cfg.model:
        raise RuntimeError("Hourly Summaries model is missing (hourly_summaries.model)")

    base = hourly_summaries_base_url(cfg)
    url = f"{base}/v1/chat/completions"
    body = {
        "model": cfg.model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": getattr(cfg, "max_output_tokens", 8192) or 8192,
        "temperature": 0.2,
        "stream": False,
    }

    req = urllib.request.Request(
        url=url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://scanscribe.local",
            "X-Title": "ScanScribe",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = ""
        msg = f"OpenRouter request failed: HTTP {e.code} {e.reason} for {url}"
        if err_body:
            msg += f" | response: {err_body[:800]}"
        raise RuntimeError(msg) from e
    except Exception as e:
        raise RuntimeError(f"OpenRouter request failed: {e}") from e

    try:
        data = json.loads(raw)
        if data.get("error"):
            raise RuntimeError(f"OpenRouter error: {data['error']}")
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"No choices returned: {raw[:500]}")
        message = choices[0].get("message") or {}
        text = message.get("content")
        if not text:
            raise RuntimeError(f"No content returned: {raw[:500]}")
        return text.strip()
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"OpenRouter response parse failed: {e}") from e


def build_hour_prompt(entries: List[Dict[str, Any]], date_str: str, hour: int) -> str:
    """Build prompt from filename_id, talkgroup, time, transcript."""
    header = (
        "You are summarizing public-safety radio transcripts.\n"
        "Write your summary in Markdown: use **bold** for emphasis, - bullet lists, ## headings. "
        "Keep it concise. Do NOT invent facts.\n\n"
        f"Date: {date_str}\n"
        f"Hour: {hour:02d}:00\n\n"
        "Entries (filename_id | talkgroup | time | transcript):\n"
    )

    lines: List[str] = []
    for e in entries:
        filename_id = e.get("filename_id") or e.get("title") or ""
        talkgroup = e.get("talkgroup") or "N/A"
        t = e.get("time") or ""
        transcript = (e.get("transcript") or "").strip()
        if not transcript:
            continue
        lines.append(f"- {filename_id} | {talkgroup} | {t} | {transcript}")

    if not lines:
        return header + "\n(No usable transcript text for this hour.)\n"

    return header + "\n".join(lines) + "\n"


def generate_hour_summary(entries: List[Dict[str, Any]], date_str: str, hour: int) -> Dict[str, Any]:
    """Generate an hour summary using configured provider. Returns {\"summary\": str}."""
    prompt = build_hour_prompt(entries, date_str=date_str, hour=hour)
    settings = get_settings()
    cfg = settings.config.hourly_summaries
    provider = (cfg.provider or "gemini").strip().lower()

    if provider == "openrouter":
        raw = _openrouter_generate_text(prompt)
    elif provider == "gemini":
        raw = _gemini_generate_text(prompt)
    else:
        raise RuntimeError(
            f"Unknown hourly_summaries.provider={provider!r} (valid: gemini, openrouter)"
        )

    return {"summary": raw.strip()}
