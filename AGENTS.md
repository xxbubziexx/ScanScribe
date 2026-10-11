# ScanScribe Agent Guidelines & Operational Protocol

Welcome to **ScanScribe** — an enterprise-grade public safety radio transcription and incident intelligence pipeline.
ScanScribe ingests live audio transmissions from radio recorders (e.g. Trunk Recorder, SDR), transcribes via local Whisper models, performs Silero VAD gating and Named Entity Recognition (NER), classifies incidents via OpenRouter LLM routing, and powers an interactive React geospatial command center.

> **CRITICAL ENVIRONMENT CONTEXT**:  
> ScanScribe runs live on an Ubuntu production/edge node ingesting real-world public safety radio traffic 24/7. Development is conducted across different machines (Windows/Ubuntu) by different AI models. All models and agents operating in this repository must adhere strictly to these rules to prevent code decay and protect live data capture.

---

## 1. Prime Directive: Zero Regressions in Live Real-Time Ingest

1. **Ingestion Loop Priority:** Audio files placed into `ingest/` must **never** be dropped, delayed, deadlock, or disappear without ingestion.
2. **Non-Blocking Async Pipeline:** Never introduce blocking synchronous I/O, synchronous HTTP (`requests`), or `time.sleep()` into the asynchronous event loop or worker pipelines. Use `httpx.AsyncClient` and `asyncio.sleep`.
3. **Database Concurrency & WAL:** ScanScribe uses a single unified SQLite database (`data/scanscribe.db`) running with `PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON`. Never execute table-locking operations or ad-hoc `DROP TABLE` statements on runtime startup.
4. **Data Preservation:** User audio in `audio_storage/`, active incidents, and transcription records must remain persistent and lossless. Never purge or wipe production directories.

---

## 2. Post-Refactor Codebase Integrity (Strict Architectural Guardrails)

The codebase has completed an extensive 5-phase modular refactor (documented in [`Plan/refactoring_master_plan.md`](file:///a:/Scanscribe_Projects/scanscribe/Plan/refactoring_master_plan.md)). Models must **NEVER** reintroduce legacy "Layer-Cake AI Archeology":

* **Database Migrations via Alembic Only:**
  * All database schema alterations must be enacted strictly via Alembic revisions in [`alembic/versions/`](file:///a:/Scanscribe_Projects/scanscribe/alembic/versions/).
  * Never alter table columns through ad-hoc startup SQL probing or destructive auto-drops.
* **No Inline Imports:**
  * All `import` statements must remain cleanly organized at the top of Python modules. Never insert inline imports inside function bodies to hide circular dependencies.
* **No Blind Exception Swallowing:**
  * Broad `except Exception: pass` blocks are strictly forbidden. Catch specific exceptions, handle or re-raise them, or log them with appropriate severity (`logger.warning` / `logger.error`) including traceback context.
* **Strong Type Contracts:**
  * Backend endpoints and services must be defined with explicit **Pydantic v2 schemas**.
  * Frontend components must use matching **TypeScript interfaces** (no `any` types for domain models).
* **Managed Lifecycles & Concurrency:**
  * Do not spawn bare unmanaged `threading.Thread(...)` or untracked `asyncio.create_task(...)` without keeping task references and registering shutdown drains.

---

## 3. Inter-Model Handoff Protocol (Mandatory)

Because multiple models (e.g. Claude, Gemini, OpenAI) and different machines work on this codebase across independent sessions, **[`ACTIVE_CONTEXT.md`](file:///a:/Scanscribe_Projects/scanscribe/ACTIVE_CONTEXT.md) is the living blackboard and shared memory**.

### On Session Start:
1. **Read [`ACTIVE_CONTEXT.md`](file:///a:/Scanscribe_Projects/scanscribe/ACTIVE_CONTEXT.md)** before writing code to understand what the previous model completed, current architectural focus, and any live environment gotchas.
2. **Review `git status` & recent commits** (`git log -n 5 --oneline`) to orient yourself to the current branch state.

### On Session Wrap-up / Completing a Task:
1. **Run verification tests:** Execute `pytest tests/` (and frontend checks if modifying UI).
2. **Update [`ACTIVE_CONTEXT.md`](file:///a:/Scanscribe_Projects/scanscribe/ACTIVE_CONTEXT.md):** Append a new structured handoff log entry with:
   - Date & Model Name
   - Summary of Changes
   - Live Ubuntu Ingestion Impact
   - Gotchas / Warnings for the Next Model
   - Remaining / Next Tasks
3. *(Alternative)* Run the `.agents/skills/handoff` skill to automate this process.

---

## 4. Multi-Machine Development Conventions

* **Windows Dev Workstations:** When developing on non-Ubuntu machines, live radio SDR hardware will not be present. Run tests using synthetic fixtures in `tests/` and verify unit/integration test suites.
* **Ubuntu Live Node:** When pulling changes to the Ubuntu machine, ensure migrations (`alembic upgrade head`) and service restarts follow clean startup procedures without killing background tasks mid-transcription.
* **Configuration:** Never commit sensitive tokens, API keys, or live `.env` / `config.yml` files. Keep `.env.example` and `config.yml.example` updated with any new required keys.

---

## 5. Git Branching & Promotion Protocol (STRICT ENFORCEMENT)

All agents and models must strictly follow this branching protocol:

1. **`snapshot` is the Exclusive Development Branch:**
   - **ALL active code edits, bug fixes, refactorings, and day-to-day commits MUST be made on `snapshot`.**
   - **NEVER** write code or commit directly onto `main` during standard development tasks.
   - At the beginning of any session or prior to modifying files, verify your active branch: `git branch --show-current`. If not on `snapshot`, switch immediately: `git switch snapshot`.
   - Push development progress directly to `origin snapshot`: `git push origin snapshot`.

2. **`main` is the Protected Production Release Branch:**
   - `main` serves as the rock-solid production release. It is what the public landing page installer one-liners (`install.ps1` / `install.sh`) and standard `scanscribe update` fetch by default.
   - `main` is updated **ONLY** via clean fast-forward promotion merges from `snapshot` after a batch of features or fixes has passed all verification gates.

3. **Release Promotion Procedure (`snapshot` → `main`):**
   - When the user explicitly requests promoting changes to production or cutting a release:
     1. Verify full test suite: `pytest tests/` (must be 100% green).
     2. Verify migrations: `alembic upgrade head`.
     3. Switch to `main`: `git switch main`.
     4. Pull latest `main`: `git pull --ff-only origin main`.
     5. Fast-forward merge `snapshot`: `git merge --ff-only snapshot`.
     6. Tag release (e.g. `v2.0.1`): `git tag -a vX.Y.Z -m "Release vX.Y.Z"`.
     7. Push release: `git push origin main --tags`.
     8. **Immediately switch back to development**: `git switch snapshot`.

4. **Zero Force-Push Policy:**
   - Never run destructive `git push --force` on `main` or `snapshot`.
   - Legacy pre-refactor code remains permanently archived under `archive/*` tags and `legacy/*` branches.

