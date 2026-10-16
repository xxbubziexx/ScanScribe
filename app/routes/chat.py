"""FastAPI routes for Scanner Intelligence conversational queries."""
import asyncio
import json
import logging
from datetime import datetime
from typing import List, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db, SessionLocal, utcnow
from ..models.user import User
from ..models.chat import ChatThread, ChatMessage
from ..models.log_entry import LogEntry
from ..schemas.chat import (
    ChatThreadCreate,
    ChatThreadUpdate,
    ChatThreadOut,
    ChatThreadDetailOut,
    ChatMessageOut,
    ChatPromptInput,
    ChatTimeScope,
    TransmissionLookupOut,
    ToolCallRecord,
)
from .auth import get_current_active_user
from ..services.chat_context import (
    parse_time_scope,
    query_transmissions,
    build_system_prompt,
    build_agent_system_prompt,
    build_agent_context_block,
    format_context_block,
    extract_cited_ids,
)
from ..services.agent_tools import ToolContext
from ..services.chat_streamer import AssistantTrace, stream_chat_completion
from ..config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["scanner-intelligence"])


def _parse_tool_calls(raw: Optional[str], message_id: int) -> Optional[List[ToolCallRecord]]:
    """Deserialize persisted tool call records; malformed rows are logged and dropped."""
    if not raw:
        return None
    try:
        items = json.loads(raw)
        return [ToolCallRecord(**item) for item in items]
    except (json.JSONDecodeError, TypeError, ValueError) as ex:
        logger.warning("Malformed tool_calls JSON on chat message %s: %s", message_id, ex)
        return None


def _load_agent_context(start_time: datetime, end_time: datetime, time_desc: str) -> Tuple[str, int]:
    """Build the compact agent context header in a worker thread with its own session."""
    with SessionLocal() as ctx_db:
        return build_agent_context_block(ctx_db, start_time, end_time, time_desc)


