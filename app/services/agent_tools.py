"""Read-only agent tools for Scanner Intelligence tool calling.

Every tool is strictly read-only, bounded by hard row limits, and filters on indexed
columns (LogEntry.timestamp, Event.updated_at) so that live ingest on the shared
SQLite WAL database is never starved. Tool bodies are synchronous SQLAlchemy code and
are always dispatched through ``asyncio.to_thread`` with a dedicated session.
"""
import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Literal, Optional, Type

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models.event import EntityObservation, Event, EventTranscriptLink
from ..models.log_entry import LogEntry
from .chat_context import format_tx_line

logger = logging.getLogger(__name__)

MAX_QUERY_TERMS = 8
MAX_TOOL_RESULT_CHARS = 24000
MAX_SURROUNDING_ROWS = 80
MAX_LINKED_TX_PER_EVENT = 6
MAX_TALKGROUP_ROWS = 40


class ToolArgumentError(ValueError):
    """Raised when tool arguments are syntactically valid but semantically unusable."""


@dataclass
class ToolContext:
    """Per-request context shared with every tool execution (naive local datetimes)."""

    scope_start: Optional[datetime] = None
    scope_end: Optional[datetime] = None
    scope_desc: str = "Unscoped"
    is_scoped: bool = False

    def __post_init__(self):
        if self.scope_start is not None and self.scope_end is not None and not self.is_scoped:
            self.is_scoped = True


@dataclass
class ToolResult:
    """Outcome of a tool run: text for the model plus a compact summary for the UI."""

    content: str
    summary: str
    count: int = 0
    is_error: bool = False
    cited_ids: List[int] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Argument models
# --------------------------------------------------------------------------- #


class ScopeTimeRangeArgs(BaseModel):
    start_time: Optional[str] = Field(
        default=None,
        description="Explicit start datetime in ISO 8601 format (e.g. '2026-10-16T14:00:00') based on CURRENT LOCAL TIME.",
    )
    end_time: Optional[str] = Field(
        default=None,
        description="Explicit end datetime in ISO 8601 format (e.g. '2026-10-16T16:00:00') based on CURRENT LOCAL TIME.",
    )
    time_expression: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Natural language time description from user prompt, e.g. 'today around 3pm', 'past 2 hours', 'yesterday between 2pm and 4pm'.",
    )
    preset: Optional[Literal["1h", "2h", "4h", "8h", "12h", "today", "yesterday"]] = Field(
        default=None,
        description="Standard time window preset matching the user prompt.",
    )
    hours: Optional[int] = Field(
        default=None,
        ge=1,
        le=168,
        description="Look back this many hours from CURRENT LOCAL TIME.",
    )


class SearchTranscriptsArgs(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    match: Literal["any", "all"] = "any"
    talkgroup: Optional[str] = Field(default=None, max_length=50)
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=100)


class SurroundingArgs(BaseModel):
    tx_id: int = Field(..., ge=1)
    window_seconds: int = Field(default=180, ge=10, le=900)
    same_talkgroup_only: bool = False


class IncidentArgs(BaseModel):
    query: Optional[str] = Field(default=None, max_length=200)
    status: Literal["open", "closed", "any"] = "any"
    hours: int = Field(default=24, ge=1, le=720)
    limit: int = Field(default=20, ge=1, le=50)


class TalkgroupActivityArgs(BaseModel):
    query: Optional[str] = Field(default=None, max_length=50)
    hours: int = Field(default=24, ge=1, le=720)


class LookupNerEntitiesArgs(BaseModel):
    query: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Optional entity name or substring to match against canonical/raw text, e.g. '112', 'walton', 'Engine 4', '10-50'.",
    )
    label: Optional[Literal["UNIT", "LOC", "ADDRESS", "EVT_TYPE", "STATUS", "TIME"]] = Field(
        default=None,
        description="Optional filter by NER entity label: UNIT (units/responders), LOC/ADDRESS (locations/streets), EVT_TYPE (call type), STATUS (tactical status).",
    )
    talkgroup: Optional[str] = Field(default=None, max_length=50, description="Optional talkgroup substring filter.")
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    limit: int = Field(default=30, ge=1, le=60, description="Max matching entity observations or top entities to return (default 30).")


class ScopeIncidentAudioArgs(BaseModel):
    incident_title: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="Concise descriptive title of the incident, e.g. 'Pursuit & Collision on I-95' or 'Structure Fire at 500 Oak St'.",
    )
    tx_ids: List[int] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Chronological list of transmission IDs belonging to this incident timeline.",
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _parse_local_dt(raw: Optional[str], field_name: str) -> Optional[datetime]:
    """Parse ISO 8601 text to naive local time (matching LogEntry.timestamp storage)."""
    if raw is None or not str(raw).strip():
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00"))
    except ValueError as ex:
        raise ToolArgumentError(
            f"{field_name} '{raw}' is not valid ISO 8601 (expected e.g. 2026-10-14T18:00)."
        ) from ex
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _utc_naive_to_local(dt: Optional[datetime]) -> Optional[datetime]:
    """Event timestamps are stored as naive UTC wall time; convert for display."""
    if dt is None:
        return None
    aware = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    return aware.astimezone().replace(tzinfo=None)


