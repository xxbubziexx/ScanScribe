# Phase 4: Backend Modularization & Clean Code Standards

> **Phase Order**: 4 of 5  
> **Status**: Ready for Implementation  
> **Estimated Execution Time**: ~3–4 hours  
> **Target Files**: `app/services/events_worker.py`, `app/routes/events.py`, `app/routes/insights.py`, `app/config.py`, `app/schemas/`

---

## 1. Objectives

1. Decompose monolithic 1,000+ line god-files into cohesive, single-responsibility modules.
2. Untangle circular dependencies to eliminate all **64+ inline function imports**, restoring clean top-level imports.
3. Replace **84+ blanket `except Exception: pass`** statements with specific exception catching and structured logging.
4. Separate SQLAlchemy models from Pydantic API schemas by introducing a dedicated `app/schemas/` package.
5. Eliminate configuration aliases and hardcoded state defaults (e.g. `DEFAULT_STATE = "Missouri"`).

---

## 2. Decomposing the God-Files

### 1. [`app/services/events_worker.py`](file:///a:/Scanscribe_Projects/scanscribe/app/services/events_worker.py) (1,108 lines)
Split into the `app/services/events/` package:

```
app/services/events/
├── __init__.py           # Clean public exports (process_transcript_for_monitor, etc.)
├── pipeline.py           # Core routing & transcript ingestion loop (~300 lines)
├── spans.py              # SpanStore & EntityObservation creation and extraction (~200 lines)
├── incidents.py          # Event entity creation, merging, and attachment (~250 lines)
├── cleanup.py            # Stale event auto-closing and maintenance sweep (~150 lines)
└── context.py            # Canonical context builder (open incidents, recent spans) (~150 lines)
```

### 2. [`app/routes/events.py`](file:///a:/Scanscribe_Projects/scanscribe/app/routes/events.py) (1,059 lines)
Decompose into sub-routers aggregated under `app/routes/events/`:

```
app/routes/events/
├── __init__.py           # APIRouter combining all sub-routers
├── monitors_router.py    # Monitor CRUD: /monitors, /monitors/{id}
├── incidents_router.py   # Event lifecycle: /events, /events/{id}, close, reopen, manual patch
├── spans_router.py       # Data querying: /spans, /span-store, /entities
├── geocode_router.py     # Location API: /geocoder/autocomplete, /geocoder/reverse
└── admin_router.py       # Debugging & LLM status: /debug, /llm-status, /global-rules
```

