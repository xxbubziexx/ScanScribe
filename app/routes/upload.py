"""Upload routes for client file transfers."""
import asyncio
import os
import logging
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.user import User
from .auth import get_current_active_user
from ..config import get_settings
from ..services.websocket import websocket_manager
from ..schemas.upload import UploadAudioResponse, UploadStatusResponse

router = APIRouter(prefix="/api/upload", tags=["upload"])
logger = logging.getLogger(__name__)


@router.post("/audio", response_model=UploadAudioResponse)
async def upload_audio(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> UploadAudioResponse:
    """Upload audio file to ingest directory without blocking event loop on disk I/O."""
    settings = get_settings()
    client_ip = request.client.host if request.client else "unknown"
    
    # Log client connection (automatically goes to console, file, and WebSocket)
    logger.info(f"📤 Client upload: {current_user.username} @ {client_ip}")
    
    # Validate file extension
    allowed_extensions = settings.config.watchdog_client.extensions
    file_ext = Path(file.filename).suffix.lower()
    
    if file_ext not in allowed_extensions:
        logger.warning(f"❌ Invalid file type from {current_user.username}: {file.filename}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # Save directly to queue (client already handled stability)
    try:
        queue_dir = settings.ingest_dir / "queue"
        queue_dir.mkdir(exist_ok=True)
        
        queue_path = queue_dir / file.filename
        
        # Handle duplicate filenames
        counter = 1
        original_stem = Path(file.filename).stem
        while queue_path.exists():
            queue_path = queue_dir / f"{original_stem}_{counter}{file_ext}"
            counter += 1
        
        # Read uploaded bytes and write to disk in worker thread (non-blocking)
        content = await file.read()
        await asyncio.to_thread(queue_path.write_bytes, content)
        
        file_size_mb = len(content) / (1024 * 1024)
        
        logger.info(f"✅ Uploaded: {queue_path.name} ({file_size_mb:.2f} MB) from {current_user.username} @ {client_ip}")
        
        return UploadAudioResponse(
            message="File uploaded successfully",
            filename=queue_path.name,
            size_mb=round(file_size_mb, 2),
            path=str(queue_path)
        )
        
    except Exception as e:
        logger.error(f"❌ Upload failed from {current_user.username} @ {client_ip}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/status", response_model=UploadStatusResponse)
async def upload_status(
    request: Request,
    current_user: User = Depends(get_current_active_user)
) -> UploadStatusResponse:
    """Get upload endpoint status."""
    settings = get_settings()
    client_ip = request.client.host if request.client else "unknown"
    
    logger.info(f"🔌 Client connected: {current_user.username} @ {client_ip}")
    await websocket_manager.send_log(
        f"🔌 Client connected: {current_user.username} @ {client_ip}",
        level="info"
    )
    
    from .. import __version__
    return UploadStatusResponse(
        online=True,
        ingest_directory=str(settings.ingest_dir),
        allowed_extensions=settings.config.watchdog_client.extensions,
        server_version=__version__
    )

