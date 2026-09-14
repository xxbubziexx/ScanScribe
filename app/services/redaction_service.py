"""PII Redaction Service for ScanScribe.

Provides robust Social Security Number (SSN) detection and redaction across
live transcription ingestion, events pipeline, and retroactive database scrubbing.
"""
import json
import logging
import re
from typing import Any, Dict, Optional

from ..config import get_settings
from ..database import EventsSessionLocal, LogsSessionLocal
from ..models.event import Event, PipelineDebugLog, SpanStore
from ..models.log_entry import LogEntry

logger = logging.getLogger(__name__)

DEFAULT_SSN_REPLACEMENT = "[REDACTED SSN]"

# Standard 9-digit SSN pattern anywhere in text: 3 digits, separator, 2 digits, separator, 4 digits
STANDARD_SSN_REGEX = re.compile(r"\b\d{3}[-\s.]\d{2}[-\s.]\d{4}\b")

# Contextual trigger keywords for SSN mentions on dispatch radio
TRIGGER_KEYWORDS = r"(?:social(?:\s+security)?(?:\s+(?:number|no|#))?|ssn)"

# Context window: trigger keyword followed by optional filler phrases, then candidate number stream
# Uses negative lookahead so context does not bleed into DOB, OLN, phone, address, or already redacted tokens
CONTEXT_SSN_REGEX = re.compile(
    rf"(?i)(\b{TRIGGER_KEYWORDS}\b(?:(?!\b(?:date of birth|dob|born|oln|license|phone|address)\b|\[REDACTED)[^\d]){{0,50}}?)"
    r"((?:\b\d+(?:[\s,\-]+\d+)*\b(?:[,\s]+(?:repeating|repeat|again|correction)?[\s,]*)*)+)"
)

# Number block tokenizer for digits separated by hyphens, spaces, or commas
NUMBER_BLOCK_REGEX = re.compile(r"\b(?:\d{1,6}[-\s,]+){1,8}\d{1,6}\b|\b\d{8,11}\b")

# Spoken digits mapping
SPOKEN_DIGIT_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "oh": "0",
}
SPOKEN_DIGITS_REGEX = re.compile(
    r"(?i)\b(?:zero|one|two|three|four|five|six|seven|eight|nine|oh)\b"
)
SPOKEN_CONTEXT_REGEX = re.compile(
    rf"(?i)(\b{TRIGGER_KEYWORDS}\b[^\w\d]{{0,40}}?(?:is|it\'?s|going to be|will be|#|:|\*|-)*\s*)"
    r"((?:(?:zero|one|two|three|four|five|six|seven|eight|nine|oh)[\s,\-]*){8,12})"
)


def redact_ssn(text: Optional[str], replacement: Optional[str] = None) -> Optional[str]:
    """Redact Social Security Numbers from text.
    
    Catches standard 3-2-4 formats as well as dispatch/Whisper variations
    (e.g., stuttered groups, comma-separated tokens, and spoken digit words).
    """
    if not text:
        return text

    try:
        cfg = get_settings().config.redaction
        if not cfg.enabled or not cfg.redact_ssn:
            return text
        if replacement is None:
            replacement = cfg.replacement or DEFAULT_SSN_REPLACEMENT
    except Exception:
        if replacement is None:
            replacement = DEFAULT_SSN_REPLACEMENT

    # 1. Standard SSN formats (3-2-4 digits): 123-45-6789, 123 45 6789, 123.45.6789
    redacted = STANDARD_SSN_REGEX.sub(replacement, text)

    # 2. Spoken word digits after trigger (e.g., "social is four eight eight one five...")
    def _sub_spoken(match):
        prefix = match.group(1)
        return f"{prefix}{replacement}"

    redacted = SPOKEN_CONTEXT_REGEX.sub(_sub_spoken, redacted)

    # 3. Contextual digit groupings following trigger words
    def _redact_context_chunk(match):
        prefix = match.group(1)  # e.g. "social is ", "with a social "
        number_stream = match.group(2)

        def _sub_block(m):
            raw = m.group(0)
            digits = re.sub(r"\D", "", raw)
            if 8 <= len(digits) <= 11:
                return replacement
            if len(digits) > 11:
                sub_parts = re.split(
                    r"(,\s*|\s+repeating\s+|\s+repeat\s+|\s+again\s+|\s+correction\s+)",
                    raw,
                    flags=re.IGNORECASE,
                )
                res = []
                for sp in sub_parts:
                    d = re.sub(r"\D", "", sp)
                    if 8 <= len(d) <= 11:
                        res.append(replacement)
                    else:
                        res.append(sp)
                return "".join(res)
            return raw

        redacted_stream = NUMBER_BLOCK_REGEX.sub(_sub_block, number_stream)
        return prefix + redacted_stream

    redacted = CONTEXT_SSN_REGEX.sub(_redact_context_chunk, redacted)
    return redacted


