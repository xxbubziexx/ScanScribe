"""Shared persistent async HTTP client with connection pooling."""
from __future__ import annotations
import httpx
from typing import Optional

_client: Optional[httpx.AsyncClient] = None


def get_async_client() -> httpx.AsyncClient:
    """Return shared AsyncClient singleton with keep-alive connection pooling."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        )
    return _client


async def close_async_client() -> None:
    """Close the shared AsyncClient singleton during shutdown."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None
