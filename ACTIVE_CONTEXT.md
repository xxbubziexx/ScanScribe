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

<!-- 
### TEMPLATE FOR NEXT MODEL (Copy & Fill Below):
### [YYYY-MM-DD HH:MM] | <Model Name> (<Machine: Windows/Ubuntu>)
- **Work Performed:** <Summary of changes made>
- **Live Ingestion Impact:** <Any changes to ingest/, workers, or ports?>
- **Gotchas / Warnings for Next Model:** <Gotchas, quirks, or pitfalls discovered>
- **Verification Performed:** <pytest / typecheck / live testing results>
- **Next Tasks / Unfinished Work:** <What should the next agent work on?>
-->