def _local_to_utc_naive(dt: datetime) -> datetime:
    """Convert naive local datetime to naive UTC datetime for querying UTC timestamp columns."""
    local_tz = datetime.now().astimezone().tzinfo
    aware = dt.replace(tzinfo=local_tz) if dt.tzinfo is None else dt
    return aware.astimezone(timezone.utc).replace(tzinfo=None)


def _terms(query: str) -> List[str]:
    parts = [p.strip() for p in query.replace(",", " ").split() if p.strip()]
    if not parts:
        raise ToolArgumentError("query must contain at least one search term.")
    return parts[:MAX_QUERY_TERMS]


def _join_capped(header: List[str], rows: List[str]) -> str:
    """Join header and rows, truncating rows to MAX_TOOL_RESULT_CHARS with an explicit notice."""
    out: List[str] = list(header)
    used = sum(len(h) + 1 for h in header)
    for idx, row in enumerate(rows):
        if used + len(row) + 1 > MAX_TOOL_RESULT_CHARS:
            out.append(f"[TRUNCATED: {len(rows) - idx} more rows omitted; narrow the query or time window]")
            break
        out.append(row)
        used += len(row) + 1
    return "\n".join(out)


def _window_label(start: datetime, end: datetime) -> str:
    return f"{start.strftime('%Y-%m-%d %H:%M')} to {end.strftime('%Y-%m-%d %H:%M')} local"


def _tx_filters(start: datetime, end: datetime) -> list:
    return [
        LogEntry.is_deleted == False,  # noqa: E712 - SQLAlchemy expression
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
    ]


# --------------------------------------------------------------------------- #
# Executors
# --------------------------------------------------------------------------- #


def execute_scope_time_range(db: Session, ctx: ToolContext, args: ScopeTimeRangeArgs) -> ToolResult:
    now = datetime.now()
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    desc: str = ""

    if args.start_time:
        start = _parse_local_dt(args.start_time, "start_time")
        end = _parse_local_dt(args.end_time, "end_time") or now
        desc = args.time_expression or f"{start.strftime('%Y-%m-%d %I:%M %p')} to {end.strftime('%I:%M %p')}"
    elif args.preset:
        p = args.preset.lower().strip()
        if p == "1h":
            start, end, desc = now - timedelta(hours=1), now, "Past 1 Hour"
        elif p == "2h":
            start, end, desc = now - timedelta(hours=2), now, "Past 2 Hours"
        elif p == "4h":
            start, end, desc = now - timedelta(hours=4), now, "Past 4 Hours"
        elif p == "8h":
            start, end, desc = now - timedelta(hours=8), now, "Past 8 Hours"
        elif p == "12h":
            start, end, desc = now - timedelta(hours=12), now, "Past 12 Hours"
        elif p == "yesterday":
            yesterday = now - timedelta(days=1)
            start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
            desc = f"Yesterday ({start.strftime('%Y-%m-%d')})"
        else:  # today
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
            desc = f"Today ({start.strftime('%Y-%m-%d')})"
    elif args.hours:
        start = now - timedelta(hours=args.hours)
        end = now
        desc = f"Past {args.hours} Hours"
    elif args.time_expression:
        expr = args.time_expression.lower().strip()
        if "yesterday" in expr:
            yesterday = now - timedelta(days=1)
            start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
            desc = f"Yesterday ({start.strftime('%Y-%m-%d')})"
        elif "today" in expr:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
            desc = f"Today ({start.strftime('%Y-%m-%d')})"
        else:
            m = re.search(r'(?:past|last)\s+(\d+)\s*hour', expr)
            if m:
                h = int(m.group(1))
                start = now - timedelta(hours=min(h, 168))
                end = now
                desc = f"Past {h} Hours"

    if start is None or end is None:
        raise ToolArgumentError(
            "Could not determine time scope. Please provide start_time/end_time in ISO 8601 (e.g. 2026-10-16T14:00:00), "
            "preset ('today', 'yesterday', '1h', '4h'), or hours."
        )

    if start > end:
        start, end = end, start

    max_delta = timedelta(days=7)
    if (end - start) > max_delta:
        raise ToolArgumentError("Requested time window exceeds maximum limit of 7 days. Please narrow the time window.")

    # Update context
    ctx.scope_start = start
    ctx.scope_end = end
    ctx.scope_desc = desc
    ctx.is_scoped = True

    # Query stats in this window
    filters = [
        LogEntry.is_deleted == False,
        LogEntry.timestamp >= start,
        LogEntry.timestamp <= end,
    ]
    total, first_ts, last_ts = (
        db.query(func.count(LogEntry.id), func.min(LogEntry.timestamp), func.max(LogEntry.timestamp))
        .filter(and_(*filters))
        .one()
    )

    out = [
        f"TIME SCOPE ESTABLISHED: {desc}",
        f"Window: {start.strftime('%Y-%m-%d %I:%M:%S %p')} to {end.strftime('%Y-%m-%d %I:%M:%S %p')} local [{start.strftime('%H:%M:%S')} to {end.strftime('%H:%M:%S')}]",
        f"Transmissions recorded in scope: {total}",
    ]

    if total == 0:
        out.append("NOTE: Zero transmissions were recorded during this exact time window in local storage.")
        earliest_db, latest_db = (
            db.query(func.min(LogEntry.timestamp), func.max(LogEntry.timestamp))
            .filter(LogEntry.is_deleted == False)
            .one()
        )
        if earliest_db and latest_db:
            out.append(f"Available database logs exist between {earliest_db.strftime('%Y-%m-%d %I:%M %p')} and {latest_db.strftime('%Y-%m-%d %I:%M %p')}.")
    else:
        out.append(f"Earliest in scope: {first_ts.strftime('%I:%M:%S %p [%H:%M:%S]') if first_ts else 'N/A'}")
        out.append(f"Latest in scope: {last_ts.strftime('%I:%M:%S %p [%H:%M:%S]') if last_ts else 'N/A'}")
        top = (
            db.query(LogEntry.talkgroup, func.count(LogEntry.id).label("n"))
            .filter(and_(*filters))
            .group_by(LogEntry.talkgroup)
            .order_by(func.count(LogEntry.id).desc())
            .limit(5)
            .all()
        )
        if top:
            out.append("Active talkgroups: " + ", ".join(f"{(tg or 'N/A').strip()} ({n})" for tg, n in top))

    out.append("Scope is locked. Proceed with targeted search_transcripts or lookup_ner_entities within this window.")

    summary = f"Scoped {desc}: {total} TXs"
    return ToolResult(content="\n".join(out), summary=summary, count=total)


