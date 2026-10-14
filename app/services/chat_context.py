"""Context builder and retrieval engine for Scanner Intelligence chat."""
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_

from ..models.log_entry import LogEntry
from ..schemas.chat import ChatTimeScope
from ..config import get_settings


def parse_time_scope(time_scope: Optional[ChatTimeScope]) -> Tuple[datetime, datetime, str]:
    """Resolve preset or custom range into aware UTC (start_time, end_time, description)."""
    now = datetime.now(timezone.utc)
    preset = (time_scope.preset if time_scope and time_scope.preset else "today").lower().strip()

    if preset == "1h":
        start = now - timedelta(hours=1)
        end = now
        desc = "Past 1 Hour"
    elif preset == "4h":
        start = now - timedelta(hours=4)
        end = now
        desc = "Past 4 Hours"
    elif preset == "12h":
        start = now - timedelta(hours=12)
        end = now
        desc = "Past 12 Hours"
    elif preset == "yesterday":
        yesterday = now - timedelta(days=1)
        start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        desc = f"Yesterday ({start.strftime('%Y-%m-%d')})"
    elif preset == "custom" and time_scope and time_scope.start_time:
        start = time_scope.start_time
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        end = time_scope.end_time or now
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        desc = f"Custom ({start.strftime('%Y-%m-%d %H:%M')} to {end.strftime('%Y-%m-%d %H:%M')})"
    else:  # default: today
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
        desc = f"Today ({start.strftime('%Y-%m-%d')})"

    return start, end, desc


def query_transmissions(
    db: Session,
    start_time: datetime,
    end_time: datetime,
    talkgroups: Optional[List[str]] = None,
    limit: int = 2500,
) -> List[LogEntry]:
    """Retrieve indexed transmissions within the specified time window."""
    # SQLite timestamp comparisons work cleanly with ISO format strings or datetime objects
    filters = [
        LogEntry.is_deleted == False,
        LogEntry.timestamp >= start_time,
        LogEntry.timestamp <= end_time,
    ]

    if talkgroups and len(talkgroups) > 0:
        cleaned_tgs = [tg.strip() for tg in talkgroups if tg.strip()]
        if cleaned_tgs:
            filters.append(LogEntry.talkgroup.in_(cleaned_tgs))

    logs = (
        db.query(LogEntry)
        .filter(and_(*filters))
        .order_by(LogEntry.timestamp.asc())
        .limit(limit)
        .all()
    )
    return logs


def build_system_prompt() -> str:
    """Construct system prompt for scanner intelligence analysis."""
    settings = get_settings()
    custom_rules = (settings.config.chat.system_prompt_rules or "").strip()

    base_prompt = (
        "You are ScanScribe Intel, an analytical assistant for serious radio hobbyists, "
        "SDR operators, and scanner monitoring stations.\n"
        "You analyze raw, time-indexed public safety and tactical radio transmissions captured from radio systems.\n\n"
        "CRITICAL OPERATIONAL RULES:\n"
        "1. CITATIONS: Whenever stating facts, officer/firefighter actions, vehicle descriptions, or timestamps, "
        "you MUST cite the transmission ID using the exact bracket format: [TX-<id>]. "
        "Example: 'Medic 12 was dispatched to a motor vehicle crash at 14:22 [TX-4521].'\n"
        "2. ACCURACY & CAUTION: Scanner audio transcripts may contain phonetics, abbreviations, 10-codes, "
        "signal codes, or occasional transcription errors due to radio static. If information is ambiguous or incomplete, "
        "clearly note the ambiguity rather than guessing.\n"
        "3. RADIO BREVITY: Disambiguate common scanner abbreviations (e.g., '10-4', '10-50' for accident, 'signal 11', 'POV', 'RP' for reporting party) "
        "in your explanation to provide clear context.\n"
        "4. TONE: Objective, technical, and precise. Avoid sensationalism or marketing fluff."
    )

    if custom_rules:
        base_prompt += f"\n\nUSER REGIONAL CONTEXT & RULES:\n{custom_rules}"

    return base_prompt


def format_context_block(transmissions: List[LogEntry], time_desc: str) -> str:
    """Format retrieved transmissions into prompt context block."""
    if not transmissions:
        return f"TIME SCOPE: {time_desc}\nNO RADIO TRANSMISSIONS RECORDED IN THIS TIME WINDOW."

    lines = [f"TIME SCOPE: {time_desc} (Total Transmissions: {len(transmissions)}):\n---"]
    for tx in transmissions:
        ts_str = tx.timestamp.strftime("%Y-%m-%d %H:%M:%S") if tx.timestamp else "UNKNOWN"
        tg = (tx.talkgroup or "N/A").strip()
        body = (tx.transcript or "").strip()
        lines.append(f"[TX-{tx.id} | {ts_str} | TG: {tg}]: \"{body}\"")

    lines.append("---\nEND OF LOG ENTRIES.")
    return "\n".join(lines)


def extract_cited_ids(text: str) -> List[int]:
    """Parse out referenced TX IDs like [TX-1042] from generated response."""
    pattern = r"\[TX-(\d+)\]"
    matches = re.findall(pattern, text)
    ids: List[int] = []
    seen = set()
    for m in matches:
        try:
            val = int(m)
            if val not in seen:
                seen.add(val)
                ids.append(val)
        except ValueError:
            continue
    return ids
