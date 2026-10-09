"""Unit tests for Phase 3: Concurrency, TaskManager, and Async HTTP Client."""
import asyncio
import pytest
from app.services.task_manager import BackgroundTaskManager
from app.services.http_client import get_async_client, close_async_client


@pytest.mark.asyncio
async def test_task_manager_spawn_and_drain():
    """Verify BackgroundTaskManager tracks tasks, prevents GC collection, and drains cleanly."""
    tm = BackgroundTaskManager()
    completed = []

    async def sample_work(item_id: int):
        await asyncio.sleep(0.01)
        completed.append(item_id)

    # Spawn 5 tasks
    for i in range(5):
        tm.spawn(sample_work(i), name=f"sample-{i}")

    assert len(tm._tasks) == 5

    # Drain with timeout
    await tm.drain(timeout_seconds=2.0)

    assert len(completed) == 5
    assert len(tm._tasks) == 0


@pytest.mark.asyncio
async def test_async_http_client_singleton_and_close():
    """Verify shared async HTTP client lifecycle."""
    client1 = get_async_client()
    client2 = get_async_client()
    assert client1 is client2
    assert not client1.is_closed

    await close_async_client()
    assert client1.is_closed
