"""Queue processor for handling transcription jobs."""
import logging
import asyncio
import shutil
import re
import os
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal, LogsSessionLocal, EventsSessionLocal
from ..models.log_entry import LogEntry
from ..utils.audio_metadata import extract_audio_metadata, get_talkgroup_from_metadata
from ..utils.audio_file_ops import safe_async_unlink
from .transcription_engine import get_engine
from .websocket import websocket_manager
from .watcher import get_watcher_service
from .events_worker import get_matching_monitor_ids, process_transcript_for_monitor
from .redaction_service import redact_ssn

logger = logging.getLogger(__name__)


# A queued file must be untouched for this long before it is treated as
# complete. Writers refresh mtime on every flush, so a file that is still being
# written is never eligible. This single guard covers every producer: HTTP
# uploads, the local watchdog and the startup sweep alike.
MIN_QUEUE_AGE_SECONDS = 3.0

# How many times a file that failed processing is re-queued before it is
# purged. Failures are frequently a partial read rather than a bad recording,
# so the file gets another chance once it has settled. The counter is
# in-memory: a restart resets it, which is bounded by MIN_QUEUE_AGE_SECONDS
# rather than becoming a hot retry loop.
MAX_PROCESS_ATTEMPTS = 3


def parse_timestamp_from_filename(filename: str) -> Optional[datetime]:
    """
    Parse timestamp from filename.
    
    Supports:
    1. YYYYMMDD_HHMMSS (e.g., 20260125_123543)
    2. HH-MM-SS AM/PM MM-DD-YY (e.g., 11-37-12 PM 02-21-26)
    3. HH-MM-SS AM/PM (e.g., 12-36-13 PM) — uses current date
    """
    # Format 1: YYYYMMDD_HHMMSS
    pattern1 = r'(\d{8}_\d{6})'
    match1 = re.search(pattern1, filename)
    if match1:
        try:
            return datetime.strptime(match1.group(1), '%Y%m%d_%H%M%S')
        except ValueError:
            pass

    # Format 2: HH-MM-SS AM/PM MM-DD-YY (e.g., 11-37-12 PM 02-21-26)
    pattern2 = r'(\d{1,2})-(\d{2})-(\d{2})\s*(AM|PM)\s*(\d{2})-(\d{2})-(\d{2})'
    match2 = re.search(pattern2, filename, re.IGNORECASE)
    if match2:
        try:
            hour = int(match2.group(1))
            minute = int(match2.group(2))
            second = int(match2.group(3))
            ampm = match2.group(4).upper()
            mm, dd, yy = int(match2.group(5)), int(match2.group(6)), int(match2.group(7))
            if ampm == 'PM' and hour != 12:
                hour += 12
            elif ampm == 'AM' and hour == 12:
                hour = 0
            year = 2000 + yy
            return datetime(year, mm, dd, hour, minute, second)
        except (ValueError, IndexError):
            pass

    # Format 3: HH-MM-SS AM/PM only — use current date
    pattern3 = r'(\d{1,2})-(\d{2})-(\d{2})\s*(AM|PM)'
    match3 = re.search(pattern3, filename, re.IGNORECASE)
    if match3:
        try:
            hour = int(match3.group(1))
            minute = int(match3.group(2))
            second = int(match3.group(3))
            ampm = match3.group(4).upper()
            if ampm == 'PM' and hour != 12:
                hour += 12
            elif ampm == 'AM' and hour == 12:
                hour = 0
            today = datetime.now().date()
            return datetime.combine(today, datetime.min.time().replace(hour=hour, minute=minute, second=second))
        except (ValueError, IndexError):
            pass

    return None


_monitor_locks: Dict[int, asyncio.Lock] = {}


def _get_monitor_lock(monitor_id: int) -> asyncio.Lock:
    """Return an asyncio.Lock dedicated to the specified monitor to serialize background event routing."""
    if monitor_id not in _monitor_locks:
        _monitor_locks[monitor_id] = asyncio.Lock()
    return _monitor_locks[monitor_id]