@router.get("/threads", response_model=List[ChatThreadOut])
def list_threads(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> List[ChatThreadOut]:
    """List all chat threads for the current user."""
    threads = (
        db.query(ChatThread)
        .filter(ChatThread.user_id == current_user.id)
        .order_by(ChatThread.updated_at.desc())
        .all()
    )

    out: List[ChatThreadOut] = []
    for t in threads:
        msg_count = db.query(func.count(ChatMessage.id)).filter(ChatMessage.thread_id == t.id).scalar() or 0
        tgs = json.loads(t.talkgroups) if t.talkgroups else []
        out.append(
            ChatThreadOut(
                id=t.id,
                user_id=t.user_id,
                title=t.title,
                time_scope_preset=t.time_scope_preset,
                start_time=t.start_time,
                end_time=t.end_time,
                talkgroups=tgs,
                created_at=t.created_at,
                updated_at=t.updated_at,
                message_count=msg_count,
            )
        )
    return out


@router.post("/threads", response_model=ChatThreadOut, status_code=status.HTTP_201_CREATED)
def create_thread(
    data: ChatThreadCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ChatThreadOut:
    """Create a new chat query thread."""
    tgs_json = json.dumps(data.talkgroups) if data.talkgroups else None
    thread = ChatThread(
        user_id=current_user.id,
        title=data.title or "New Query",
        time_scope_preset=data.time_scope_preset or "today",
        start_time=data.start_time,
        end_time=data.end_time,
        talkgroups=tgs_json,
    )
    db.add(thread)
    db.commit()
    db.refresh(thread)

    return ChatThreadOut(
        id=thread.id,
        user_id=thread.user_id,
        title=thread.title,
        time_scope_preset=thread.time_scope_preset,
        start_time=thread.start_time,
        end_time=thread.end_time,
        talkgroups=data.talkgroups or [],
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        message_count=0,
    )


@router.get("/threads/{thread_id}", response_model=ChatThreadDetailOut)
def get_thread(
    thread_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ChatThreadDetailOut:
    """Get thread detail and complete message history."""
    thread = (
        db.query(ChatThread)
        .filter(ChatThread.id == thread_id, ChatThread.user_id == current_user.id)
        .first()
    )
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    messages_out: List[ChatMessageOut] = []
    for m in thread.messages:
        cited = json.loads(m.cited_log_ids) if m.cited_log_ids else []
        messages_out.append(
            ChatMessageOut(
                id=m.id,
                thread_id=m.thread_id,
                role=m.role,
                content=m.content,
                cited_log_ids=cited,
                thought=m.thought,
                tool_calls=_parse_tool_calls(m.tool_calls, m.id),
                created_at=m.created_at,
            )
        )

    tgs = json.loads(thread.talkgroups) if thread.talkgroups else []
    return ChatThreadDetailOut(
        id=thread.id,
        user_id=thread.user_id,
        title=thread.title,
        time_scope_preset=thread.time_scope_preset,
        start_time=thread.start_time,
        end_time=thread.end_time,
        talkgroups=tgs,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        message_count=len(messages_out),
        messages=messages_out,
    )


@router.patch("/threads/{thread_id}", response_model=ChatThreadOut)
def update_thread(
    thread_id: int,
    data: ChatThreadUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ChatThreadOut:
    """Update title, time scope, or talkgroup filters on a thread."""
    thread = (
        db.query(ChatThread)
        .filter(ChatThread.id == thread_id, ChatThread.user_id == current_user.id)
        .first()
    )
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    if data.title is not None:
        thread.title = data.title.strip() or "Untitled Query"
    if data.time_scope_preset is not None:
        thread.time_scope_preset = data.time_scope_preset
    if data.start_time is not None:
        thread.start_time = data.start_time
    if data.end_time is not None:
        thread.end_time = data.end_time
    if data.talkgroups is not None:
        thread.talkgroups = json.dumps(data.talkgroups)

    thread.updated_at = utcnow()
    db.commit()
    db.refresh(thread)

    msg_count = db.query(func.count(ChatMessage.id)).filter(ChatMessage.thread_id == thread.id).scalar() or 0
    tgs = json.loads(thread.talkgroups) if thread.talkgroups else []

    return ChatThreadOut(
        id=thread.id,
        user_id=thread.user_id,
        title=thread.title,
        time_scope_preset=thread.time_scope_preset,
        start_time=thread.start_time,
        end_time=thread.end_time,
        talkgroups=tgs,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        message_count=msg_count,
    )


@router.delete("/threads/{thread_id}")
def delete_thread(
    thread_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Delete a thread and its messages."""
    thread = (
        db.query(ChatThread)
        .filter(ChatThread.id == thread_id, ChatThread.user_id == current_user.id)
        .first()
    )
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    db.delete(thread)
    db.commit()
    return {"ok": True, "deleted_id": thread_id}


@router.get("/talkgroups", response_model=List[str])
def list_available_talkgroups(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> List[str]:
    """List distinct talkgroups recorded in log entries."""
    rows = (
        db.query(LogEntry.talkgroup)
        .filter(
            LogEntry.is_deleted == False,
            LogEntry.talkgroup.isnot(None),
            LogEntry.talkgroup != "",
            LogEntry.talkgroup != "N/A",
        )
        .distinct()
        .order_by(LogEntry.talkgroup.asc())
        .limit(100)
        .all()
    )
    return [r[0] for r in rows if r[0]]


@router.get("/transmissions/{log_id}", response_model=TransmissionLookupOut)
def get_transmission_detail(
    log_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> TransmissionLookupOut:
    """Retrieve transmission details and audio URL for grounding verification."""
    log = db.query(LogEntry).filter(LogEntry.id == log_id).first()
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transmission not found")

    audio_url = ""
    if log.audio_path and log.audio_path != "file not saved":
        clean_path = log.audio_path.lstrip("/\\")
        audio_url = f"/{clean_path}"

    return TransmissionLookupOut(
        id=log.id,
        filename=log.filename,
        timestamp=log.timestamp,
        log_date=log.log_date,
        duration=log.duration or 0.0,
        audio_path=log.audio_path,
        transcript=log.transcript,
        talkgroup=log.talkgroup,
        audio_url=audio_url,
    )


@router.post("/threads/{thread_id}/stream")
async def stream_query(
    thread_id: int,
    payload: ChatPromptInput,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Execute streaming query over transcript logs within the specified time scope."""
    thread = (
        db.query(ChatThread)
        .filter(ChatThread.id == thread_id, ChatThread.user_id == current_user.id)
        .first()
    )
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    settings = get_settings()
    cfg = settings.config.chat
    agentic = bool(cfg.agentic_enabled)

    # Resolve time scope
    active_scope = payload.time_scope
    if not active_scope:
        # Fall back to thread preset
        active_scope = ChatTimeScope(
            preset=thread.time_scope_preset or "today",
            start_time=thread.start_time,
            end_time=thread.end_time,
        )

    start_time, end_time, time_desc = parse_time_scope(active_scope)

    # Legacy talkgroup filter: honored only in non-agentic mode. In agentic mode the model
    # targets talkgroups itself through tool arguments.
    talkgroups = None
    if not agentic:
        talkgroups = payload.talkgroups
        if talkgroups is None and thread.talkgroups:
            try:
                talkgroups = json.loads(thread.talkgroups)
            except json.JSONDecodeError:
                logger.warning("Thread %s has malformed talkgroups JSON; ignoring filter", thread.id)
                talkgroups = None

    # Update thread auto-title if it's currently default
    if thread.title in ("New Query", "New Intel Query") and len(payload.prompt) > 0:
        clean_title = payload.prompt.strip()[:60]
        if len(payload.prompt.strip()) > 60:
            clean_title += "..."
        thread.title = clean_title
        thread.time_scope_preset = active_scope.preset
        thread.start_time = start_time
        thread.end_time = end_time
        if talkgroups:
            thread.talkgroups = json.dumps(talkgroups)
        thread.updated_at = utcnow()

    # Save user message to database
    user_msg = ChatMessage(
        thread_id=thread.id,
        role="user",
        content=payload.prompt,
    )
    db.add(user_msg)
    db.commit()

    tool_ctx: Optional[ToolContext] = None
    if agentic:
        # Compact scope header only; the model pulls transmissions through tools.
        system_prompt = build_agent_system_prompt()
        context_text, transmissions_count = await asyncio.to_thread(
            _load_agent_context, start_time, end_time, time_desc
        )
        tool_ctx = ToolContext(scope_start=start_time, scope_end=end_time, scope_desc=time_desc)
    else:
        limit = getattr(cfg, "max_transmissions_context", 2500) or 2500
        transmissions = query_transmissions(
            db=db,
            start_time=start_time,
            end_time=end_time,
            talkgroups=talkgroups,
            limit=limit,
        )
        system_prompt = build_system_prompt()
        context_text = format_context_block(transmissions, time_desc)
        transmissions_count = len(transmissions)

    # Prepare message history (last 10 messages)
    history_messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.thread_id == thread.id, ChatMessage.id != user_msg.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(10)
        .all()
    )
    history_messages.reverse()
    formatted_history = [{"role": m.role, "content": m.content} for m in history_messages]

    meta_info = {
        "transmissions_count": transmissions_count,
        "time_desc": time_desc,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "talkgroups": talkgroups or [],
        "model": cfg.model,
        "agentic": agentic,
    }

    # Asynchronous generator to stream events and persist the assistant turn on completion
    async def response_wrapper():
        trace = AssistantTrace()
        try:
            async for chunk in stream_chat_completion(
                system_prompt=system_prompt,
                context_text=context_text,
                conversation_history=formatted_history,
                user_prompt=payload.prompt,
                meta_info=meta_info,
                tool_ctx=tool_ctx,
            ):
                if chunk.startswith("data: "):
                    try:
                        trace.consume(json.loads(chunk[6:].strip()))
                    except json.JSONDecodeError:
                        logger.warning("Skipping unparseable SSE chunk while tracing assistant turn")
                yield chunk

        finally:
            # Commit assistant message to database in isolated session
            if trace.text.strip():
                cited_ids = trace.cited_ids or extract_cited_ids(trace.text)
                try:
                    with SessionLocal() as save_db:
                        asst_msg = ChatMessage(
                            thread_id=thread_id,
                            role="assistant",
                            content=trace.text,
                            cited_log_ids=json.dumps(cited_ids) if cited_ids else None,
                            thought=trace.thought or None,
                            tool_calls=json.dumps(trace.tool_calls) if trace.tool_calls else None,
                        )
                        save_db.add(asst_msg)
                        # update thread timestamp
                        save_db.query(ChatThread).filter(ChatThread.id == thread_id).update(
                            {"updated_at": utcnow()}
                        )
                        save_db.commit()
                except Exception as ex:
                    logger.error(f"Failed to persist assistant message to database: {ex}", exc_info=True)

    return StreamingResponse(
        response_wrapper(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
