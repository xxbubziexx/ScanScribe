# Phase 3: Concurrency, Asyncio & Pipeline Architecture

> **Phase Order**: 3 of 5  
> **Status**: Ready for Implementation  
> **Estimated Execution Time**: ~2–3 hours  
> **Target Files**: `app/services/queue_processor.py`, `app/services/events_router_engine.py`, `app/services/geocoder_service.py`, `app/services/task_manager.py`, `app/main.py`

---

## 1. Objectives

1. Eliminate all bare, unmanaged `threading.Thread(...)` spawns and replace them with a bounded worker pool.
2. Eradicate fire-and-forget `asyncio.create_task(...)` hazards by creating a centralized `BackgroundTaskManager` with strong references and shutdown draining.
3. Convert blocking synchronous HTTP calls in [`app/services/events_router_engine.py`](file:///a:/Scanscribe_Projects/scanscribe/app/services/events_router_engine.py) and [`app/services/geocoder_service.py`](file:///a:/Scanscribe_Projects/scanscribe/app/services/geocoder_service.py) to use a shared, high-throughput `httpx.AsyncClient`.
4. Replace brittle lock dictionaries with clean, structured pipeline queues.

---

## 2. Concurrency Anti-Patterns Identified

| Current Code Location | Anti-Pattern | Operational Risk |
| :--- | :--- | :--- |
| [`app/services/events_worker.py:81`](file:///a:/Scanscribe_Projects/scanscribe/app/services/events_worker.py#L81) | `threading.Thread(target=_worker, name=f"geocode-{event_id}").start()` | Unbounded OS thread creation under high ingest rates; resource exhaustion. |
| [`app/services/queue_processor.py:370`](file:///a:/Scanscribe_Projects/scanscribe/app/services/queue_processor.py#L370) | `asyncio.create_task(_dispatch_events_pipeline(...))` | In Python 3.11+, unreferenced tasks are garbage collected mid-flight; tasks drop on server shutdown. |
| [`app/services/events_router_engine.py:569`](file:///a:/Scanscribe_Projects/scanscribe/app/services/events_router_engine.py#L569) | `httpx.Client(timeout=30).post(...)` inside `asyncio.to_thread` | Consumes OS thread pool workers while waiting on remote LLM API sockets. |
| [`app/services/queue_processor.py:83`](file:///a:/Scanscribe_Projects/scanscribe/app/services/queue_processor.py#L83) | `_monitor_locks: Dict[int, asyncio.Lock]` | Serializes all transcripts for a monitor; a 30s LLM delay stalls all subsequent audio transmissions. |

---

## 3. Centralized `BackgroundTaskManager`

Create a new service module: [`app/services/task_manager.py`](file:///a:/Scanscribe_Projects/scanscribe/app/services/task_manager.py) to manage all background coroutines:

```python
"""Centralized, graceful asyncio background task manager."""
from __future__ import annotations
import asyncio
import logging
from typing import Coroutine, Set

logger = logging.getLogger("scanscribe.tasks")

class BackgroundTaskManager:
    """Tracks active asyncio tasks, prevents GC collection, and provides shutdown draining."""

    def __init__(self):
        self._tasks: Set[asyncio.Task] = set()

    def spawn(self, coro: Coroutine, name: str = "task") -> asyncio.Task:
        """Spawn a background task with strong reference and error logging."""
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)

        def _on_done(t: asyncio.Task):
            self._tasks.discard(t)
            if not t.cancelled():
                exc = t.exception()
                if exc:
                    logger.error("Background task '%s' failed with error: %s", t.get_name(), exc, exc_info=exc)

        task.add_done_callback(_on_done)
        return task

    async def drain(self, timeout_seconds: float = 10.0) -> None:
        """Gracefully wait for all pending tasks to finish during application shutdown."""
        if not self._tasks:
            return

        logger.info("Draining %d active background tasks (timeout: %.1fs)...", len(self._tasks), timeout_seconds)
        done, pending = await asyncio.wait(self._tasks, timeout=timeout_seconds)

        if pending:
            logger.warning("%d background tasks timed out during shutdown. Cancelling...", len(pending))
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

task_manager = BackgroundTaskManager()
```

### Hook into FastAPI Lifespan ([`app/main.py`](file:///a:/Scanscribe_Projects/scanscribe/app/main.py)):
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup...
    yield
    # Shutdown:
    logger.info("Initiating graceful shutdown sequence...")
    await queue_processor.stop()
    await watcher_service.stop()
    await task_manager.drain(timeout_seconds=10.0)
    logger.info("All tasks drained. Shutdown complete.")
```

---

## 4. Asynchronous HTTP Client Unification

### The Problem:
`EventsRouter.route_transcript` creates a new synchronous `httpx.Client()` on every LLM call, performing full TLS handshakes on every request, then blocking worker threads.

### The Solution:
Create a managed HTTP client singleton in [`app/services/http_client.py`](file:///a:/Scanscribe_Projects/scanscribe/app/services/http_client.py):

```python
"""Shared persistent async HTTP client with connection pooling."""
import httpx
from typing import Optional

_client: Optional[httpx.AsyncClient] = None

def get_async_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        )
    return _client

async def close_async_client():
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None
```

### Updating `EventsRouter` ([`app/services/events_router_engine.py`](file:///a:/Scanscribe_Projects/scanscribe/app/services/events_router_engine.py)):
Change `route_transcript` to native `async`:
```python
@classmethod
async def route_transcript_async(
    cls,
    *,
    monitor_name: str,
    talkgroup: str,
    transcript: str,
    entities: Optional[Dict[str, List[str]]] = None,
    open_incidents: Optional[List[Dict[str, Any]]] = None,
    recent_spans: Optional[List[Union[str, Dict[str, Any]]]] = None,
    known_units: Optional[str] = None,
    global_rules: Optional[str] = None,
) -> Dict[str, Any]:
    client = get_async_client()
    # Call client.post(...) directly without blocking event loop or OS thread pools
    response = await client.post(url, headers=headers, json=payload)
    # Parse JSON...
```

---

## 5. Geocoding Worker Pool

Replace `threading.Thread(target=_worker, name=f"geocode-{event_id}").start()` in [`app/services/events_worker.py`](file:///a:/Scanscribe_Projects/scanscribe/app/services/events_worker.py) with an async background task managed by `task_manager`:

```python
async def _async_geocode_worker(event_id: str, location: str, monitor_id: int):
    try:
        from .geocoder_service import resolve_address_async
        res = await resolve_address_async(location, geo_region)
        if res:
            with SessionLocal() as db:
                ev = db.query(Event).filter(Event.event_id == event_id).first()
                if ev:
                    ev.latitude = res.latitude
                    ev.longitude = res.longitude
                    ev.resolved_address = res.resolved_address
                    db.commit()
            await websocket_manager.broadcast({
                "type": "event_geocoded",
                "data": {"event_id": event_id, "latitude": res.latitude, "longitude": res.longitude}
            })
    except Exception as exc:
        logger.warning("Geocoding failed for %s: %s", event_id, exc)

def dispatch_geocoding(event_id: str, location: str, monitor_id: int):
    task_manager.spawn(_async_geocode_worker(event_id, location, monitor_id), name=f"geocode-{event_id}")
```

---

## 6. Logic & Algorithmic Optimizations

### 1. NER CPU Bottleneck (`app/services/ner_service.py`)
Currently, `pipeline("ner", ..., device=-1)` explicitly forces CPU execution, creating a massive token processing bottleneck during ingest spikes.
* **Fix**: Implement dynamic device resolution using `torch.backends.mps.is_available()` and `torch.cuda.is_available()` to offload inference to the GPU.

### 2. Regex Overhead in Geocoder (`app/services/geocoder_service.py`)
`clean_location_string` and `build_fallback_queries` execute dozens of uncompiled `re.search` and `re.sub` patterns per address.
* **Fix**: Extract all static regex patterns (e.g., preambles, cross-streets, highway variants) to module-level `re.compile()` constants.

---

## 7. Verification Criteria

- [ ] Zero instances of `threading.Thread(target=...).start()` remain in `app/`.
- [ ] Zero unreferenced `asyncio.create_task(...)` calls remain; all background work uses `task_manager.spawn(...)`.
- [ ] During server shutdown (`Ctrl+C`), active background tasks finish cleanly without `Task was destroyed but it was still pending` errors.
- [ ] Ingestion throughput test: Transcribing 20 simulated audio files concurrently does not block or produce lock timeouts.