def execute_search_transcripts(db: Session, ctx: ToolContext, args: SearchTranscriptsArgs) -> ToolResult:
    start = _parse_local_dt(args.start_time, "start_time") or ctx.scope_start
    end = _parse_local_dt(args.end_time, "end_time") or ctx.scope_end
    if start is None or end is None or (not ctx.is_scoped and not args.start_time):
        return ToolResult(
            content=(
                "REFUSED: No active time scope. You must call 'scope_time_range' first to establish a time window "
                "or provide explicit start_time/end_time before searching transcripts."
            ),
            summary="Refused: Unscoped query",
            is_error=True,
        )
    if end < start:
        raise ToolArgumentError("end_time is earlier than start_time.")

    clauses = []
    for term in _terms(args.query):
        pattern = f"%{_escape_like(term)}%"
        clauses.append(
            or_(
                LogEntry.transcript.ilike(pattern, escape="\\"),
                LogEntry.corrected_transcript.ilike(pattern, escape="\\"),
            )
        )
    text_filter = and_(*clauses) if args.match == "all" else or_(*clauses)

    filters = _tx_filters(start, end) + [text_filter, LogEntry.transcript != "VAD_REJECTED"]
    if args.talkgroup and args.talkgroup.strip():
        filters.append(LogEntry.talkgroup.ilike(f"%{_escape_like(args.talkgroup.strip())}%", escape="\\"))

    total = db.query(func.count(LogEntry.id)).filter(and_(*filters)).scalar() or 0
    rows = (
        db.query(LogEntry)
        .filter(and_(*filters))
        .order_by(LogEntry.timestamp.desc())
        .limit(args.limit)
        .all()
    )
    rows.reverse()
    lines = [line for line in (format_tx_line(r) for r in rows) if line]

    header = [
        f"search_transcripts query='{args.query}' match={args.match}"
        + (f" talkgroup~'{args.talkgroup}'" if args.talkgroup else "")
        + f" window={_window_label(start, end)}",
        f"MATCHES: {total} total, showing {len(lines)} (chronological, most recent {args.limit} max)",
    ]
    if not lines:
        header.append(
            "NO MATCHING TRANSMISSIONS. This does not prove the event did not occur: ASR may have transcribed "
            "the words differently. Try phonetic variants, numeric versus spelled-out forms, or a wider window."
        )
    summary = f"{total} match(es)" + (f", showing {len(lines)}" if total > len(lines) else "")
    return ToolResult(
        content=_join_capped(header, lines),
        summary=summary,
        count=total,
        cited_ids=[r.id for r in rows],
    )


