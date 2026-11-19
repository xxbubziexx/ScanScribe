"""Audio storage path contract: sharded writes, layout-agnostic resolution.

Two layouts coexist by design:

    flat      audio_storage/<basename>.wav
    sharded   audio_storage/<YYYY>/<MM>/<DD>/<basename>.wav

``log_entries.audio_path`` stores the storage-relative path, so resolution always
follows the stored value and never an assumption about the layout. That is what lets an
existing install adopt sharded writes without a migration: its old rows keep pointing at
flat files, new rows point into date directories, and both resolve.

The shard date is the row's own ``log_date``, which is derived from the file's capture
timestamp at ingest. Never use the wall clock or mtime here: retention filters on
``log_date``, so any disagreement would let the directory tree drift away from what a
purge believes it is deleting.
"""
from __future__ import annotations

import logging
import os
import re
import urllib.parse
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

#: Prefix stored in ``log_entries.audio_path`` for files kept on disk.
STORAGE_PREFIX = "audio_storage/"

#: Sentinel written when a transmission was transcribed without keeping its audio.
NOT_SAVED = "file not saved"

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def is_saved(stored: Optional[str]) -> bool:
    """True when ``stored`` names a real file rather than the not-saved sentinel."""
    if not stored:
        return False
    value = str(stored).strip()
    return bool(value) and value != NOT_SAVED


def normalize_stored(stored: str) -> str:
    """Return the storage-relative portion of a stored path, POSIX separators.

    Backslashes are folded because the development tree is Windows while every
    deployment is Linux; a stored ``\\`` would break both the URL and path resolution.
    """
    value = str(stored).strip().replace("\\", "/").lstrip("/")
    if value.startswith(STORAGE_PREFIX):
        value = value[len(STORAGE_PREFIX):]
    return value.lstrip("/")


def shard_parts(log_date: Optional[str]) -> Tuple[str, ...]:
    """Split ``YYYY-MM-DD`` into ``(YYYY, MM, DD)``; empty tuple if unusable.

    An unparseable date yields no parts, which makes the caller store the file flat
    rather than invent a directory name from a bad value.
    """
    if not log_date:
        return ()
    match = _DATE_RE.match(str(log_date).strip())
    return match.groups() if match else ()


def shard_target(
    output_dir: Path,
    log_date: Optional[str],
    filename: str,
) -> Tuple[Path, str]:
    """Absolute destination and the value to persist in ``audio_path``.

    Returns ``(output_dir/YYYY/MM/DD/name, "audio_storage/YYYY/MM/DD/name")``, or the
    flat equivalent when ``log_date`` is missing or malformed. The caller is
    responsible for creating the parent directory.
    """
    safe_name = Path(str(filename).replace("\\", "/")).name
    parts = shard_parts(log_date)
    relative = Path(*parts) / safe_name if parts else Path(safe_name)
    return Path(output_dir) / relative, STORAGE_PREFIX + relative.as_posix()


def resolve_audio_file(stored: Optional[str], output_dir: Path) -> Optional[Path]:
    """Map a stored ``audio_path`` to an existing file inside ``output_dir``.

    Tries the exact stored relative path first (sharded or flat), then falls back to
    the basename so a row written before a layout change still finds its file.
    Every candidate is confined to ``output_dir``: the stored value is data, and data
    must not be able to address files outside the audio tree.
    """
    if not is_saved(stored):
        return None

    root = Path(output_dir).resolve()
    raw = str(stored).strip().replace("\\", "/")

    if os.path.isabs(raw):
        candidate = Path(raw).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            logger.warning("audio path escapes the output directory, ignoring: %s", raw)
            return None
        return candidate if candidate.is_file() else None

    relative = normalize_stored(raw)
    if not relative:
        return None

    for candidate_rel in (relative, Path(relative).name):
        candidate = (root / candidate_rel).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None


def audio_url_for(stored: Optional[str]) -> str:
    """Static playback URL for a stored path, or ``""`` when nothing was saved."""
    relative = normalize_stored(stored) if is_saved(stored) else ""
    if not relative:
        return ""
    return "/audio_storage/" + urllib.parse.quote(relative, safe="/")
