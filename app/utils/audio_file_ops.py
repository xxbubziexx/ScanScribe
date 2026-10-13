"""Defensive file system operations for audio processing pipelines."""
import asyncio
import logging
import time
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)


def safe_unlink(path: Union[str, Path], retries: int = 3, delay: float = 0.1) -> bool:
    """Safely unlink a file with retry backoff against transient OS locks (e.g. Windows indexer, AV).
    
    Returns True if the file was deleted or did not exist, False if deletion failed after all retries.
    """
    p = Path(path)
    if not p.exists():
        return True

    for attempt in range(1, retries + 1):
        try:
            p.unlink(missing_ok=True)
            return True
        except (PermissionError, OSError) as e:
            if attempt == retries:
                logger.warning(
                    f"⚠️ safe_unlink failed for {p} after {retries} attempts: {e}"
                )
                return False
            time.sleep(delay * (2 ** (attempt - 1)))
        except Exception as e:
            logger.warning(f"⚠️ Unexpected error deleting {p}: {e}")
            return False
    return False


async def safe_async_unlink(path: Union[str, Path], retries: int = 3, delay: float = 0.1) -> bool:
    """Async variant of safe_unlink that yields control to the event loop during retry delays."""
    p = Path(path)
    if not p.exists():
        return True

    for attempt in range(1, retries + 1):
        try:
            p.unlink(missing_ok=True)
            return True
        except (PermissionError, OSError) as e:
            if attempt == retries:
                logger.warning(
                    f"⚠️ safe_async_unlink failed for {p} after {retries} attempts: {e}"
                )
                return False
            await asyncio.sleep(delay * (2 ** (attempt - 1)))
        except Exception as e:
            logger.warning(f"⚠️ Unexpected error deleting {p}: {e}")
            return False
    return False