def execute_get_surrounding_transmissions(db: Session, ctx: ToolContext, args: SurroundingArgs) -> ToolResult:
    target = (
        db.query(LogEntry)
        .filter(LogEntry.id == args.tx_id, LogEntry.is_deleted == False)  # noqa: E712
        .first()
    )
    if target is None or target.timestamp is None:
        raise ToolArgumentError(f"Transmission TX-{args.tx_id} was not found.")

    delta = timedelta(seconds=args.window_seconds)
    filters = _tx_filters(target.timestamp - delta, target.timestamp + delta)
    if args.same_talkgroup_only and target.talkgroup:
        filters.append(LogEntry.talkgroup == target.talkgroup)

    rows = (
        db.query(LogEntry)
        .filter(and_(*filters))
        .order_by(LogEntry.timestamp.asc(), LogEntry.id.asc())
        .limit(MAX_SURROUNDING_ROWS)
        .all()
    )
    lines: List[str] = []
    for r in rows:
        line = format_tx_line(r)
        if not line:
            continue
        lines.append((">> " if r.id == target.id else "   ") + line)

    header = [
        f"get_surrounding_transmissions tx=TX-{args.tx_id} window=+/-{args.window_seconds}s"
        + (f" talkgroup={target.talkgroup}" if args.same_talkgroup_only else " all talkgroups"),
        "The line marked '>>' is the requested transmission.",
        f"RETURNED: {len(lines)} transmission(s)",
    ]
    return ToolResult(
        content=_join_capped(header, lines),
        summary=f"{len(lines)} transmission(s) around TX-{args.tx_id}",
        count=len(lines),
        cited_ids=[r.id for r in rows],
    )


def execute_get_incident_records(db: Session, ctx: ToolContext, args: IncidentArgs) -> ToolResult:
    cutoff_utc = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=args.hours)
    filters = [Event.updated_at >= cutoff_utc]
    if args.status != "any":
        filters.append(Event.status == args.status)
    if args.query and args.query.strip():
        clauses = []
        for term in _terms(args.query):
            pattern = f"%{_escape_like(term)}%"
            clauses.append(
                or_(
                    Event.event_type.ilike(pattern, escape="\\"),
                    Event.location.ilike(pattern, escape="\\"),
                    Event.resolved_address.ilike(pattern, escape="\\"),
                    Event.summary.ilike(pattern, escape="\\"),
                    Event.original_transcription.ilike(pattern, escape="\\"),
                )
            )
        filters.append(or_(*clauses))

    events = (
        db.query(Event)
        .filter(and_(*filters))
        .order_by(Event.updated_at.desc())
        .limit(args.limit)
        .all()
    )

    links_by_event: Dict[int, List[int]] = {}
    if events:
        link_rows = (
            db.query(EventTranscriptLink.event_id, EventTranscriptLink.log_entry_id)
            .filter(EventTranscriptLink.event_id.in_([e.id for e in events]))
            .order_by(EventTranscriptLink.log_entry_id.asc())
            .all()
        )
        for event_id, log_id in link_rows:
            bucket = links_by_event.setdefault(event_id, [])
            if len(bucket) < MAX_LINKED_TX_PER_EVENT:
                bucket.append(log_id)

    lines: List[str] = []
    cited: List[int] = []
    for e in events:
        updated = _utc_naive_to_local(e.updated_at)
        linked = links_by_event.get(e.id, [])
        cited.extend(linked)
        parts = [
            f"[EVENT {e.event_id} | status: {e.status} | updated: {updated.strftime('%Y-%m-%d %H:%M') if updated else 'unknown'} local]",
            f"type: {e.event_type or 'unknown'}",
            f"location: {e.resolved_address or e.location or 'unknown'}",
            f"units: {', '.join(e.units_list) if e.units_list else 'none recorded'}",
        ]
        if e.status_detail:
            parts.append(f"status detail: {e.status_detail}")
        if e.summary:
            parts.append(f"summary: {e.summary.strip()[:600]}")
        if linked:
            parts.append("linked transmissions: " + ", ".join(f"[TX-{i}]" for i in linked))
        lines.append(" | ".join(parts))

    header = [
        f"get_incident_records query='{args.query or ''}' status={args.status} last {args.hours}h",
        "Incident fields are produced by an automated NER/LLM pipeline over ASR transcripts and may be wrong; verify against linked transmissions.",
        f"RETURNED: {len(lines)} incident(s)",
    ]
    if not lines:
        header.append("NO MATCHING INCIDENTS.")
    return ToolResult(
        content=_join_capped(header, lines),
        summary=f"{len(lines)} incident(s)",
        count=len(lines),
        cited_ids=cited,
    )


