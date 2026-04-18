"""Simplified file watcher service for monitoring ingest directory.

The client (watchdog_client) handles all stability checking and rejection.
This server-side watcher just detects files and immediately moves them to queue.
"""
import os
import time
import asyncio
import shutil
from typing import Optional, Dict, Set
from pathlib import Path
import logging
from datetime import datetime

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from ..config import get_settings
from ..database import LogsSessionLocal
from ..models.log_entry import LogEntry
from .websocket import websocket_manager

logger = logging.getLogger(__name__)


class SimpleFileHandler(FileSystemEventHandler):
    """Handles file system events - immediately queues audio files."""
    
    def __init__(self, watcher_service):
        self.watcher_service = watcher_service
        self._processing: Set[str] = set()  # Prevent duplicate processing
        
    def on_created(self, event):
        if event.is_directory:
            return
        self._handle_file(event.src_path)
        
    def on_moved(self, event):
        """Handle files moved into the directory."""
        if event.is_directory:
            return
        self._handle_file(event.dest_path)
        
    def _handle_file(self, file_path: str) -> None:
        """Handle new file - immediately move to queue."""
        filename = os.path.basename(file_path)
        
        # Skip if already processing
        if file_path in self._processing:
            return
            
        # Check if it's an audio file
        ext = os.path.splitext(file_path)[1].lower()
        extensions = self.watcher_service.extensions
        
        if ext not in extensions:
            logger.debug(f"Ignoring {filename} - not a monitored extension")
            return
        
        # Skip if file doesn't exist (race condition)
        if not os.path.exists(file_path):
            return
            
        self._processing.add(file_path)
        
        try:
            # Small delay to ensure file is fully written (client already validated)
            time.sleep(0.2)
            
            # Move to queue
            self.watcher_service._queue_file(file_path)
            
        finally:
            self._processing.discard(file_path)


