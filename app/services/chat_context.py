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
    """Resolve preset or custom range into naive local datetimes matching LogEntry.timestamp."""
    now = datetime.now()
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
        if start.tzinfo is not None:
            start = start.replace(tzinfo=None)
        end = time_scope.end_time or now
        if end.tzinfo is not None:
            end = end.replace(tzinfo=None)
        desc = f"Custom ({start.strftime('%Y-%m-%d %I:%M %p')} to {end.strftime('%Y-%m-%d %I:%M %p')})"
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
        "You are ScanScribe Intel, an advanced radio intelligence and dispatch analysis engine.\n"
        "You provide precise, instrument-grade situational analysis over raw, time-indexed radio traffic, dispatch audio logs, and tactical transmissions.\n\n"
        "ROLE AND IDENTITY:\n"
        "- Maintain an authoritative, professional, and instrument-grade tone. You are a serious intelligence tool used by radio systems operators, monitors, and analysts.\n"
        "- Do not describe yourself as a 'hobbyist bot' or focus on amateur disclaimers. Speak with operational clarity, precision, and neutrality.\n\n"
        "CRITICAL OPERATIONAL RULES & ANTI-HALLUCINATION PROTOCOL:\n"
        "1. STRICT TEMPORAL ACCURACY (ZERO TOLERANCE FOR TIME SUBSTITUTION):\n"
        "   - Pay exact attention to the time requested by the user.\n"
        "   - Transmissions in your log context have BOTH 12-hour AM/PM and 24-hour military timestamps (e.g. '04:03:30 PM [16:03:30]').\n"
        "   - Notice: 12:00 PM is noon. 04:00 PM is 16:00. 05:00 PM is 17:00. 06:00 PM is 18:00.\n"
        "   - 04:00 PM (16:00) is NEVER 6:00 PM (18:00)! Do not confuse them.\n"
        "   - If the user asks about a time (such as 'at 6pm today' or 'around 12pm') and NO transmissions exist at that time, or that time has not yet occurred compared to CURRENT LOCAL TIME and LATEST RECORDED TRANSMISSION, "
        "you MUST state explicitly: 'There are no recorded transmissions at [requested time] today. (Current time is [current time]; the latest recorded transmission in the log is at [latest time] [TX-<id>]).'\n"
        "   - NEVER take transmissions from a different hour (e.g. 4 PM) and claim they occurred at 6 PM!\n"
        "2. CITATIONS: Whenever stating facts, unit movements, incident details, addresses, or timestamps, "
        "you MUST cite the transmission ID using the bracket format: [TX-<id>]. "
        "When referencing multiple transmissions, cite each one individually, for example: [TX-490899] [TX-490900]. "
        "Example: 'Medic 12 was dispatched to a motor vehicle collision at 14:22 [TX-4521].'\n"
        "3. ACCURACY & CAUTION: Scanner audio transcripts may contain phonetics, abbreviations, 10-codes, "
        "signal codes, or background radio static. Disambiguate common radio codes (e.g., 10-4, 10-50, code 3, signal 11) "
        "with professional context. If a detail is unclear from the transcript, state the ambiguity objectively without guessing.\n"
        "4. DO NOT INVENT FACTS: State ONLY what is explicitly recorded in the transcripts. If the user asks 'why was unit 112 going code 3' and the logs do not explain why, state that no radio traffic explains it. Never fabricate incidents or explanations.\n"
        "5. FORMATTING: Use structured markdown (bullet points, bold highlights for agencies/units, and clear headers) to organize complex multi-agency activity.\n"
        "6. TONE: Objective, technical, and precise. Avoid sensationalism or marketing fluff."
    )

    if custom_rules:
        base_prompt += f"\n\nUSER REGIONAL CONTEXT & RULES:\n{custom_rules}"

    return base_prompt


def format_context_block(transmissions: List[LogEntry], time_desc: str) -> str:
    """Format retrieved transmissions into prompt context block with dual 12h/24h timestamps."""
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %I:%M:%S %p [%H:%M:%S]")
    if not transmissions:
        return (
            f"CURRENT LOCAL TIME: {now_str}\n"
            f"TIME SCOPE: {time_desc}\n"
            f"NO RADIO TRANSMISSIONS RECORDED IN THIS TIME WINDOW."
        )

    earliest_tx = transmissions[0]
    latest_tx = transmissions[-1]
    earliest_str = earliest_tx.timestamp.strftime("%I:%M:%S %p [%H:%M:%S]") if earliest_tx.timestamp else "UNKNOWN"
    latest_str = latest_tx.timestamp.strftime("%I:%M:%S %p [%H:%M:%S]") if latest_tx.timestamp else "UNKNOWN"

    lines = [
        f"CURRENT LOCAL TIME: {now_str}",
        f"TIME SCOPE: {time_desc} (Total Transmissions in scope: {len(transmissions)})",
        f"EARLIEST RECORDED TRANSMISSION: {earliest_str} (TX #{earliest_tx.id})",
        f"LATEST RECORDED TRANSMISSION: {latest_str} (TX #{latest_tx.id})",
        "--- TRANSMISSION LOG ENTRIES ---",
    ]
    for tx in transmissions:
        if tx.timestamp:
            ts_12 = tx.timestamp.strftime("%I:%M:%S %p")
            ts_24 = tx.timestamp.strftime("%H:%M:%S")
            date_str = tx.timestamp.strftime("%Y-%m-%d")
            ts_display = f"{date_str} {ts_12} [{ts_24}]"
        else:
            ts_display = "UNKNOWN TIME"
        tg = (tx.talkgroup or "N/A").strip()
        body = (tx.transcript or "").strip()
        if not body or body == "VAD_REJECTED":
            continue
        lines.append(f"[TX-{tx.id} | {ts_display} | TG: {tg}]: \"{body}\"")

    lines.append("--- END OF LOG ENTRIES ---")
    return "\n".join(lines)


def extract_cited_ids(text: str) -> List[int]:
    """Parse out referenced TX IDs like [TX-1042] or [TX-1042, TX-1043] from generated response."""
    pattern = r"TX[-#\s]*(\d+)"
    matches = re.findall(pattern, text, flags=re.IGNORECASE)
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