def execute_get_talkgroup_activity(db: Session, ctx: ToolContext, args: TalkgroupActivityArgs) -> ToolResult:
    if ctx.is_scoped and ctx.scope_start and ctx.scope_end:
        start = ctx.scope_start
        end = ctx.scope_end
    else:
        end = datetime.now()
        start = end - timedelta(hours=args.hours)
    filters = _tx_filters(start, end)
    if args.query and args.query.strip():
        filters.append(LogEntry.talkgroup.ilike(f"%{_escape_like(args.query.strip())}%", escape="\\"))

    rows = (
        db.query(
            LogEntry.talkgroup,
            func.count(LogEntry.id),
            func.min(LogEntry.timestamp),
            func.max(LogEntry.timestamp),
        )
        .filter(and_(*filters))
        .group_by(LogEntry.talkgroup)
        .order_by(func.count(LogEntry.id).desc())
        .limit(MAX_TALKGROUP_ROWS)
        .all()
    )
    lines = [
        f"{(tg or 'N/A').strip()}: {n} transmission(s), first {first.strftime('%m-%d %H:%M')}, last {last.strftime('%m-%d %H:%M')}"
        for tg, n, first, last in rows
        if first and last
    ]
    header = [
        f"get_talkgroup_activity query='{args.query or ''}' window={_window_label(start, end)}",
        f"TALKGROUPS: {len(lines)} (busiest first)",
    ]
    if not lines:
        header.append("NO TALKGROUP ACTIVITY IN WINDOW.")
    return ToolResult(content=_join_capped(header, lines), summary=f"{len(lines)} talkgroup(s)", count=len(lines))


