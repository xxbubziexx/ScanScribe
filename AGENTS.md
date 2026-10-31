# ScanScribe Agent Guidelines & Operational Protocol

Welcome to **ScanScribe** — a professional-grade radio transcription and incident intelligence pipeline built for serious scanner hobbyists, SDR systems operators, and the RadioReference / r/policescanner communities.
ScanScribe ingests live audio transmissions from radio recorders (e.g. Trunk Recorder, SDR), transcribes via local Whisper models, performs Silero VAD gating and Named Entity Recognition (NER), classifies incidents via OpenRouter LLM routing, and powers an interactive React geospatial command center. You are responsible for keeping this file updated as you learn and discover new things about ScanScribe.

> **PRODUCT IDENTITY & PROFESSIONAL STANDARD**:  
> ScanScribe is engineered to professional standards for **serious radio hobbyists, SDR operators, and the RadioReference / r/policescanner communities**. While technically rigorous, it is **NOT** a certified 911 dispatch or public safety CAD suite. Keep all documentation, UI copy, and commit messages technically precise, clean, and free of bloated enterprise marketing jargon ("tactical field responders", "CAD compliance"). Maintain an instrument-grade, serious tool tone. Minimize emojis across all documentation, code comments, and UI elements.

> **CRITICAL ENVIRONMENT CONTEXT**:  
> ScanScribe runs live on an Ubuntu production/edge node ingesting real-world public safety radio traffic 24/7. That node runs ScanScribe **inside Docker**, not natively — see §4. Development is conducted across different machines (Windows/Ubuntu) by different AI models. All models and agents operating in this repository must adhere strictly to these rules to prevent code decay and protect live data capture.

---

## 1. Prime Directive: Zero Regressions in Live Real-Time Ingest

1. **Ingestion Loop Priority:** Audio files placed into `ingest/` must **never** be dropped, delayed, deadlock, or disappear without ingestion.
2. **Non-Blocking Async Pipeline:** Never introduce blocking synchronous I/O, synchronous HTTP (`requests`), or `time.sleep()` into the asynchronous event loop or worker pipelines. Use `httpx.AsyncClient` and `asyncio.sleep`.
3. **Database Concurrency & WAL:** ScanScribe uses a single unified SQLite database (`data/scanscribe.db`) running with `PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON`. Never execute table-locking operations or ad-hoc `DROP TABLE` statements on runtime startup.
4. **Data Preservation:** User audio in `audio_storage/`, active incidents, and transcription records must remain persistent and lossless. Never purge or wipe production directories.
5. **Failures Degrade, Never Wedge:** A single bad transmission or hardware fault must cost, at most, that one transmission. It must never stall the queue processor or halt subsequent ingest. See §2 "GPU Memory Safety".

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
* **GPU Memory Safety (Whisper / CUDA):**
  * **A CUDA OOM is reported asynchronously**, at a *later* CUDA call — frequently outside the function that triggered it. Never rely on a single `try/except` around generation to reclaim memory; that is exactly how the pipeline wedges (allocator keeps its reserved blocks → every following file OOMs).
  * `TranscriptionEngine.release_gpu_memory()` is called before **every** `transcribe()` and on **every** failure path, and `QueueProcessor._process_file` reclaims in its own handler because that is where the async OOM actually surfaces. **Do not optimise these away.**
  * On OOM, `_transcribe_chunk()` retries **once** with greedy decoding (`num_beams=1`) and then raises a typed `TranscriptionOutOfMemoryError`. Only OOM is retried; genuine errors must not be masked.
  * **Never remove `output_scores=True`** from the Whisper `generate()` kwargs to reduce VRAM. `transformers` sets `sequences_scores = None` when `output_scores` is False (see `generation/utils.py`), which silently reports confidence `0.0` for *every* beam-search transcription. Bound peak memory via the retry ladder instead, not by dropping score collection.
  * `load_ner_model()` must honour `model.device` from config. It previously seized the GPU (`device=0`) whenever CUDA existed, which meant setting `model.device: cpu` relieved nothing.
