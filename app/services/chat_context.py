"""Context builder and retrieval engine for Scanner Intelligence chat."""
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from ..models.log_entry import LogEntry
from ..schemas.chat import ChatTimeScope
from ..config import get_settings


ASR_FALLIBILITY_RULES = (
    "ASR TRANSCRIPT RELIABILITY (MANDATORY):\n"
    "- Every transcript in this system was produced by an automatic speech recognition (Whisper) model running on noisy radio audio. "
    "Transcripts are NOISY PHONETIC APPROXIMATIONS, not verbatim records. They routinely contain mis-heard words, "
    "clipped or dropped syllables, hallucinated filler, wrong numbers, and garbled unit IDs, street names, and 10-codes "
    "(for example 'Duval' heard as 'do all', 'Battalion 1' heard as 'Italian one', '10-50' heard as 'ten fifty' or 'tent 50').\n"
    "- Never treat a single transcript as proof of an exact word, name, number, or address. When a phrase is implausible in context, "
    "treat it as a probable mis-transcription, say so, and give the most likely intended meaning only if surrounding transmissions support it.\n"
    "- When reporting unit IDs, addresses, plate numbers, or other precision details, qualify them as 'transcribed as' and "
    "note when the same detail is not corroborated by another transmission.\n"
    "- Flag low-confidence or conflicting details explicitly, and direct the operator to verify critical details by playing the cited [TX-<id>] audio.\n"
    "- A failed keyword match does NOT prove an event did not occur: the word may have been transcribed differently. "
    "Report absence of evidence as 'not found in transcripts', never as 'did not happen'."
)

AGENT_TOOL_RULES = (
    "TOOL USE PROTOCOL:\n"
    "You have read-only tools that query the radio transcript database. You do not have the full log in context; "
    "the context block only gives you the current time, the active time scope, and summary statistics. "
    "You MUST call tools to retrieve transmissions before making any factual claim about radio traffic.\n"
    "- search_transcripts: keyword search over transcripts. Defaults to the active time scope; pass start_time/end_time to widen or move the window.\n"
    "- get_surrounding_transmissions: pull the conversation before and after a specific [TX-<id>] to corroborate or disambiguate it.\n"
    "- get_incident_records: query incidents already classified by the pipeline (type, location, units, status).\n"
    "- get_talkgroup_activity: see which talkgroups were active and how busy they were.\n"
    "Search strategy:\n"
    "1. Because of ASR errors, a single keyword search is not sufficient. When a search returns nothing or little, retry with phonetic variants, "
    "spelled-out versus numeric forms (e.g. '10-50' and 'ten fifty', 'forty five' and '45'), partial words, and synonyms before concluding anything is absent.\n"
    "2. When a hit is ambiguous or garbled, call get_surrounding_transmissions on it and judge the exchange as a whole.\n"
    "3. If the user asks about a period outside the active time scope, set start_time/end_time explicitly (local time, ISO 8601, e.g. 2026-10-14T18:00).\n"
    "4. Keep tool calls purposeful: prefer a few targeted searches over many broad ones. Stop searching once you have enough evidence and write the answer.\n"
    "5. Only cite [TX-<id>] values that actually appeared in tool results or the context block. Never invent transmission IDs."
)


def format_tx_line(tx: LogEntry) -> Optional[str]:
    """Format one transmission as '[TX-id | date 12h [24h] | TG: name]: \"text\"'; None when it has no usable text."""
    body = ((tx.corrected_transcript or tx.transcript) or "").strip()
    if not body or body == "VAD_REJECTED":
        return None
    if tx.timestamp:
        ts_12 = tx.timestamp.strftime("%I:%M:%S %p")
        ts_24 = tx.timestamp.strftime("%H:%M:%S")
        date_str = tx.timestamp.strftime("%Y-%m-%d")
        ts_display = f"{date_str} {ts_12} [{ts_24}]"
    else:
        ts_display = "UNKNOWN TIME"
    tg = (tx.talkgroup or "N/A").strip()
    return f"[TX-{tx.id} | {ts_display} | TG: {tg}]: \"{body}\""


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

    base_prompt += f"\n\n{ASR_FALLIBILITY_RULES}"

    if custom_rules:
        base_prompt += f"\n\nUSER REGIONAL CONTEXT & RULES:\n{custom_rules}"

    return base_prompt


def build_agent_system_prompt() -> str:
    """System prompt for agentic (tool calling) mode: base analysis rules plus tool use protocol."""
    base = build_system_prompt()
    marker = "\n\nUSER REGIONAL CONTEXT & RULES:"
    if marker in base:
        head, tail = base.split(marker, 1)
        return f"{head}\n\n{AGENT_TOOL_RULES}{marker}{tail}"
    return f"{base}\n\n{AGENT_TOOL_RULES}"


def build_agent_context_block(
    db: Session, start_time: datetime, end_time: datetime, time_desc: str
) -> Tuple[str, int]:
    """Compact scope header for agentic mode: current time, scope, volume statistics, top talkgroups.

    Returns the context text and the number of transmissions in scope.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p [%H:%M:%S]")
    base_filters = [
        LogEntry.is_deleted == False,
        LogEntry.timestamp >= start_time,
        LogEntry.timestamp <= end_time,
    ]
    total, first_ts, last_ts = (
        db.query(func.count(LogEntry.id), func.min(LogEntry.timestamp), func.max(LogEntry.timestamp))
        .filter(and_(*base_filters))
        .one()
    )
    lines = [
        f"CURRENT LOCAL TIME: {now_str}",
        f"ACTIVE TIME SCOPE: {time_desc} ({start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')} local)",
        f"TRANSMISSIONS IN SCOPE: {total}",
    ]
    if not total:
        lines.append("NO RADIO TRANSMISSIONS RECORDED IN THIS TIME WINDOW.")
        return "\n".join(lines), 0

    lines.append(f"EARLIEST IN SCOPE: {first_ts.strftime('%I:%M:%S %p [%H:%M:%S]')}")
    lines.append(f"LATEST IN SCOPE: {last_ts.strftime('%I:%M:%S %p [%H:%M:%S]')}")
    top = (
        db.query(LogEntry.talkgroup, func.count(LogEntry.id).label("n"))
        .filter(and_(*base_filters))
        .group_by(LogEntry.talkgroup)
        .order_by(func.count(LogEntry.id).desc())
        .limit(10)
        .all()
    )
    if top:
        lines.append("TOP TALKGROUPS IN SCOPE: " + ", ".join(f"{(tg or 'N/A').strip()} ({n})" for tg, n in top))
    return "\n".join(lines), total


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
        line = format_tx_line(tx)
        if line:
            lines.append(line)

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