def execute_lookup_ner_entities(db: Session, ctx: ToolContext, args: LookupNerEntitiesArgs) -> ToolResult:
    start_dt = _parse_local_dt(args.start_time, "start_time") or ctx.scope_start
    end_dt = _parse_local_dt(args.end_time, "end_time") or ctx.scope_end
    if start_dt is None or end_dt is None or (not ctx.is_scoped and not args.start_time):
        return ToolResult(
            content=(
                "REFUSED: No active time scope. You must call 'scope_time_range' first to establish a time window "
                "or provide explicit start_time/end_time before querying named entities."
            ),
            summary="Refused: Unscoped query",
            is_error=True,
        )
    if start_dt > end_dt:
        raise ToolArgumentError(f"start_time ({start_dt}) cannot be after end_time ({end_dt}).")

    filters = [
        EntityObservation.ts >= start_dt,
        EntityObservation.ts <= end_dt,
    ]
    if args.label:
        filters.append(EntityObservation.label == args.label.strip().upper())
    if args.talkgroup and args.talkgroup.strip():
        filters.append(EntityObservation.talkgroup.ilike(f"%{_escape_like(args.talkgroup.strip())}%", escape="\\"))

    # Case 1: Specific query (e.g. Unit 112 timeline or 1155 Walton Dr history)
    if args.query and args.query.strip():
        terms = _terms(args.query)
        q_clauses = []
        for t in terms:
            pat = f"%{_escape_like(t)}%"
            q_clauses.append(
                or_(
                    EntityObservation.canonical.ilike(pat, escape="\\"),
                    EntityObservation.raw.ilike(pat, escape="\\"),
                )
            )
        filters.append(or_(*q_clauses))

        results = (
            db.query(EntityObservation, LogEntry)
            .outerjoin(LogEntry, EntityObservation.log_entry_id == LogEntry.id)
            .filter(and_(*filters))
            .order_by(EntityObservation.ts.asc(), EntityObservation.id.asc())
            .limit(args.limit)
            .all()
        )

        header = [
            f"lookup_ner_entities query='{args.query}'"
            + (f" label={args.label}" if args.label else "")
            + (f" talkgroup={args.talkgroup}" if args.talkgroup else ""),
            f"TIME WINDOW: {start_dt.strftime('%Y-%m-%d %I:%M %p')} to {end_dt.strftime('%Y-%m-%d %I:%M %p')}",
            f"RETURNED: {len(results)} observation(s)",
        ]

        if not results:
            lines = [
                f"No NER entity observations found matching '{args.query}' in this time window.",
                "Note: Automatic NER extraction depends on speech recognition clarity. If an entity was mentioned "
                "with non-standard phrasing or RF noise, try search_transcripts with phonetic variations.",
            ]
            return ToolResult(
                content=_join_capped(header, lines),
                summary=f"0 entities matching '{args.query}'",
                count=0,
            )

        lines: List[str] = []
        cited_ids: List[int] = []
        for obs, log in results:
            local_ts = _utc_naive_to_local(obs.ts) or obs.ts
            ts_12 = local_ts.strftime("%I:%M:%S %p")
            ts_24 = local_ts.strftime("%H:%M:%S")
            date_str = local_ts.strftime("%Y-%m-%d")
            ts_display = f"{date_str} {ts_12} [{ts_24}]"
            tg = obs.talkgroup or (log.talkgroup if log else "N/A") or "N/A"
            tx_id_str = f"TX-{obs.log_entry_id}" if obs.log_entry_id else "NO-TX"
            if obs.log_entry_id:
                cited_ids.append(obs.log_entry_id)

            transcript_snippet = ""
            if log:
                tx_text = ((log.corrected_transcript or log.transcript) or "").strip()
                if tx_text and tx_text != "VAD_REJECTED":
                    transcript_snippet = f' - "{tx_text}"'

            lines.append(
                f"[{tx_id_str} | {ts_display} | TG: {tg}] {obs.label}: '{obs.canonical}' (raw: '{obs.raw}'){transcript_snippet}"
            )

        summary = f"{len(results)} entity observation(s) for '{args.query}'"
        return ToolResult(
            content=_join_capped(header, lines),
            summary=summary,
            count=len(results),
            cited_ids=cited_ids,
        )

    # Case 2: General entity frequency aggregation
    agg_query = (
        db.query(
            EntityObservation.canonical,
            EntityObservation.label,
            func.count(EntityObservation.id).label("freq"),
            func.min(EntityObservation.ts).label("first_seen"),
            func.max(EntityObservation.ts).label("last_seen"),
            func.max(EntityObservation.log_entry_id).label("sample_tx_id"),
        )
        .filter(and_(*filters))
        .group_by(EntityObservation.canonical, EntityObservation.label)
        .order_by(func.count(EntityObservation.id).desc())
        .limit(args.limit)
        .all()
    )

    header = [
        f"lookup_ner_entities aggregation"
        + (f" label={args.label}" if args.label else " all labels")
        + (f" talkgroup={args.talkgroup}" if args.talkgroup else ""),
        f"TIME WINDOW: {start_dt.strftime('%Y-%m-%d %I:%M %p')} to {end_dt.strftime('%Y-%m-%d %I:%M %p')}",
        f"RETURNED: {len(agg_query)} distinct entity group(s)",
    ]

    lines = []
    cited_ids = []
    for canonical, label, freq, first_seen, last_seen, sample_tx in agg_query:
        first_local = _utc_naive_to_local(first_seen)
        last_local = _utc_naive_to_local(last_seen)
        first_str = first_local.strftime("%I:%M %p") if first_local else "N/A"
        last_str = last_local.strftime("%I:%M %p") if last_local else "N/A"
        tx_cite = f" [TX-{sample_tx}]" if sample_tx else ""
        if sample_tx:
            cited_ids.append(sample_tx)
        lines.append(
            f"- [{label}] '{canonical}': {freq} mention(s) between {first_str} and {last_str}{tx_cite}"
        )

    summary = f"{len(agg_query)} entity group(s)"
    return ToolResult(
        content=_join_capped(header, lines),
        summary=summary,
        count=len(agg_query),
        cited_ids=cited_ids,
    )


def execute_scope_incident_audio(
    db: Session, ctx: ToolContext, args: ScopeIncidentAudioArgs
) -> ToolResult:
    """Stage and verify a chronological playlist of transmission IDs for an incident into the operator audio deck."""
    if not args.tx_ids:
        raise ToolArgumentError("At least one transmission ID is required to scope incident audio.")

    seen = set()
    deduped_ids = []
    for tid in args.tx_ids:
        if tid not in seen and tid > 0:
            seen.add(tid)
            deduped_ids.append(tid)

    if not deduped_ids:
        raise ToolArgumentError("No valid positive transmission IDs provided.")

    records = (
        db.query(LogEntry)
        .filter(LogEntry.id.in_(deduped_ids), LogEntry.is_deleted.is_(False))
        .order_by(LogEntry.timestamp.asc(), LogEntry.id.asc())
        .all()
    )

    if not records:
        return ToolResult(
            content=f"None of the provided transmission IDs ({deduped_ids}) exist or remain active in the database.",
            summary=f"No matching transmissions found for '{args.incident_title}'",
            count=0,
            is_error=True,
        )

    lines = []
    ordered_ids = []
    for r in records:
        ordered_ids.append(r.id)
        formatted = format_tx_line(r)
        if formatted:
            lines.append(f"- {formatted}")
        else:
            ts_str = r.timestamp.strftime("%Y-%m-%d %H:%M:%S") if r.timestamp else "UNKNOWN"
            lines.append(f"- [TX-{r.id} | {ts_str} | TG: {r.talkgroup or 'N/A'}]")

    header = [
        f"INCIDENT AUDIO SCOPE STAGED: '{args.incident_title}'",
        f"Total {len(ordered_ids)} transmissions ordered chronologically for playback in the Audio Deck.",
        "Timeline Transmissions:",
    ]
    footer = f"\nAction Button for Response: [⚡ Scope Incident Audio ({len(ordered_ids)} Transmissions)](scope:tx:{','.join(map(str, ordered_ids))})"

    return ToolResult(
        content=_join_capped(header, lines) + footer,
        summary=f"Scoped {len(ordered_ids)} incident audio clips for '{args.incident_title}'",
        count=len(ordered_ids),
        cited_ids=ordered_ids,
    )


