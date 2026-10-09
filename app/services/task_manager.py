"""Centralized, graceful asyncio background task manager."""
from __future__ import annotations
import asyncio
import logging
from typing import Coroutine, Set, Optional

logger = logging.getLogger("scanscribe.tasks")


class BackgroundTaskManager:
    """Tracks active asyncio tasks, prevents garbage collection, and provides shutdown draining."""

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
        self._tasks.clear()


task_manager = BackgroundTaskManager()
