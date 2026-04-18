"""Watcher control routes."""
import psutil
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from ..models.user import User
from .auth import get_current_active_user
from ..services.watcher import get_watcher_service
from ..services.queue_processor import get_processor
from ..services.websocket import websocket_manager

router = APIRouter(prefix="/api/watcher", tags=["watcher"])

# Get service instances
watcher_service = get_watcher_service()
queue_processor = get_processor()


class RejectionReport(BaseModel):
    count: int = Field(default=1, ge=1, le=1000)


@router.get("/status")
async def get_watcher_status(current_user: User = Depends(get_current_active_user)):
    """Get watcher status and statistics."""
    from ..config import get_settings
    settings = get_settings()
    
    # Get memory info
    mem = psutil.virtual_memory()
    memory_used_gb = mem.used / (1024 ** 3)
    memory_total_gb = mem.total / (1024 ** 3)
    memory_percent = mem.percent
    
    # Get CPU info
    cpu_percent = psutil.cpu_percent(interval=None)
    
    # Get engine device from config
    engine_device = settings.config.model.device.upper() if settings.config.model.device else "CPU"
    
    return {
        **watcher_service.get_stats(),
        **watcher_service.get_live_stats(),
        "queue_count": queue_processor.get_queue_count(),
        "processor_running": queue_processor.running,
        "memory_used_gb": round(memory_used_gb, 1),
        "memory_total_gb": round(memory_total_gb, 1),
        "memory_percent": memory_percent,
        "cpu_percent": cpu_percent,
        "engine_device": engine_device
    }


@router.post("/start")
async def start_watcher(current_user: User = Depends(get_current_active_user)):
    """Start the file watcher and transcription engine."""
    watcher_success = await watcher_service.start()
    
    # Also start the queue processor (transcription engine)
    await queue_processor.start()
    
    return {
        "success": watcher_success,
        "message": "Watcher and engine started" if watcher_success else "Failed to start watcher",
        "stats": watcher_service.get_stats()
    }


@router.post("/stop")
async def stop_watcher(current_user: User = Depends(get_current_active_user)):
    """Stop the file watcher and transcription engine."""
    watcher_success = await watcher_service.stop()
    
    # Also stop the queue processor (transcription engine)
    await queue_processor.stop()
    
    return {
        "success": watcher_success,
        "message": "Watcher and engine stopped" if watcher_success else "Failed to stop watcher",
        "stats": watcher_service.get_stats()
    }


@router.post("/pause")
async def pause_watcher(current_user: User = Depends(get_current_active_user)):
    """Pause the file watcher and transcription engine."""
    success = await watcher_service.pause()
    await queue_processor.pause()
    return {
        "success": success,
        "message": "Watcher and engine paused" if success else "Failed to pause watcher",
        "stats": watcher_service.get_stats()
    }


@router.post("/resume")
async def resume_watcher(current_user: User = Depends(get_current_active_user)):
    """Resume the file watcher and transcription engine."""
    success = await watcher_service.resume()
    await queue_processor.resume()
    return {
        "success": success,
        "message": "Watcher and engine resumed" if success else "Failed to resume watcher",
        "stats": watcher_service.get_stats()
    }


@router.post("/rejected")
async def report_rejected(
    payload: RejectionReport,
    current_user: User = Depends(get_current_active_user),
):
    """Report rejected files from watchdog client (daily stat)."""
    watcher_service.increment_rejected(payload.count)
    return {"success": True, "files_rejected": payload.count}


# WebSocket endpoint (no auth for simplicity - only logged-in users can access dashboard anyway)
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await websocket_manager.connect(websocket)
    try:
        # Keep connection alive and listen for client messages
        while True:
            data = await websocket.receive_text()
            # Echo back (or handle commands if needed)
            # For now, just keep connection alive
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
