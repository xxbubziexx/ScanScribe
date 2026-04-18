"""NER service: loads fine-tuned token classification model, extracts entities from transcripts."""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Entity labels from user's model
ENTITY_LABELS = frozenset({"UNIT", "LOC", "SUBJECT", "DESC", "EVT_TYPE", "ADDRESS", "X_STREET", "AGENCY", "STATUS", "CONTEXT"})

_pipeline = None


def is_loaded() -> bool:
    """True if NER model is loaded."""
    return _pipeline is not None


def _normalize_label(label: str) -> str:
    """Strip B-/I- prefix to get entity type."""
    if not label:
        return ""
    s = str(label).strip().upper()
    if s.startswith("B-") or s.startswith("I-"):
        return s[2:]
    return s


def load_ner_model(model_path: str) -> bool:
    """Load NER pipeline from local folder. Returns True on success."""
    global _pipeline
    path = Path(model_path).resolve()
    if not path.is_dir():
        logger.error("NER model path is not a directory: %s", path)
        return False
    try:
        from transformers import pipeline
        _pipeline = pipeline(
            "ner",
            model=str(path),
            aggregation_strategy="simple",
            device=-1,  # CPU
        )
        logger.info("NER model loaded from %s", path)
        return True
    except Exception as e:
        logger.exception("Failed to load NER model from %s: %s", path, e)
        _pipeline = None
        return False


def normalize_span_for_ner(text: str, strip_commas: bool) -> str:
    """
    Light pre-NER normalization. Only ASCII commas removed when strip_commas is True.
    Revert: set events_pipeline.ner_strip_commas: false in config.yml.
    """
    if not text:
        return ""
    if not strip_commas:
        return text
    return text.replace(",", "")


def extract_entities(transcript: str, threshold: float = 0.0) -> tuple[Dict[str, List[str]], List[dict]]:
    """
    Run NER on transcript. Returns (entities_dict, raw_pipeline_results).
    entities: {"EVT_TYPE": ["fire"], "ADDRESS": ["123 Main St"], ...}
    raw: list of {"entity_group", "word", "start", "end", "score"} from pipeline
    threshold: minimum confidence score (0.0–1.0); spans below this are discarded.
    """
    global _pipeline
    if not _pipeline or not transcript or not transcript.strip():
        return {}, []

    try:
        results = _pipeline(transcript.strip()) or []
    except Exception as e:
        logger.warning("NER inference failed: %s", e)
        return {}, []

    if threshold > 0.0:
        results = [r for r in results if float(r.get("score", 0)) >= threshold]

    # Use transcript[start:end] and merge consecutive same-entity spans (avoids "##" tokenizer artifacts)
    text = transcript.strip()
    out: Dict[str, List[str]] = {}
    seen: Dict[str, set] = {}
    # Group consecutive same-entity spans, then extract merged text from transcript
    i = 0
    while i < len(results):
        item = results[i]
        entity = _normalize_label(item.get("entity_group") or item.get("entity", ""))
        if not entity or entity not in ENTITY_LABELS:
            i += 1
            continue
        start = int(item.get("start", 0))
        end = int(item.get("end", 0))
        j = i + 1
        while j < len(results):
            next_item = results[j]
            next_entity = _normalize_label(next_item.get("entity_group") or next_item.get("entity", ""))
            if next_entity != entity:
                break
            next_end = int(next_item.get("end", 0))
            if next_item.get("start", 0) <= end:
                end = max(end, next_end)
                j += 1
            else:
                break
        word = text[start:end].strip() if 0 <= start < end <= len(text) else (item.get("word") or "").replace("##", "").strip()
        if word:
            seen.setdefault(entity, set())
            key = word.lower()
            if key not in seen[entity]:
                seen[entity].add(key)
                out.setdefault(entity, []).append(word)
        i = j
    return out, results


def parse_list_field(raw: Optional[str]) -> List[str]:
    """Parse a JSON array or comma-separated string into a list of trimmed strings."""
    if not raw or not str(raw).strip():
        return []
    s = str(raw).strip()
    if s.startswith("["):
        try:
            out = json.loads(s)
            return [str(x).strip() for x in out] if isinstance(out, list) else [s]
        except (json.JSONDecodeError, TypeError):
            pass
    return [x.strip() for x in s.split(",") if x.strip()]