# --------------------------------------------------------------------------- #
# Registry and provider declarations
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: Type[BaseModel]
    parameters: Dict[str, Any]
    executor: Callable[[Session, ToolContext, Any], ToolResult]


_TIME_PARAM = {
    "type": "string",
    "description": "Local time, ISO 8601 (e.g. 2026-10-14T18:00). Overrides the active time scope.",
}

TOOL_REGISTRY: Dict[str, ToolSpec] = {
    "scope_time_range": ToolSpec(
        name="scope_time_range",
        description=(
            "MANDATORY FIRST STEP when the operator provides a time, date, or relative window. "
            "Resolves and locks the active time scope for the conversation, verifies how many radio transmissions "
            "exist in that window, and identifies active talkgroups. "
            "You MUST call this tool before calling search_transcripts or lookup_ner_entities. "
            "If the operator prompt did NOT specify any time or date, DO NOT call this tool; instead refuse output."
        ),
        args_model=ScopeTimeRangeArgs,
        parameters={
            "type": "object",
            "properties": {
                "start_time": _TIME_PARAM,
                "end_time": _TIME_PARAM,
                "time_expression": {
                    "type": "string",
                    "description": "Natural language time expression from user prompt, e.g. 'today around 3pm', 'yesterday between 2pm and 4pm', 'past 2 hours'.",
                },
                "preset": {
                    "type": "string",
                    "enum": ["1h", "2h", "4h", "8h", "12h", "today", "yesterday"],
                    "description": "Optional preset time window matching the prompt.",
                },
                "hours": {
                    "type": "integer",
                    "description": "Optional hours lookback from current time (1 to 168).",
                },
            },
        },
        executor=execute_scope_time_range,
    ),
    "search_transcripts": ToolSpec(
        name="search_transcripts",
        description=(
            "Keyword search over ASR radio transcripts. Space-separated terms are matched case-insensitively as "
            "substrings. Defaults to the active time scope. Transcripts are noisy, so retry with phonetic and "
            "numeric/spelled variants when results are empty or thin."
        ),
        args_model=SearchTranscriptsArgs,
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search terms separated by spaces."},
                "match": {
                    "type": "string",
                    "enum": ["any", "all"],
                    "description": "'any' (default) matches transcripts containing at least one term; 'all' requires every term.",
                },
                "talkgroup": {"type": "string", "description": "Optional talkgroup name substring filter."},
                "start_time": _TIME_PARAM,
                "end_time": _TIME_PARAM,
                "limit": {"type": "integer", "description": "Max rows to return, 1-100 (default 50)."},
            },
            "required": ["query"],
        },
        executor=execute_search_transcripts,
    ),
    "get_surrounding_transmissions": ToolSpec(
        name="get_surrounding_transmissions",
        description=(
            "Fetch transmissions immediately before and after a specific transmission ID to see the full dispatch "
            "exchange and corroborate or disambiguate a garbled transcript."
        ),
        args_model=SurroundingArgs,
        parameters={
            "type": "object",
            "properties": {
                "tx_id": {"type": "integer", "description": "Transmission ID (the number in [TX-<id>])."},
                "window_seconds": {"type": "integer", "description": "Seconds before and after, 10-900 (default 180)."},
                "same_talkgroup_only": {"type": "boolean", "description": "Restrict to the same talkgroup (default false)."},
            },
            "required": ["tx_id"],
        },
        executor=execute_get_surrounding_transmissions,
    ),
    "get_incident_records": ToolSpec(
        name="get_incident_records",
        description=(
            "Query incidents classified by the automated pipeline: type, location, units, status, summary, and "
            "linked transmission IDs. Pipeline output may contain errors; verify against linked transmissions."
        ),
        args_model=IncidentArgs,
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Optional terms matched against type, location, and summary."},
                "status": {"type": "string", "enum": ["open", "closed", "any"], "description": "Incident status (default any)."},
                "hours": {"type": "integer", "description": "Look back this many hours from now, 1-720 (default 24)."},
                "limit": {"type": "integer", "description": "Max incidents, 1-50 (default 20)."},
            },
        },
        executor=execute_get_incident_records,
    ),
    "get_talkgroup_activity": ToolSpec(
        name="get_talkgroup_activity",
        description="Summarize which talkgroups were active and how many transmissions each carried, without loading transcripts.",
        args_model=TalkgroupActivityArgs,
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Optional talkgroup name substring filter."},
                "hours": {"type": "integer", "description": "Look back this many hours from now, 1-720 (default 24)."},
            },
        },
        executor=execute_get_talkgroup_activity,
    ),
    "lookup_ner_entities": ToolSpec(
        name="lookup_ner_entities",
        description=(
            "Query extracted named entities (UNIT, LOC, ADDRESS, EVT_TYPE, STATUS, TIME) from the incident NER pipeline. "
            "Use this as the PRIMARY tool when asked about specific emergency units (e.g. 'What did unit 112 do?'), "
            "street addresses or locations (e.g. 'What happened at 1155 walton dr?'), or to see an aggregated summary "
            "of active units or incident types in a time window."
        ),
        args_model=LookupNerEntitiesArgs,
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Optional unit name, address, or incident term to search (e.g. '112', 'walton', 'Engine 4').",
                },
                "label": {
                    "type": "string",
                    "enum": ["UNIT", "LOC", "ADDRESS", "EVT_TYPE", "STATUS", "TIME"],
                    "description": "Optional filter by NER entity label.",
                },
                "talkgroup": {"type": "string", "description": "Optional talkgroup substring filter."},
                "start_time": _TIME_PARAM,
                "end_time": _TIME_PARAM,
                "limit": {"type": "integer", "description": "Max rows to return, 1-60 (default 30)."},
            },
        },
        executor=execute_lookup_ner_entities,
    ),
    "scope_incident_audio": ToolSpec(
        name="scope_incident_audio",
        description=(
            "Stage and verify a chronological playlist of transmission IDs for an incident into the operator audio deck. "
            "Validates that the transmission IDs exist, sorts them chronologically by timestamp, and confirms them for continuous playback."
        ),
        args_model=ScopeIncidentAudioArgs,
        parameters={
            "type": "object",
            "properties": {
                "incident_title": {
                    "type": "string",
                    "description": "Descriptive title of the incident, e.g. 'Pursuit & Collision on I-95' or 'Structure Fire at 500 Oak St'.",
                },
                "tx_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of transmission IDs ([TX-<id>]) belonging to this incident timeline in chronological order.",
                },
            },
            "required": ["incident_title", "tx_ids"],
        },
        executor=execute_scope_incident_audio,
    ),
}