* **SQLite Query Planning:**
  * Use `_not_deleted()` (`LogEntry.is_deleted.is_not(True)` → `is_deleted IS NOT 1`) — **never** `is_(False)` or `== False`.
  * On the live DB (261k rows, 2-day range) `IS NOT 1` keeps the planner on `idx_timestamp` at **3.8 ms**; `IS 0` falls back to the low-selectivity `ix_log_entries_is_deleted` and full-scans at **602.8 ms**. Both return identical rows.
  * Never inherit a predicate choice from a `main`-era commit without checking `EXPLAIN QUERY PLAN` against a real DB.

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

### Claim Verification (Mandatory)
Models hand work to each other via summaries, and summaries drift. Before acting on **any** inherited claim:
* Verify it against the real source, the real DB, or the real library — **not** against the summary. A stated benchmark number, a schema shape, or a library guarantee is a hypothesis until checked.
* Frontend test counts in this document's history have been quoted as fully green while the suite in fact carries pre-existing environment failures. Re-run and confirm; do not repeat a quoted count.

---

## 4. Multi-Machine Development Conventions

* **Ubuntu Live Node runs in DOCKER, not natively:**
  * The instance at `~/Desktop/projects/scanscribe` runs via `docker compose`. The `scanscribe` command is a thin compose wrapper (`start` / `stop` / `restart` / `logs` / `update`), and `update` performs `docker compose up -d --build`.
  * **The host virtualenv is irrelevant.** Do not burn time debugging host Python dependencies, `pip`, or `uv` for this node — a `venv/` or missing `.venv` on the host tells you nothing about the running service. Check `docker ps` first.
  * `docker-compose.yml` **bind-mounts `./app`** (alongside `./data`, `./config.yml`, `./models`, `./logs`, `./ingest`), so application code changes take effect on container **restart** — no image rebuild required for app edits.
  * `docker/entrypoint.sh` runs `alembic upgrade head` on every container boot.
  * **Known defect — no `alembic_version` stamp:** that instance's schema was created by the app's own table initialisation, so Alembic has never recorded a revision (there is no `alembic_version` table in any of its databases). Schema and code are consistent today, but a future revision will attempt a from-base upgrade and collide with tables that already exist. It needs a one-time `alembic stamp <current-head>` before the next real migration.
  * Restarts must not kill in-flight transcription — stop the queue processor cleanly (the log should show the drain of active tasks) rather than hard-killing the container mid-transcribe.
  * The DB is large (~261 MB). DDL changes are cheap to reverse but not instant; take a copy of `data/scanscribe.db` before a migration anyway.
* **Windows Dev Workstations:** When developing on non-Ubuntu machines, live radio SDR hardware will not be present. Run tests using synthetic fixtures in `tests/` and verify unit/integration test suites.
* **Configuration:** Never commit sensitive tokens, API keys, or live `.env` / `config.yml` files. Keep `.env.example` and `config.yml.example` updated with any new required keys.
* **Untracked host files are not defects:** on a live node you may see untracked `scanscribe` (the CLI), `config.yml.personal.backup`, and rebuilt `app/frontend/dist/assets/*`. These are normal; leave them alone.

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

5. **Never Resolve a Blocked Checkout by Discarding Work:**
   - If a dirty working tree blocks a `git switch`, the changes may exist **nowhere else** — verify before touching them: `git log --all --oneline --find-object=$(git hash-object <file>)`. An empty result means that content has never been committed on any branch, tag, or remote.
   - Prefer `git stash push` (recoverable) over `git checkout -- .` / `reset --hard` (permanent). A stash gives an identical clean tree and stays reversible.
   - Never `--force` a checkout over uncommitted work without an explicit, informed instruction from the user.

6. **Verify Pushes Against the Remote:**
   - A successful `git push` message is not proof. Confirm with `git ls-remote origin refs/heads/<branch>` and, where available, the hosting API. Do not report a ref as updated from the local ref alone.
