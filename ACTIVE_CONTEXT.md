# ScanScribe Active Context & Inter-Model Blackboard

Shared working memory across AI models and workstations (Ubuntu live Docker node and Windows dev machines). Read this file on session start and append a concise entry on wrap-up. *(Historical session logs prior to 2026-11-24 are preserved in git history.)*

---

## 1. Current System State

- **Active Development Branch:** `snapshot` (ahead of release branch `main`; commit all changes to `snapshot` only — see [`AGENTS.md`](file:///a:/Scanscribe_Projects/scanscribe/AGENTS.md)).
- **Runtime & Database:** Unified SQLite DB (`data/scanscribe.db`, `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`), managed via Alembic ([`alembic/versions/`](file:///a:/Scanscribe_Projects/scanscribe/alembic/versions/)). Live Ubuntu node runs inside Docker with `./app` bind-mounted (`scanscribe restart` picks up app code edits).
- **Audio & Intelligence Pipelines:** Local Whisper ASR (`sepiaapps/whisper-small.en-police-radio`), local NER (`xxbubziexx/incident_ner_v1`), optional OpenRouter LLM incident routing, and hardened NER-only mode (`events_pipeline.ner_only: true`).
- **Frontend:** React + Vite + Tailwind compiled into [`app/frontend/dist/`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/dist/).

---

## 2. Active Gotchas & Environment Notes

- **NER-Only Mode & Monitors:** `span_store.monitor_id` has an FK to `monitors.id` — at least one enabled `Monitor` matching the talkgroup must exist in the DB for NER-only ingest to persist spans. `extract_entities()` raises `RuntimeError` if `_pipeline` is unloaded/failing on non-empty transcripts.
- **Ubuntu Live DB Alembic Stamp:** The live node's schema was created via app table init and lacks an `alembic_version` table. Run a one-time `alembic stamp <current-head>` (with a backup copy of `data/scanscribe.db`) before applying any future Alembic revision.
- **CSS Layering (`audio-player.css`):** [`audio-player.css`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/styles/audio-player.css) is unlayered. Component overrides targeting embedded `.sc-audio-player*` inside [`database.css`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/styles/components/database.css) must remain outside `@layer components`.
- **SQLite Soft-Delete Predicate:** Always use `LogEntry.is_deleted.is_not(True)` (`IS NOT 1`), never `is_(False)` or `== False`, to keep SQLite queries on `idx_timestamp`.
- **Frontend Tooling (Windows):** Run Vite builds via `npm.cmd --prefix app/frontend run build` (and stage updated `app/frontend/dist` when shipping frontend changes). Run Vitest from inside `app/frontend` via `npx.cmd vitest run ...`. Known pre-existing failure: [`DatePickers.test.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/test/DatePickers.test.tsx) (2 tests expecting Oct 2026 calendar cells against Nov 2026 clock). Do not stage untracked root `config-ui/` or `node_modules/`.

---

## 3. Next Objectives

- [ ] Validate live UI updates and `ner_only` ingestion on the Ubuntu Docker node.
- [ ] Run one-time `alembic stamp <current-head>` on the live Ubuntu database before introducing any new Alembic migrations.
- [ ] Promote verified `snapshot` changes to `main` and tag release when ready.

---

## 4. Model Handoff Log

### 2026-11-25 | Gemini 4 Neon (High) (Windows Dev Workstation)
- **Active `snapshot` Rollup (`43baf4b`..`c5f5262`):**
  - **NER-Only Hardening:** Propagated NER failures in `ner_service.py`, added shared `is_events_pipeline_active(cfg)` and startup monitor warnings, normalized rate-limited unmatched-talkgroup logging, updated `/api/events/llm-status`, and added SQLite acceptance coverage in [`tests/test_ner_only_mode.py`](file:///a:/Scanscribe_Projects/scanscribe/tests/test_ner_only_mode.py).
  - **Monitor Deletion Warning:** Added `GET /api/events/monitors/{monitor_id}/delete-impact` ([`monitors_router.py`](file:///a:/Scanscribe_Projects/scanscribe/app/routes/events/monitors_router.py)) + [`MonitorDeleteModal.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/pages/Events/components/MonitorDeleteModal.tsx) showing exact `ON DELETE CASCADE` row counts, a `Disable Monitor Instead` shortcut, and type-to-confirm deletion while preserving `log_entries`.
  - **Database Workbench Suite:** Unified `/data/*` (`Transmissions`, `Span Store`, `NER Entities`, `Events`, `Fine-Tuning Dataset`) into a full-bleed dark workbench ([`DataExplorerLayout.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/pages/DataExplorer/DataExplorerLayout.tsx), [`database.css`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/styles/components/database.css)) with left-rail live table counts/telemetry (`GET /api/maintenance/overview`), cross-page audio ZIP export, NER raw-values CSV exporter, drag-resizable persisted columns ([`useResizableColumns.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/pages/DataExplorer/hooks/useResizableColumns.tsx)), multi-select checkbox talkgroup filtering ([`TalkgroupMultiSelect.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/components/database/TalkgroupMultiSelect.tsx), [`logs.py`](file:///a:/Scanscribe_Projects/scanscribe/app/routes/logs.py)), compact expanded inspector drawer + single-row audio player ([`LogExpandedRow.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/pages/Database/components/LogExpandedRow.tsx)), and Refresh `+N` delta / relative timestamp status ([`WorkbenchRefreshControl.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/pages/DataExplorer/components/WorkbenchRefreshControl.tsx)).
  - **Search Results Polish:** Updated [`SearchPage.tsx`](file:///a:/Scanscribe_Projects/scanscribe/app/frontend/src/pages/Search/SearchPage.tsx) result cards with crisp `rounded-sm` surfaces, color-coded metadata/NER badges, threshold-colored ASR confidence indicators, and bolder transcript typography.
- **Latest Verified Checks (as of `c5f5262`):**
  - `.venv\Scripts\python.exe -m pytest tests/test_database_dashboard.py -v`: **5 passed**.
  - `npm.cmd --prefix app/frontend run build`: `tsc -b && vite build` passed (`built in 1.86s`).
  - Targeted Vitest (`DatabaseDashboard.test.tsx`, `App.test.tsx`, `TopNav.test.tsx`, `AdminMobileRestriction.test.tsx`): **4 test files passed (24 tests passed)**.