### 3. [`app/routes/insights.py`](file:///a:/Scanscribe_Projects/scanscribe/app/routes/insights.py) (874 lines)
Extract the mathematical aggregation logic out of the route handler into [`app/services/insights_engine.py`](file:///a:/Scanscribe_Projects/scanscribe/app/services/insights_engine.py):
* Move `get_hourly_activity`, `get_daily_activity`, `get_weekly_activity`, and trend calculations into the engine.
* The route handler in `app/routes/insights.py` becomes a thin controller:
```python
@router.get("/stats", response_model=InsightsStatsResponse)
async def get_insights_stats(
    date: Optional[str] = Query(None),
    view: str = Query("hourly"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    target_date = parse_date_or_today(date)
    return insights_engine.compute_stats(db, target_date, view)
```

---

## 3. Eradicating Circular Imports & 64+ Inline Imports

### Why Did Circular Imports Occur?
Models frequently imported services inside models, or models inside routers that imported services that imported routers:

```
[app.main] ──► [app.routes.events] ──► [app.services.events_worker]
     ▲                                                │
     │                                                ▼
[app.database] ◄──────── (Inline Import) ──────── [app.models.event]
```

### Architectural Dependency Hierarchy (Strict Layering):
To guarantee zero import cycles, enforce a strict one-way dependency chain:

```
Layer 0: Config & Core Database Base (app.config, app.database)
   │
   ▼
Layer 1: Domain Models & Schemas (app.models.*, app.schemas.*)  <-- Pure data, NEVER imports services
   │
   ▼
Layer 2: Utility & Low-Level Helpers (app.utils.*, app.services.http_client)
   │
   ▼
Layer 3: Core Domain Services (app.services.*)
   │
   ▼
Layer 4: API Presentation Layer (app.routes.*, app.main)
```

### Execution Rule:
Once data models only depend on `Base` and standard library types, **every inline import** (`from .foo import bar` inside a `def`) can be safely relocated to the top of the file without generating an `ImportError`.

---

## 4. Eradicating Blanket `except Exception: pass`

Audit and replace all 84 occurrences of unhandled `except Exception:` with specific error types and actionable logging.

### Anti-Pattern Example ([`app/services/events_router_engine.py:402`](file:///a:/Scanscribe_Projects/scanscribe/app/services/events_router_engine.py#L402)):
```python
# BEFORE (Silent data loss / masked bug)
try:
    decision = json.loads(cleaned[idx:])
    return decision
except Exception:
    pass
```

### Clean Standard:
```python
# AFTER (Explicit parsing with diagnostics)
try:
    decision = json.loads(cleaned[idx:])
    return decision
except json.JSONDecodeError as exc:
    logger.debug("Failed parsing JSON block at offset %d: %s", idx, exc)
    continue
except Exception as exc:
    logger.error("Unexpected error parsing LLM routing response: %s", exc, exc_info=True)
    break
```

---

## 5. Configuration Consolidation

Clean up historical duplicate fields in [`app/config.py`](file:///a:/Scanscribe_Projects/scanscribe/app/config.py):

1. **Deprecate Duplicate Model Configs**:
   Merge `openrouter` and `incidents_ollama` into a single, provider-agnostic LLM configuration:
   ```yaml
   llm:
     provider: "openrouter"  # "openrouter" | "ollama" | "deepseek"
     api_key: "${LLM_API_KEY}"
     base_url: "https://openrouter.ai/api/v1"
     model: "anthropic/claude-3.5-haiku"
     timeout_seconds: 30
   ```
2. **Remove Hardcoded Regional Defaults**:
   In [`app/services/geocoder_service.py`](file:///a:/Scanscribe_Projects/scanscribe/app/services/geocoder_service.py), remove hardcoded `Missouri` fallbacks. Read directly from `config.yml`:
   ```python
   default_state = config.geocoding.default_state or os.getenv("DEFAULT_GEO_STATE", "")
   ```

---

## 6. Database Transaction & Cache Optimization

### 1. Eliminate Redundant Commits (`app/services/events_worker.py`)
`_create_event_full` currently flushes the event, commits, creates a link, commits, and then immediately calls `summarize_event_attachments` which queries another session, updates the summary, and commits *again*.
* **Fix**: Batch all object creation and updates into a single scoped transaction. Do not commit until the fully initialized `Event` and its first `EventTranscriptLink` are fully constructed.

### 2. Optimize Monitor Index Cache
`_build_monitor_talkgroup_index` scans the entire `Monitor` table on every fingerprint mismatch (which occurs anytime *any* monitor is updated).
* **Fix**: Implement row-level or dictionary-based cache invalidation for the monitor talkgroup index, preventing full table scans on high-ingest paths.

### 3. Optimize JSON Recovery (`app/services/events_router_engine.py`)
`_clean_and_parse_json` uses an expensive brute-force loop that sequentially raises and catches `json.JSONDecodeError` to heuristically repair truncated tokens.
* **Fix**: Replace the exception-driven loop with an AST/regex-based schema extractor for the known `action`, `event_id`, and `reason` fields if standard parsing fails.

---

## 7. Verification Criteria

- [ ] Command `grep -rn "^\s\+import " app/` returns **0** matches.
- [ ] Command `grep -rn "except Exception:\s*pass" app/` returns **0** matches.
- [ ] No Python file in `app/` exceeds **500 lines** in length.
- [ ] All API request/response types validate via Pydantic schemas in `app/schemas/`.
- [ ] Full test suite executes cleanly: `pytest tests/`.
