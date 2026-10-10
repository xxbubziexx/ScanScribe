# Phase 2 — Merge `snapshot` → `main`

**Status:** PLANNED · **Parent:** [branch_consolidation_master_plan.md](branch_consolidation_master_plan.md)
**Prerequisite:** Every Phase 1 exit check has passed.
**Objective:** `main` ends up with exactly the content of `snapshot` (plus any ported fixes), keeps its full history, and needs **no force-push**.

---

## Strategy

`snapshot` is a full 5-phase refactor of the code. A normal 3-way merge with `main`'s 4 unique pre-refactor commits would produce many conflicts in files that no longer have the same structure. The plan is:

1. **Audit** the 4 `main`-only commits and port anything still needed onto `snapshot` (as normal commits that pass the tests).
2. **Merge `main` into a staging branch with `-s ours`.** This records `main`'s history as merged while keeping the tree exactly as `snapshot` has it.
3. **Fast-forward `main`** to that merge commit. This is a normal push, not a force-push.

Result: `git log main` contains both histories, and `main`'s files equal the audited `snapshot`.

> [!WARNING]
> `-s ours` discards the *content* of `main`-only commits. That is why step 2.1 (the audit) is mandatory. Anything not ported in 2.1 will not be on `main`. It stays recoverable only through the Phase 1 archive tag.

---

## Steps

### 2.1 Audit `main`-only commits (content parity)
For each commit, run `git show <sha>` and compare against `snapshot`. Record a verdict: **present / obsolete / port**.

| Commit | What to check | Expected verdict |
|---|---|---|
| `0f8463f` dtype fix | `torch_dtype` line in `transcription_engine.py` | present (already verified) |
| `f654db7` DeepSeek routing | `ollama_event_routing.py`, `ollama_worker.py`, `master_event_header_ollama.py`, `event_summary_ollama.py`, `events_worker.py` | **depends on Open Decision #1** |
| `01169cd` Tailwind fallback | Jinja templates are gone on `snapshot`, so the CSS is obsolete. **Check the `app/models/event.py` hunk (+37/-?)** and confirm the model change exists on `snapshot` or through an Alembic migration. | obsolete, except the model hunk needs a check |
| `42ba4e8` Events pipeline optimization | Diff `config.py`, `database.py`, `events_worker.py`, `ner_service.py`, `ollama_event_routing.py` against `snapshot`. The `entity_*` modules already exist. | mostly present, confirm |

Any port is a separate commit on `snapshot`. It must follow AGENTS.md: Alembic for schema changes, no inline imports, no bare excepts, async-safe code.

### 2.2 Pre-merge gate (on `snapshot`)
- [ ] Fix the `except Exception: pass` blocks in `app/server_control.py::cmd_uninstall` (AGENTS.md §2).
- [ ] README pass: replace the outdated Docker-wizard prerequisites/setup sections with the native installer flow, and point Docker users to `docker/README.md`.
- [ ] `python -m pytest tests/` is green (baseline: 77 passed).
- [ ] Frontend build/typecheck passes, if the frontend was touched.
- [ ] `alembic upgrade head` runs cleanly on (a) a fresh DB and (b) a copy of a legacy DB.

### 2.3 Create the merge on a staging branch
```bash
git fetch --all --prune
git switch -c release/promote-snapshot origin/snapshot
git merge -s ours --no-ff origin/main \
  -m "Merge legacy main into snapshot (history only; snapshot supersedes main)"
git diff origin/snapshot --stat      # MUST be empty: the tree equals snapshot
python -m pytest tests/
git push -u origin release/promote-snapshot
```
Optionally, open a PR `release/promote-snapshot → main` on GitHub for a final review.

### 2.4 Fast-forward `main`
```bash
git switch main
git pull --ff-only origin main
git merge --ff-only release/promote-snapshot
git push origin main                  # normal push, no --force
```
If `--ff-only` fails, someone pushed to `main` after Phase 1. **Stop**, re-archive, and redo 2.1.

### 2.5 Tag the release
```bash
git tag -a v2.0.0 -m "ScanScribe 2.0: modular architecture, unified DB, native installer + CLI"
git push origin v2.0.0
```

### 2.6 Post-merge verification
- [ ] `https://raw.githubusercontent.com/xxbubziexx/ScanScribe/main/install.ps1` returns 200 (it was a 404 before).
- [ ] Same check for `install.sh`, `uninstall.ps1`, and `uninstall.sh`.
- [ ] The landing-page one-liner URLs match the real repo path and casing (`xxbubziexx/ScanScribe` vs `scanscribe`). GitHub redirects case differences for repos, but confirm the raw URLs resolve.
- [ ] A fresh clone of `main` runs `pytest` green.
- [ ] GitHub's default branch is still `main`.

### 2.7 Ubuntu live node rollout (only if it tracks `main`)
Follow AGENTS.md §4. Schedule a low-traffic window, then:
```bash
scanscribe stop            # or the existing service manager
git pull --ff-only
alembic upgrade head
scanscribe start
```
Watch `ingest/` drain and `scanscribe logs` for 15+ minutes. No audio may be dropped (Prime Directive).

### 2.8 Housekeeping
- Apply Open Decision #4: keep `snapshot` as the dev branch, or delete it.
- Consider GitHub branch protection on `main` (require a PR and block force-push).
- Add a handoff entry to `ACTIVE_CONTEXT.md`.

---

## Exit checks
- [ ] `git diff main origin/snapshot` is empty (or contains only the intended ports).
- [ ] `git merge-base --is-ancestor archive/main-legacy-2026-10-10 main` returns true (legacy history is kept).
- [ ] Tag `v2.0.0` is pushed.
- [ ] Raw installer URLs return 200.
- [ ] The live node is healthy (if applicable).

## Rollback
- **Before 2.4:** delete `release/promote-snapshot`. Nothing changed on `main`.
- **After 2.4:** prefer `git revert -m 1 <merge-sha>` on `main` (a normal push). Force-resetting to `archive/main-legacy-2026-10-10` is a last resort and needs explicit approval.