async def _dispatch_events_pipeline(
    talkgroup: str,
    transcript_text: str,
    log_entry_id: int,
    timestamp: datetime,
) -> None:
    """Run events pipeline routing asynchronously in background so audio ingestion loop is never blocked."""
    try:
        events_db = EventsSessionLocal()
        try:
            monitor_ids = get_matching_monitor_ids(events_db, talkgroup)
        finally:
            events_db.close()
        for mid in monitor_ids:
            lock = _get_monitor_lock(mid)
            async with lock:
                await asyncio.to_thread(
                    process_transcript_for_monitor,
                    mid,
                    talkgroup,
                    transcript_text,
                    log_entry_id,
                    timestamp,
                )
    except Exception as e:
        logger.warning("Events pipeline background task failed: %s", e)


class QueueProcessor:
    """Processes audio files from the queue directory."""
    
    def __init__(self):
        """Initialize queue processor."""
        self.settings = get_settings()
        self.config = self.settings.config
        self.queue_dir = self.settings.ingest_dir / "queue"
        self.audio_storage = Path(self.settings.output_dir)
        self.running = False
        self.paused = False
        self.engine = get_engine()
        self.websocket_manager = websocket_manager

        # Completeness bookkeeping for the queue (see _get_next_file)
        self._seen_sizes: Dict[str, int] = {}
        # Bounded retry bookkeeping for failed files (see _handle_failed_file)
        self._attempts: Dict[str, int] = {}
        
        # Ensure directories exist
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.audio_storage.mkdir(parents=True, exist_ok=True)
    
    async def start(self):
        """Start the queue processor."""
        if self.running:
            logger.warning("Queue processor already running")
            return
        
        self.running = True
        logger.info("🚀 Queue processor starting...")
        
        # Load model on startup
        if not self.engine.model:
            logger.info("📦 Loading Whisper model...")
            success = await asyncio.to_thread(self.engine.load_model)
            if not success:
                logger.error("❌ Failed to load model, queue processor cannot start")
                self.running = False
                return
        
        # Start processing loop
        from .task_manager import task_manager
        self._process_task = task_manager.spawn(self._process_loop(), name="queue-processor-loop")
    
    async def stop(self):
        """Stop the queue processor."""
        if not self.running:
            return
        
        self.running = False
        logger.info("🛑 Queue processor stopped")
    
    async def pause(self):
        """Pause the queue processor."""
        self.paused = True
        logger.info("⏸️ Queue processor paused")
    
    async def resume(self):
        """Resume the queue processor."""
        self.paused = False
        logger.info("▶️ Queue processor resumed")
    
    def get_queue_count(self) -> int:
        """Get number of files in queue."""
        if not self.queue_dir.exists():
            return 0
        
        extensions = self.config.watchdog_client.extensions
        count = sum(1 for f in self.queue_dir.iterdir() 
                   if f.is_file() and f.suffix.lower() in extensions)
        return count
    
    async def _process_loop(self):
        """Main processing loop."""
        logger.info("🔄 Queue processing loop started")
        
        while self.running:
            try:
                if self.paused:
                    await asyncio.sleep(1)
                    continue
                
                # Get next file from queue
                audio_file = self._get_next_file()
                
                if audio_file:
                    await self._process_file(audio_file)
                else:
                    # No files, wait before checking again
                    await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"❌ Error in processing loop: {e}")
                await asyncio.sleep(5)
    
    def _get_next_file(self) -> Optional[Path]:
        """
        Get the next *complete* file from the queue (FIFO order).

        Files that are still being written are skipped. A file is only eligible
        once its mtime is older than MIN_QUEUE_AGE_SECONDS and it has not grown
        since the previous poll. Reading a partial file is what produces
        mutagen's "can't sync to MPEG frame" and truncated transcripts, and this
        is the single funnel every producer passes through - HTTP uploads, the
        local watchdog and the startup sweep.
        """
        if not self.queue_dir.exists():
            return None

        extensions = self.config.watchdog_client.extensions
        now = time.time()
        eligible = []
        present = set()

        for file_path in self.queue_dir.iterdir():
            if not file_path.is_file() or file_path.suffix.lower() not in extensions:
                continue

            try:
                file_stat = file_path.stat()
            except OSError as e:
                logger.debug("Skipping unreadable queue entry %s: %s", file_path, e)
                continue

            key = str(file_path)
            present.add(key)
            previous_size = self._seen_sizes.get(key)
            self._seen_sizes[key] = file_stat.st_size

            # Still being written: too fresh, or it grew since the last poll
            if now - file_stat.st_mtime < MIN_QUEUE_AGE_SECONDS:
                continue
            if previous_size is not None and previous_size != file_stat.st_size:
                continue

            eligible.append((file_stat.st_mtime, file_path))

        # Drop bookkeeping for files that are gone
        for stale_key in set(self._seen_sizes) - present:
            self._seen_sizes.pop(stale_key, None)
        for stale_key in set(self._attempts) - present:
            self._attempts.pop(stale_key, None)

        if not eligible:
            return None

        eligible.sort(key=lambda item: item[0], reverse=not self.config.queue.fifo_order)
        return eligible[0][1]
    
    async def _handle_failed_file(self, audio_path: Path, filename: str) -> None:
        """
        Re-queue a failed file a bounded number of times before purging it.

        A failure is frequently a partial read rather than a bad recording, so
        the file is given another chance once it has settled. Touching mtime
        restarts the completeness window in _get_next_file, which spaces the
        retries out instead of spinning on the same file.
        """
        key = str(audio_path)
        attempts = self._attempts.get(key, 0) + 1
        self._attempts[key] = attempts

        if attempts < MAX_PROCESS_ATTEMPTS:
            try:
                os.utime(audio_path, None)
            except OSError as e:
                logger.warning(f"Could not re-age {filename} for retry: {e}")
            logger.warning(
                f"♻️ Processing failed for {filename} "
                f"(attempt {attempts}/{MAX_PROCESS_ATTEMPTS}) — re-queued"
            )
            return

        deleted = await safe_async_unlink(audio_path)
        if deleted:
            logger.info(
                f"🗑️ Purged failed file after {attempts} attempts: {filename}"
            )

    async def _process_file(self, audio_path: Path):
        """
        Process a single audio file.
        
        Flow:
        1. Get file creation timestamp
        2. Check size filter
        3. Extract metadata
        4. Transcribe
        5. Save to database
        6. Handle audio storage
        7. Remove from queue
        """
        filename = audio_path.name
        logger.info(f"📂 Processing: {filename}")
        
        # Get file timestamp based on configured method
        timestamp_method = self.config.timestamp.method
        file_timestamp = None
        
        if timestamp_method in ["title", "both"]:
            # Try to extract from filename first
            file_timestamp = parse_timestamp_from_filename(filename)
            if file_timestamp:
                logger.info(f"📅 Timestamp from title: {file_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            elif timestamp_method == "title":
                logger.warning(f"⚠️ Could not extract timestamp from title, using current time")
                file_timestamp = datetime.now()
        
        if file_timestamp is None and timestamp_method in ["metadata", "both"]:
            # Fallback to file metadata
            try:
                file_stat = audio_path.stat()
                # Try to get birth time (creation time), fall back to modification time
                if hasattr(file_stat, 'st_birthtime'):
                    # macOS
                    file_timestamp = datetime.fromtimestamp(file_stat.st_birthtime)
                else:
                    # Linux/Windows - use modification time as proxy for creation
                    # On Windows, st_ctime is creation time; on Linux it's metadata change time
                    # st_mtime (modification time) is most reliable across platforms
                    file_timestamp = datetime.fromtimestamp(file_stat.st_mtime)
                logger.info(f"📅 Timestamp from metadata: {file_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            except Exception as e:
                logger.warning(f"⚠️ Could not get file timestamp from metadata: {e}")
                file_timestamp = datetime.now()
        
        if file_timestamp is None:
            # Final fallback
            file_timestamp = datetime.now()
            logger.warning(f"⚠️ Using current time as fallback")
        
        db = LogsSessionLocal()
        file_handled = False  # Track if file was moved/deleted
        
        try:
            # Get file size for logging
            file_size = audio_path.stat().st_size
            
            # Extract metadata
            logger.info("📊 Extracting metadata...")
            metadata = await asyncio.to_thread(extract_audio_metadata, str(audio_path))
            talkgroup = get_talkgroup_from_metadata(metadata, filename)
            
            # Transcribe
            result = await asyncio.to_thread(self.engine.transcribe, audio_path)
            
            if not result:
                logger.error(f"❌ Transcription failed for {filename}")
                file_handled = True
                await self._handle_failed_file(audio_path, filename)
                return
            
            # Apply PII/SSN redaction immediately so raw SSNs are never stored, logged, or broadcasted
            if result.get("transcript"):
                result["transcript"] = redact_ssn(result["transcript"])
            
            # Use file creation timestamp (extracted earlier)
            timestamp = file_timestamp
            log_date = timestamp.strftime("%Y-%m-%d")
            
            # Determine audio storage path
            save_audio = self.config.storage.save_audio_for_playback
            speech_only_path = result.get("speech_only_audio_path")
            if speech_only_path and Path(speech_only_path).exists():
                # VAD wrote speech-only WAV; use it instead of original
                if save_audio:
                    stored_name = audio_path.stem + ".wav"
                    audio_dest = self.audio_storage / stored_name
                    await asyncio.to_thread(shutil.move, speech_only_path, str(audio_dest))
                    file_size = audio_dest.stat().st_size
                    audio_path_stored = f"audio_storage/{audio_dest.name}"
                    logger.info(f"💾 Speech-only WAV saved: {stored_name}")
                else:
                    await safe_async_unlink(speech_only_path)
                    audio_path_stored = "file not saved"
                await safe_async_unlink(audio_path)
                file_handled = True
            elif save_audio:
                # Move original to audio_storage
                audio_dest = self.audio_storage / filename
                await asyncio.to_thread(shutil.move, str(audio_path), str(audio_dest))
                audio_path_stored = f"audio_storage/{audio_dest.name}"
                file_handled = True
                logger.info(f"💾 Audio saved: {audio_dest.name}")
            else:
                await safe_async_unlink(audio_path)
                file_handled = True
                audio_path_stored = "file not saved"
                logger.info("🗑️ Audio deleted (playback disabled)")
            
            # Save to database
            log_entry = LogEntry(
                filename=filename,
                timestamp=timestamp,
                log_date=log_date,
                duration=result["duration"],
                file_size=file_size,
                audio_path=audio_path_stored,
                transcript=result["transcript"],
                language=result["language"],
                confidence=result["confidence"],
                model_used=self.config.model.name,
                processing_time=result["processing_time"],
                talkgroup=talkgroup,
                uploaded_by="system"
            )
            
            db.add(log_entry)
            db.commit()
            
            logger.info(f"✅ Saved to database (ID: {log_entry.id})")

            # Events pipeline: dispatch asynchronously in background so audio ingestion is not blocked
            settings = get_settings()
            if getattr(settings.config, "events_pipeline", None) and settings.config.events_pipeline.enabled:
                transcript_text = result.get("transcript") or ""
                from .task_manager import task_manager
                task_manager.spawn(
                    _dispatch_events_pipeline(
                        talkgroup=talkgroup,
                        transcript_text=transcript_text,
                        log_entry_id=log_entry.id,
                        timestamp=timestamp,
                    ),
                    name=f"events-pipeline-{log_entry.id}",
                )

            # Increment processed counter
            watcher_service = get_watcher_service()
            watcher_service.increment_processed()
            
            # Broadcast to WebSocket clients
            await self.websocket_manager.broadcast({
                "type": "transcription",
                "data": {
                    "id": log_entry.id,
                    "filename": filename,
                    "transcript": result["transcript"],
                    "talkgroup": talkgroup,
                    "duration": result["duration"],
                    "confidence": result["confidence"],
                    "timestamp": timestamp.isoformat(),
                    "audio_path": audio_path_stored,
                    "file_size": file_size
                }
            })
            
        except Exception as e:
            logger.error(f"❌ Processing failed for {filename}: {e}")
            # CUDA reports OOM asynchronously, so it can surface here at the
            # await on the worker thread rather than inside the engine. Reclaim
            # the allocator here too, otherwise the reservation persists and
            # every subsequent file OOMs as well.
            self.engine.release_gpu_memory()
            self.engine.release_memory()
            # Re-queue with a bounded retry rather than deleting a file that may
            # simply have been read while it was still being written.
            if not file_handled:
                await self._handle_failed_file(audio_path, filename)
        
        finally:
            self.engine.release_gpu_memory()
            self.engine.release_memory()
            db.close()


# Global processor instance
_processor = None


def get_processor() -> QueueProcessor:
    """Get or create queue processor instance."""
    global _processor
    if _processor is None:
        _processor = QueueProcessor()
    return _processor
