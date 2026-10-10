# ScanScribe Active Context & Inter-Model Blackboard

This living document is the **shared memory** between different AI models, human developers, and multiple workstations (Ubuntu Live Node and Windows Dev Machines). 

> **MANDATORY FOR ALL AGENTS:**  
> 1. Read this file at the start of every session.
> 2. Append a new entry to the **Handoff Log** below when completing your task or switching models/machines.

---

## 1. System Health & Current State

- **Current Architecture Phase:** Phases 1–5 Modular Refactor Completed (refer to [`Plan/refactoring_master_plan.md`](file:///a:/Scanscribe_Projects/scanscribe/Plan/refactoring_master_plan.md)).
- **Database Status:** Unified single SQLite database (`data/scanscribe.db`) with WAL mode enabled. Managed via Alembic (`alembic/versions/`). Seamless legacy database migration script in place (`57dda4f`).
- **Live Node Environment:** Ubuntu server ingesting live radio audio into `ingest/`.
- **Active Focus:** Ensuring post-refactor stability, live testing with real radio traffic, and adding new operational features without regression.

---

## 2. In-Progress Features & Next Objectives

- [ ] Validate live ingestion queue on Ubuntu with sustained high-traffic radio talkgroups.
- [ ] Monitor Alembic migration idempotence across clean setups and legacy upgrades.
- [ ] Expand automated test coverage for async OpenRouter LLM incident classification failover.

---

## 3. Model Handoff Log

### Baseline Entry — 2026-10-10 | Gemini 3.8 Flash (Pair Programming Session)
- **Author/Model:** Gemini 3.8 Flash (Antigravity IDE)
- **Work Performed:**
  - Established cross-machine and multi-model synchronization protocol.
  - Created root [`AGENTS.md`](file:///a:/Scanscribe_Projects/scanscribe/AGENTS.md) with strict post-refactor guardrails (no inline imports, no bare excepts, Alembic migrations only, async non-blocking safety).
  - Created [`ACTIVE_CONTEXT.md`](file:///a:/Scanscribe_Projects/scanscribe/ACTIVE_CONTEXT.md) and automated `.agents/skills/handoff` skill.
- **Live Ingest / Ubuntu Node Impact:** Zero impact. Guardrails installed to protect live radio capture.
- **Gotchas & Warnings for Next Model:**
  - Legacy SQLite DBs (`scanscribe_logs.db`, `scanscribe_events.db`) are unified into `data/scanscribe.db`. Never re-create the split databases or hardcode paths to old SQLite files.
  - When writing new database queries, use SQLAlchemy session models or Alembic migrations—never run raw DDL scripts at application startup.
- **Next Recommended Tasks:** Continue any scheduled feature development or live verification testing on the Ubuntu node.

---

### 2026-10-10 14:00 | Gemini 3.8 Flash (Windows Dev Workstation)
- **Work Performed:**
  - Implemented `scanscribe uninstall` CLI subcommand in [`app/server_control.py`](file:///a:/Scanscribe_Projects/scanscribe/app/server_control.py) and registered in [`app/cli.py`](file:///a:/Scanscribe_Projects/scanscribe/app/cli.py).
  - Created native uninstaller scripts: [`uninstall.ps1`](file:///a:/Scanscribe_Projects/scanscribe/uninstall.ps1) (Windows) and [`uninstall.sh`](file:///a:/Scanscribe_Projects/scanscribe/uninstall.sh) (Linux).
  - Uninstaller stops background service, removes Windows Task Scheduler logon task (or systemd user unit), removes `<InstallDir>\bin` from User PATH, purges Python bytecode caches (`__pycache__`, `*.pyc`), and deletes `.venv` and packages.
  - Adhered strictly to Prime Directive 4 (Data Preservation): User database (`data/scanscribe.db`), audio recordings (`audio_storage/`), models, and configs are preserved by default. Added optional `--purge` flag for complete removal.
- **Live Ingest / Ubuntu Node Impact:** Zero impact. Does not affect active live radio ingest or database schema.
- **Gotchas / Warnings for Next Model:**
  - On Windows, `python.exe` cannot delete its own running `.venv` in-process due to OS file locking; `cmd_uninstall` handles this cleanly by scheduling detached background removal after the process terminates.
- **Verification Performed:**
  - Executed full pytest suite (`python -m pytest tests/`): 77 passed, 0 failed.
  - Tested `scanscribe --help` and `scanscribe uninstall --help`.
- **Next Tasks / Unfinished Work:** Ready for deployment or user testing.

---

### 2026-10-10 16:35 | Gemini 3.8 Flash (Windows Dev Workstation)
- **Work Performed:**
  - Configured Hugging Face model `sepiaapps/whisper-small.en-police-radio` (the battle-tested CrimeRadar public safety foundation model) as the default installation and runtime Whisper model across ScanScribe.
  - Updated [`app/config.py`](file:///a:/Scanscribe_Projects/scanscribe/app/config.py) and [`config.yml.example`](file:///a:/Scanscribe_Projects/scanscribe/config.yml.example) default model name to `whisper-small.en-police-radio`.
  - Added robust `_resolve_model_target()` in [`app/services/transcription_engine.py`](file:///a:/Scanscribe_Projects/scanscribe/app/services/transcription_engine.py) to resolve model weights from local directories, workspace `./models`, or directly stream/load from Hugging Face Hub if weights are not yet pre-downloaded locally.
  - Updated native installer scripts [`install.ps1`](file:///a:/Scanscribe_Projects/scanscribe/install.ps1) and [`install.sh`](file:///a:/Scanscribe_Projects/scanscribe/install.sh) to automatically map `whisper-small.en-police-radio` to `sepiaapps/whisper-small.en-police-radio` for automated `snapshot_download` and set native `model.path` in generated `config.yml`.
  - Updated interactive station configurator in [`scanscribe_landing_page/index.html`](file:///a:/Scanscribe_Projects/scanscribe_landing_page/index.html) to reflect the CrimeRadar police radio model default.
  - Placed NER pipeline integration on standby per user request.
- **Live Ingestion Impact:** None. Transcriptions continue to route through `TranscriptionEngine` with identical input/output schemas.
- **Gotchas / Warnings for Next Model:**
  - `sepiaapps/whisper-small.en-police-radio` is a `small` Whisper variant (~967MB weights); it easily runs in ~1.1GB RAM / 1.2GB VRAM across CPU or CUDA.
  - If users don't pre-download weights via `install.ps1`/`install.sh`, `transcription_engine.py` will automatically fall back to downloading directly from Hugging Face Hub on first load.
- **Verification Performed:**
  - Ran full test suite: 77 passed in 12.43s.
- **Next Tasks / Unfinished Work:** Standby for NER model integration.

---

### 2026-10-10 17:55 | Gemini 3.8 Flash (Windows Dev Workstation)
- **Work Performed:**
  - Integrated public-safety NER model [`xxbubziexx/incident_ner_v1`](https://huggingface.co/xxbubziexx/incident_ner_v1) as the default Named Entity Recognition model across ScanScribe.
  - Updated [`app/config.py`](file:///a:/Scanscribe_Projects/scanscribe/app/config.py) (`EventsPipelineConfig.ner_model_path: "./models/incident_ner_v1"`) and [`config.yml.example`](file:///a:/Scanscribe_Projects/scanscribe/config.yml.example).
  - Added smart target resolution `_resolve_ner_target()` in [`app/services/ner_service.py`](file:///a:/Scanscribe_Projects/scanscribe/app/services/ner_service.py) supporting local folder paths, workspace `./models/incident_ner_v1`, and automatic fallbacks to Hugging Face Hub `xxbubziexx/incident_ner_v1`.
  - Updated native installer scripts [`install.ps1`](file:///a:/Scanscribe_Projects/scanscribe/install.ps1) and [`install.sh`](file:///a:/Scanscribe_Projects/scanscribe/install.sh) to automatically pre-download `xxbubziexx/incident_ner_v1` into `<InstallDir>/models/incident_ner_v1` and tune `config.yml` with the absolute model path.
  - Updated station installer descriptions in [`scanscribe_landing_page/index.html`](file:///a:/Scanscribe_Projects/scanscribe_landing_page/index.html) to feature both the CrimeRadar public safety Whisper and Incident NER models.
- **Live Ingestion Impact:** None. Zero schema changes or breaking changes to existing database or pipeline logic.
- **Gotchas / Warnings for Next Model:**
  - Both Whisper (`sepiaapps/whisper-small.en-police-radio`) and NER (`xxbubziexx/incident_ner_v1`) are configured for full local execution or seamless Hugging Face Hub loading.
- **Verification Performed:**
  - Full pytest suite ran: 77 passed in 12.27s (0 failures, 0 warnings).
- **Next Tasks / Unfinished Work:** All requested models (Whisper + NER) are fully wired into configuration, installer scripts, landing page, and inference engines.



<!-- 
### TEMPLATE FOR NEXT MODEL (Copy & Fill Below):
### [YYYY-MM-DD HH:MM] | <Model Name> (<Machine: Windows/Ubuntu>)
- **Work Performed:** <Summary of changes made>
- **Live Ingestion Impact:** <Any changes to ingest/, workers, or ports?>
- **Gotchas / Warnings for Next Model:** <Gotchas, quirks, or pitfalls discovered>
- **Verification Performed:** <pytest / typecheck / live testing results>
- **Next Tasks / Unfinished Work:** <What should the next agent work on?>
-->
