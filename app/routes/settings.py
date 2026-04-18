"""Settings routes."""
import os
import signal
import yaml
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from ..database import get_db, get_logs_db
from ..models.user import User
from .auth import get_current_active_user
from ..config import get_settings, save_config, reload_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ConfigContent(BaseModel):
    """Config file content."""
    content: str


@router.get("/config")
async def get_config_file(
    current_user: User = Depends(get_current_active_user)
):
    """Get raw config.yml content."""
    settings = get_settings()
    
    try:
        with open(settings.config_path, 'r') as f:
            content = f.read()
        return {"content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="config.yml not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read config: {str(e)}")


@router.post("/config")
async def save_config_file(
    config: ConfigContent,
    current_user: User = Depends(get_current_active_user)
):
    """Save raw config.yml content."""
    settings = get_settings()
    
    # Validate YAML syntax
    try:
        yaml.safe_load(config.content)
    except yaml.YAMLError as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid YAML syntax: {str(e)}"
        )
    
    # Save to file
    try:
        # Direct write (atomic rename doesn't work well with Docker bind mounts)
        with open(settings.config_path, 'w') as f:
            f.write(config.content)
        
        # Reload settings
        reload_settings()
        
        return {"message": "Configuration saved successfully. Click 'Restart' to apply changes."}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {str(e)}")


@router.post("/restart")
async def restart_application(
    current_user: User = Depends(get_current_active_user)
):
    """Restart the application to apply config changes."""
    try:
        # Send SIGTERM to self (docker restart policy will restart)
        pid = os.getpid()
        os.kill(pid, signal.SIGTERM)
        return {"message": "Application restarting..."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restart: {str(e)}")


@router.get("/audio-storage/stats")
async def get_audio_storage_stats(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get audio storage statistics."""
    import logging
    logger = logging.getLogger(__name__)
    
    settings = get_settings()
    audio_dir = settings.output_dir
    
    try:
        total_files = 0
        total_size = 0
        file_types = {}
        
        if audio_dir.exists():
            for file_path in audio_dir.rglob("*"):
                if file_path.is_file():
                    total_files += 1
                    size = file_path.stat().st_size
                    total_size += size
                    
                    ext = file_path.suffix.lower()
                    if ext not in file_types:
                        file_types[ext] = {"count": 0, "size": 0}
                    file_types[ext]["count"] += 1
                    file_types[ext]["size"] += size
        
        # Convert to MB/GB
        total_size_mb = total_size / (1024 * 1024)
        total_size_gb = total_size / (1024 * 1024 * 1024)
        
        return {
            "total_files": total_files,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size_mb, 2),
            "total_size_gb": round(total_size_gb, 2),
            "file_types": file_types,
            "directory": str(audio_dir)
        }
        
    except Exception as e:
        logger.error(f"Error getting audio storage stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.post("/audio-storage/purge")
async def purge_audio_storage(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db)
):
    """Purge all saved audio files."""
    import logging
    logger = logging.getLogger(__name__)
    
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    settings = get_settings()
    audio_dir = settings.output_dir
    
    try:
        deleted_count = 0
        deleted_size = 0
        errors = []
        
        if audio_dir.exists():
            for file_path in audio_dir.rglob("*"):
                if file_path.is_file():
                    try:
                        size = file_path.stat().st_size
                        file_path.unlink()
                        deleted_count += 1
                        deleted_size += size
                    except Exception as e:
                        errors.append(f"{file_path.name}: {str(e)}")
        
        # Update database entries to "file not saved"
        from ..models.log_entry import LogEntry
        
        updated = db.query(LogEntry).filter(
            LogEntry.audio_path != "file not saved"
        ).update({"audio_path": "file not saved"})
        db.commit()
        
        logger.info(f"Purged {deleted_count} audio files ({deleted_size / (1024*1024):.2f} MB)")
        
        return {
            "success": True,
            "deleted_files": deleted_count,
            "deleted_size_mb": round(deleted_size / (1024 * 1024), 2),
            "database_updated": updated,
            "errors": errors
        }
        
    except Exception as e:
        logger.error(f"Error purging audio storage: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to purge: {str(e)}")


@router.get("/audio-storage/download-zip")
async def download_audio_zip(
    current_user: User = Depends(get_current_active_user)
):
    """Download all saved audio files as a ZIP archive."""
    import logging
    import zipfile
    import tempfile
    from datetime import datetime
    from starlette.background import BackgroundTask
    from fastapi.responses import FileResponse

    logger = logging.getLogger(__name__)

    settings = get_settings()
    audio_dir = settings.output_dir

    try:
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        temp_zip.close()

        with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            file_count = 0
            if audio_dir.exists():
                for file_path in audio_dir.rglob("*"):
                    if file_path.is_file():
                        arcname = file_path.relative_to(audio_dir)
                        zipf.write(file_path, arcname)
                        file_count += 1

        if file_count == 0:
            os.unlink(temp_zip.name)
            raise HTTPException(status_code=404, detail="No audio files to download")

        logger.info(f"Created ZIP archive with {file_count} audio files for {current_user.username}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"scanscribe_audio_{timestamp}.zip"
        cleanup = BackgroundTask(os.unlink, temp_zip.name)

        return FileResponse(
            temp_zip.name,
            media_type="application/zip",
            filename=filename,
            background=cleanup,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating ZIP archive: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create ZIP: {str(e)}")
