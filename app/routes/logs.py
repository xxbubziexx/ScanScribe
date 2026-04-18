"""Logs routes."""
import re
import zipfile
from pathlib import Path
from datetime import date
from typing import Optional, List
import io
import csv

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..database import get_logs_db
from ..models.user import User
from ..models.log_entry import LogEntry
from .auth import get_current_active_user

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("")
async def get_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    search: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sort_by: str = Query("timestamp_desc"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db)
):
    """Get transcription logs with pagination and filtering."""
    # Build query (exclude soft-deleted entries)
    query = db.query(LogEntry).filter(LogEntry.is_deleted == False)
    
    # Apply search filter
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                LogEntry.transcript.like(search_pattern),
                LogEntry.filename.like(search_pattern),
                LogEntry.talkgroup.like(search_pattern)
            )
        )
    
    # Apply date filters
    if date_from:
        query = query.filter(LogEntry.log_date >= date_from.isoformat())
    if date_to:
        query = query.filter(LogEntry.log_date <= date_to.isoformat())
    
    # Apply sorting
    if sort_by == "timestamp_desc":
        query = query.order_by(LogEntry.timestamp.desc())
    elif sort_by == "timestamp_asc":
        query = query.order_by(LogEntry.timestamp.asc())
    elif sort_by == "filename":
        query = query.order_by(LogEntry.filename.asc())
    elif sort_by == "talkgroup":
        query = query.order_by(LogEntry.talkgroup.asc())
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    offset = (page - 1) * page_size
    logs = query.offset(offset).limit(page_size).all()
    
    # Format results
    logs_data = []
    for log in logs:
        logs_data.append({
            "id": log.id,
            "timestamp": log.timestamp,
            "filename": log.filename,
            "talkgroup": log.talkgroup,
            "transcript": log.transcript,
            "duration": log.duration,
            "file_size": log.file_size,
            "confidence": log.confidence,
            "audio_path": log.audio_path,
            "log_date": log.log_date,
            "created_at": log.created_at.isoformat() if log.created_at else None
        })
    
    return {
        "logs": logs_data,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }


@router.get("/active-dates")
async def get_active_dates(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db)
):
    """Get all dates that have log entries."""
    # Query distinct log_date values
    results = db.query(LogEntry.log_date).distinct().filter(LogEntry.log_date.isnot(None)).all()
    
    dates = [row[0] for row in results if row[0]]
    
    return {"dates": sorted(dates)}


@router.get("/talkgroups")
async def get_talkgroups(
    today: bool = Query(False, description="If true, only talkgroups that appear in today's log entries"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db)
):
    """Get distinct talkgroups from log entries (for filter dropdown). Use today=1 for only today's talkgroups."""
    query = db.query(LogEntry.talkgroup).distinct().filter(LogEntry.talkgroup.isnot(None))
    if today:
        today_str = date.today().isoformat()
        query = query.filter(LogEntry.log_date == today_str)
    rows = query.order_by(LogEntry.talkgroup).all()
    talkgroups = [r[0] if r[0] and str(r[0]).strip() else "N/A" for r in rows]
    # Dedupe and sort (N/A at end)
    seen = set()
    out = []
    for tg in talkgroups:
        if tg not in seen:
            seen.add(tg)
            out.append(tg)
    out.sort(key=lambda x: (x == "N/A", x))
    return {"talkgroups": out}


@router.get("/export")
async def export_logs_csv(
    search: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db)
):
    """Export logs as CSV."""
    # Build query (exclude soft-deleted entries)
    query = db.query(LogEntry).filter(LogEntry.is_deleted == False)
    
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                LogEntry.transcript.like(search_pattern),
                LogEntry.filename.like(search_pattern),
                LogEntry.talkgroup.like(search_pattern)
            )
        )
    
    if date_from:
        query = query.filter(LogEntry.log_date >= date_from.isoformat())
    if date_to:
        query = query.filter(LogEntry.log_date <= date_to.isoformat())
    
    query = query.order_by(LogEntry.timestamp.desc())
    logs = query.all()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['Timestamp', 'Filename', 'Talkgroup', 'Transcript', 'Duration', 'File Size', 'Log Date'])
    
    # Write data
    for log in logs:
        writer.writerow([
            log.timestamp,
            log.filename,
            log.talkgroup,
            log.transcript,
            log.duration,
            log.file_size,
            log.log_date
        ])
    
    # Create response
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=scanscribe_logs.csv"}
    )