def scrub_database_ssn(replacement: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
    """Retroactively scan and redact SSNs from all database tables.
    
    Tables scanned:
      - scanscribe.db: LogEntry (transcript, corrected_transcript)
      - scanscribe_events.db: Event (original_transcription, summary)
      - scanscribe_events.db: SpanStore (transcript)
      - scanscribe_events.db: PipelineDebugLog (payload_json)
    """
    stats = {
        "log_entries_scrubbed": 0,
        "events_scrubbed": 0,
        "span_store_scrubbed": 0,
        "debug_logs_scrubbed": 0,
        "dry_run": dry_run,
    }

    # 1. Scrub LogEntry in scanscribe.db
    logs_db = LogsSessionLocal()
    try:
        candidates = logs_db.query(LogEntry).filter(
            (LogEntry.transcript.ilike("%social%"))
            | (LogEntry.transcript.ilike("%ssn%"))
            | (LogEntry.transcript.op("GLOB")("*[0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][0-9][0-9]*"))
            | (LogEntry.corrected_transcript.isnot(None))
        ).all()

        for entry in candidates:
            changed = False
            if entry.transcript:
                new_t = redact_ssn(entry.transcript, replacement)
                if new_t != entry.transcript:
                    if not dry_run:
                        entry.transcript = new_t
                    changed = True

            if entry.corrected_transcript:
                new_c = redact_ssn(entry.corrected_transcript, replacement)
                if new_c != entry.corrected_transcript:
                    if not dry_run:
                        entry.corrected_transcript = new_c
                    changed = True

            if changed:
                stats["log_entries_scrubbed"] += 1

        if not dry_run and stats["log_entries_scrubbed"] > 0:
            logs_db.commit()
    except Exception as exc:
        logger.error("Failed scrubbing log_entries: %s", exc)
        logs_db.rollback()
        raise
    finally:
        logs_db.close()

    # 2. Scrub Events, SpanStore, and PipelineDebugLog in scanscribe_events.db
    events_db = EventsSessionLocal()
    try:
        # Events
        ev_candidates = events_db.query(Event).filter(
            (Event.original_transcription.ilike("%social%"))
            | (Event.original_transcription.ilike("%ssn%"))
            | (Event.original_transcription.op("GLOB")("*[0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][0-9][0-9]*"))
            | (Event.summary.ilike("%social%"))
            | (Event.summary.ilike("%ssn%"))
        ).all()

        for ev in ev_candidates:
            changed = False
            if ev.original_transcription:
                new_ot = redact_ssn(ev.original_transcription, replacement)
                if new_ot != ev.original_transcription:
                    if not dry_run:
                        ev.original_transcription = new_ot
                    changed = True

            if ev.summary:
                new_s = redact_ssn(ev.summary, replacement)
                if new_s != ev.summary:
                    if not dry_run:
                        ev.summary = new_s
                    changed = True

            if changed:
                stats["events_scrubbed"] += 1

        # SpanStore
        span_candidates = events_db.query(SpanStore).filter(
            (SpanStore.transcript.ilike("%social%"))
            | (SpanStore.transcript.ilike("%ssn%"))
            | (SpanStore.transcript.op("GLOB")("*[0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][0-9][0-9]*"))
        ).all()

        for span in span_candidates:
            if span.transcript:
                new_st = redact_ssn(span.transcript, replacement)
                if new_st != span.transcript:
                    if not dry_run:
                        span.transcript = new_st
                    stats["span_store_scrubbed"] += 1

        # PipelineDebugLog
        debug_candidates = events_db.query(PipelineDebugLog).filter(
            (PipelineDebugLog.payload_json.ilike("%social%"))
            | (PipelineDebugLog.payload_json.ilike("%ssn%"))
        ).all()

        for dlog in debug_candidates:
            if dlog.payload_json:
                new_json = redact_ssn(dlog.payload_json, replacement)
                if new_json != dlog.payload_json:
                    if not dry_run:
                        dlog.payload_json = new_json
                    stats["debug_logs_scrubbed"] += 1

        if not dry_run and (
            stats["events_scrubbed"] > 0
            or stats["span_store_scrubbed"] > 0
            or stats["debug_logs_scrubbed"] > 0
        ):
            events_db.commit()
    except Exception as exc:
        logger.error("Failed scrubbing events db: %s", exc)
        events_db.rollback()
        raise
    finally:
        events_db.close()

    logger.info("SSN Scrub completed: %s", stats)
    return stats