def openai_tool_declarations() -> List[Dict[str, Any]]:
    """Tool declarations in OpenAI / OpenRouter function calling format."""
    return [
        {
            "type": "function",
            "function": {"name": s.name, "description": s.description, "parameters": s.parameters},
        }
        for s in TOOL_REGISTRY.values()
    ]


def gemini_tool_declarations() -> List[Dict[str, Any]]:
    """Tool declarations in Gemini functionDeclarations format."""
    return [
        {
            "functionDeclarations": [
                {"name": s.name, "description": s.description, "parameters": s.parameters}
                for s in TOOL_REGISTRY.values()
            ]
        }
    ]


def _run_tool_sync(name: str, raw_args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        return ToolResult(
            content=f"Unknown tool '{name}'. Available tools: {', '.join(TOOL_REGISTRY)}.",
            summary="Unknown tool",
            is_error=True,
        )
    try:
        args = spec.args_model(**(raw_args or {}))
    except ValidationError as ex:
        msg = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in ex.errors())
        return ToolResult(content=f"Invalid arguments for {name}: {msg}", summary="Invalid arguments", is_error=True)

    try:
        with SessionLocal() as db:
            return spec.executor(db, ctx, args)
    except ToolArgumentError as ex:
        return ToolResult(content=f"Tool {name} rejected its arguments: {ex}", summary=str(ex)[:120], is_error=True)
    except SQLAlchemyError as ex:
        logger.error("Agent tool %s database error: %s", name, ex, exc_info=True)
        return ToolResult(
            content=f"Tool {name} failed due to a database error; try again or narrow the query.",
            summary="Database error",
            is_error=True,
        )


async def execute_tool(name: str, raw_args: Dict[str, Any], ctx: ToolContext) -> tuple[ToolResult, int]:
    """Run a tool off the event loop; returns the result and elapsed milliseconds."""
    started = time.perf_counter()
    result = await asyncio.to_thread(_run_tool_sync, name, raw_args, ctx)
    return result, int((time.perf_counter() - started) * 1000)