class WatcherService:
    """
    Simplified watcher service for monitoring ingest directory.
    
    The client handles stability checking and rejection.
    This just moves files from /ingest to /ingest/queue for processing.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.ingest_dir = Path(self.settings.ingest_dir)
        self.queue_dir = self.ingest_dir / "queue"
        self.observer: Optional[Observer] = None
        self._running = False
        self._paused = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Get extensions from watchdog_client config
        self.extensions = set(self.settings.config.watchdog_client.extensions)
        
        # Statistics
        self.stats = {
            'files_queued': 0,
            'files_processed': 0,
            'start_time': None
        }

        # Daily counters (reset automatically when date changes)
        self._daily_date = datetime.now().date().isoformat()
        self._files_rejected_daily = 0
        
        # Ensure directories exist
        self.ingest_dir.mkdir(parents=True, exist_ok=True)
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize file handler
        self.file_handler = SimpleFileHandler(self)
        
    async def start(self) -> bool:
        """Start watching the ingest directory."""
        if self._running:
            await websocket_manager.send_log(
                "Watcher already running", 
                level="warning", 
                tag="watcher"
            )
            return False
            
        try:
            # Get current event loop
            self._loop = asyncio.get_running_loop()
            
            # Process any existing files first
            await self._process_existing_files()
            
            # Start observer
            self.observer = Observer()
            self.observer.schedule(self.file_handler, str(self.ingest_dir), recursive=False)
            self.observer.start()
            self._running = True
            self._paused = False
            self.stats['start_time'] = time.time()
            
            await websocket_manager.send_log(
                f"Watcher started - Monitoring: {self.ingest_dir}", 
                level="success", 
                tag="watcher"
            )
            await websocket_manager.send_status("watcher_started", self.get_stats())
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start watcher: {e}")
            await websocket_manager.send_log(
                f"Failed to start watcher: {e}", 
                level="error", 
                tag="watcher"
            )
            return False
            
    async def stop(self) -> bool:
        """Stop watching."""
        if not self._running:
            return False
            
        try:
            self._running = False
            self._paused = False
            
            if self.observer:
                self.observer.stop()
                self.observer.join(timeout=2)
                self.observer = None
                
            self.stats['start_time'] = None
            
            await websocket_manager.send_log(
                "Watcher stopped", 
                level="info", 
                tag="watcher"
            )
            await websocket_manager.send_status("watcher_stopped", self.get_stats())
            
            return True
            
        except Exception as e:
            logger.error(f"Error stopping watcher: {e}")
            return False
            
    async def pause(self) -> bool:
        """Pause file watching."""
        if not self._running or self._paused:
            return False
            
        self._paused = True
        await websocket_manager.send_log(
            "Watcher paused", 
            level="info", 
            tag="watcher"
        )
        await websocket_manager.send_status("watcher_paused", self.get_stats())
        return True
        
    async def resume(self) -> bool:
        """Resume file watching."""
        if not self._running or not self._paused:
            return False
            
        self._paused = False
        await websocket_manager.send_log(
            "Watcher resumed", 
            level="info", 
            tag="watcher"
        )
        await websocket_manager.send_status("watcher_resumed", self.get_stats())
        return True
        
    def is_running(self) -> bool:
        """Check if watcher is running."""
        return self._running
        
    def is_paused(self) -> bool:
        """Check if watcher is paused."""
        return self._paused
        
    def get_stats(self) -> Dict:
        """Get watcher statistics."""
        uptime = None
        if self.stats['start_time']:
            uptime = int(time.time() - self.stats['start_time'])
            
        return {
            'running': self._running,
            'paused': self._paused,
            'is_running': self._running and not self._paused,
            'files_queued': self.stats['files_queued'],
            'files_processed': self.stats['files_processed'],
            'uptime_seconds': uptime,
            'monitoring_dir': str(self.ingest_dir)
        }
        
    def increment_processed(self) -> None:
        """Increment processed file counter (called by transcription engine)."""
        self.stats['files_processed'] += 1
        
        # Broadcast stats update
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                websocket_manager.send_status("stats_update", self.get_live_stats()),
                self._loop
            )

    def increment_rejected(self, count: int = 1) -> None:
        """Increment rejected file counter (reported by watchdog client)."""
        if count <= 0:
            return

        today = datetime.now().date().isoformat()
        if today != self._daily_date:
            self._daily_date = today
            self._files_rejected_daily = 0

        self._files_rejected_daily += count

        # Broadcast stats update
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                websocket_manager.send_status("stats_update", self.get_live_stats()),
                self._loop
            )
        
    def get_live_stats(self) -> Dict:
        """Get live counts of files in directories."""
        try:
            # Daily rollover
            today = datetime.now().date().isoformat()
            if today != self._daily_date:
                self._daily_date = today
                self._files_rejected_daily = 0

            # Count files in ingest (exclude queue subdirectory)
            ingest_count = 0
            for file_path in self.ingest_dir.iterdir():
                if file_path.is_file():
                    ext = file_path.suffix.lower()
                    if ext in self.extensions:
                        ingest_count += 1
            
            # Count files in queue
            queue_count = 0
            if self.queue_dir.exists():
                for file_path in self.queue_dir.iterdir():
                    if file_path.is_file():
                        ext = file_path.suffix.lower()
                        if ext in self.extensions:
                            queue_count += 1
            
            # Get total processed count from database
            db = LogsSessionLocal()
            try:
                # Daily processed (resets daily)
                total_processed = db.query(LogEntry).filter(
                    LogEntry.is_deleted == False,
                    LogEntry.log_date == today,
                ).count()
            finally:
                db.close()
            
            return {
                'ingest_count': ingest_count,
                'queue_count': queue_count,
                'files_processed': total_processed,
                'files_rejected': self._files_rejected_daily,
            }
        except Exception as e:
            logger.error(f"Error getting live stats: {e}")
            return {
                'ingest_count': 0,
                'queue_count': 0,
                'files_processed': 0,
                'files_rejected': 0,
            }
        
    async def _process_existing_files(self) -> None:
        """Move any existing files from ingest to queue."""
        try:
            audio_files = []
            for file_path in self.ingest_dir.iterdir():
                if file_path.is_file():
                    ext = file_path.suffix.lower()
                    if ext in self.extensions:
                        audio_files.append(file_path)
                        
            if audio_files:
                await websocket_manager.send_log(
                    f"Found {len(audio_files)} existing file(s) - moving to queue", 
                    level="info", 
                    tag="watcher"
                )
                
                for file_path in audio_files:
                    self._queue_file(str(file_path))
                    
        except Exception as e:
            logger.error(f"Error processing existing files: {e}")
            
    def _queue_file(self, file_path: str) -> Optional[str]:
        """Move file from ingest to queue directory."""
        filename = os.path.basename(file_path)
        
        try:
            if not os.path.exists(file_path):
                logger.warning(f"File no longer exists: {filename}")
                return None
                
            queue_file_path = self.queue_dir / filename
            
            # Handle filename conflicts
            counter = 1
            original_stem = Path(filename).stem
            original_suffix = Path(filename).suffix
            
            while queue_file_path.exists():
                new_filename = f"{original_stem}_{counter}{original_suffix}"
                queue_file_path = self.queue_dir / new_filename
                counter += 1
                
            # Move the file
            shutil.move(file_path, str(queue_file_path))
            self.stats['files_queued'] += 1
            
            # Log to WebSocket
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    websocket_manager.send_log(
                        f"Queued: {filename}", 
                        level="success", 
                        tag="queue"
                    ),
                    self._loop
                )
                
                # Send stats update
                asyncio.run_coroutine_threadsafe(
                    websocket_manager.send_status("stats_update", self.get_live_stats()),
                    self._loop
                )
            
            logger.info(f"File queued: {queue_file_path}")
            return str(queue_file_path)
            
        except Exception as e:
            logger.error(f"Error moving {filename} to queue: {e}")
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    websocket_manager.send_log(
                        f"Error queuing {filename}: {e}", 
                        level="error", 
                        tag="watcher"
                    ),
                    self._loop
                )
            return None


# Global watcher instance
_watcher_service = None


def get_watcher_service() -> WatcherService:
    """Get or create watcher service instance."""
    global _watcher_service
    if _watcher_service is None:
        _watcher_service = WatcherService()
    return _watcher_service