@router.delete("/{log_id}")
async def delete_log(
    log_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db)
):
    """Delete a single log entry. Requires admin privileges."""
    from fastapi import HTTPException
    from pathlib import Path
    from ..config import get_settings
    
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    log = db.query(LogEntry).filter(LogEntry.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log entry not found")
    
    # Delete associated audio file if exists
    if log.audio_path and log.audio_path != "file not saved":
        settings = get_settings()
        audio_file = Path(settings.output_dir) / Path(log.audio_path).name
        if audio_file.exists():
            try:
                audio_file.unlink()
            except Exception:
                pass  # Continue even if file deletion fails
    
    db.delete(log)
    db.commit()
    
    return {"success": True, "message": "Entry deleted"}


class BulkDeleteRequest(BaseModel):
    ids: List[int]


@router.post("/bulk-delete")
async def bulk_delete_logs(
    request: BulkDeleteRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db)
):
    """Delete multiple log entries. Requires admin privileges."""
    from fastapi import HTTPException
    from pathlib import Path
    from ..config import get_settings
    
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    if not request.ids:
        raise HTTPException(status_code=400, detail="No IDs provided")
    
    settings = get_settings()
    deleted_count = 0
    
    for log_id in request.ids:
        log = db.query(LogEntry).filter(LogEntry.id == log_id).first()
        if log:
            # Delete associated audio file if exists
            if log.audio_path and log.audio_path != "file not saved":
                audio_file = Path(settings.output_dir) / Path(log.audio_path).name
                if audio_file.exists():
                    try:
                        audio_file.unlink()
                    except Exception:
                        pass
            
            db.delete(log)
            deleted_count += 1
    
    db.commit()
    
    return {"success": True, "deleted": deleted_count}


class BulkDownloadRequest(BaseModel):
    ids: List[int]


def _safe_zip_name(name: str, max_len: int = 100) -> str:
    """Sanitize a filename for use inside a zip (no path separators, safe chars)."""
    base = Path(name).name if name else "file"
    stem = Path(base).stem or base
    safe = re.sub(r"[^\w\-.]", "_", stem)[:max_len]
    return safe.strip("_") or "file"


@router.post("/bulk-download")
async def bulk_download_logs(
    request: BulkDownloadRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_logs_db),
):
    """Download selected log entries as a zip (transcript .txt + audio when available)."""
    from ..config import get_settings

    if not request.ids:
        raise HTTPException(status_code=400, detail="No IDs provided")

    logs = (
        db.query(LogEntry)
        .filter(LogEntry.id.in_(request.ids), LogEntry.is_deleted == False)
        .order_by(LogEntry.timestamp.asc())
        .all()
    )
    if not logs:
        raise HTTPException(status_code=404, detail="No matching log entries found")

    settings = get_settings()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for log in logs:
            base = _safe_zip_name(log.filename or f"log_{log.id}")
            # Transcript as .txt (always include)
            header = [
                f"ID: {log.id}",
                f"Filename: {log.filename or ''}",
                f"Timestamp: {log.timestamp}",
                f"Talkgroup: {log.talkgroup or 'N/A'}",
                f"Duration: {log.duration or 0}s",
                "",
            ]
            transcript_text = (log.transcript or "").strip()
            content = "\n".join(header) + (("\n" + transcript_text) if transcript_text else "")
            txt_arcname = f"{log.id}_{base}.txt"
            zf.writestr(txt_arcname, content.encode("utf-8"))
            # Audio file if present
            if log.audio_path and log.audio_path != "file not saved":
                audio_path = Path(settings.output_dir) / Path(log.audio_path).name
                if audio_path.exists():
                    zf.write(audio_path, f"{log.id}_{base}{audio_path.suffix}")

    buf.seek(0)
    filename = f"scanscribe_bulk_{date.today().isoformat()}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
