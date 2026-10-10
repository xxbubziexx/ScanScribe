# Branch Consolidation Master Plan

**Created:** 2026-10-10 · **Status:** PLANNED (not executed)
**Goal:** Make `main` the single source of truth again, without losing any history.

| Phase | Objective | Plan file | Destructive? |
|---|---|---|---|
| 1 | Archive + back up legacy `main` and `ui-upgrade-react` | [branch_phase1_archive_backup.md](branch_phase1_archive_backup.md) | No (tags + bundle only) |
| 2 | Merge `snapshot` → `main` | [branch_phase2_merge_snapshot_to_main.md](branch_phase2_merge_snapshot_to_main.md) | No force-push. Changes what `main` serves. |

Phase 2 must not start until every Phase 1 exit check passes.

---

## Current state (verified 2026-10-10 via `git fetch --all --prune`)

| Branch | Tip | Relative to `origin/snapshot` |
|---|---|---|
| `origin/main` (GitHub default) | `4692e50` | 5 ahead / 49 behind |
| `origin/snapshot` | `3631c5b` | — |
| `origin/ui-upgrade-react` | `04755d3` | 2 ahead / 5 behind |

- Merge base of `main` and `snapshot`: `bac8300` (2026-04-24, "Fixed dashboard console time issue").
- No tags exist in the repo yet.

### Commits on `main` that are not on `snapshot` (by patch-id, `git cherry`)

| Commit | Subject | Quick parity check on `snapshot` |
|---|---|---|
| `0f8463f` | Fixed dtype mismatch (CPU float32 / GPU float16) | **Already present.** Same `torch_dtype` line on both branches. |
| `f654db7` | DeepSeek API support for worker/master routing LLMs | **Missing.** No `deepseek` references on `snapshot`. Needs a decision. |
| `01169cd` | Tailwind fallback CSS for Jinja templates | **Likely obsolete.** `snapshot` has no `app/templates/` (replaced by the React SPA). Also touches `app/models/event.py`, which needs a check. |
| `42ba4e8` | Optimized events pipeline | **Partly present.** `entity_normalize.py` and `entity_time.py` exist on `snapshot`. Changes to `config.py`, `database.py`, and `events_worker.py` need a diff review. |
| `4692e50` | AGENTS.md / ACTIVE_CONTEXT.md | Equivalent commit already on `snapshot` (`adfa29c`). |

### Commits on `ui-upgrade-react` that are not on `snapshot`

| Commit | Subject | Note |
|---|---|---|
| `50019a9` | Root-level `scanscribe` bash helper (83 lines) | Probably superseded by `bin/scanscribe` + `app/cli.py`. Confirm before archiving. |
| `04755d3` | AGENTS.md / ACTIVE_CONTEXT.md | Equivalent already on `snapshot`. |

---

## Why this matters

- The landing-page one-liner fetches `.../main/install.ps1`. **`install.ps1` does not exist on `main`**, so the one-liner currently returns a 404.
- GitHub visitors see the pre-refactor codebase on `main`.

---

## Open decisions (need answers before Phase 2)

1. **DeepSeek support (`f654db7`):** port it to the refactored LLM routing, or drop it? (OpenRouter may already cover this use case.)
2. **Ubuntu live node:** which branch does it pull from? If it pulls `main`, Phase 2 changes live code on the next pull and needs a planned restart plus `alembic upgrade head` (see AGENTS.md §4).
3. **After archiving:** should the remote `ui-upgrade-react` branch be deleted (the tag keeps it recoverable), or kept?
4. **Role of `snapshot` after the merge:** keep it as the staging/dev branch, or retire it and work on feature branches off `main`?

## Known issues to fix before Phase 2 (pre-merge gate)

- `app/server_control.py::cmd_uninstall` has several `except Exception: pass` blocks, which AGENTS.md §2 forbids. They should log a warning with context instead.
- `README.md` on `snapshot` is inconsistent. The "Prerequisites" and "Fast Interactive Setup" sections still describe a Docker-based setup wizard, but `install.ps1` / `install.sh` are now native (uv + `.venv`). This needs a docs pass so `main` doesn't ship contradictory instructions.

## Rollback (whole effort)

Phase 1 creates immutable tags. If anything goes wrong in Phase 2:
```bash
git push origin archive/main-legacy-2026-10-10:refs/heads/main --force-with-lease
```
Use this only with explicit approval, because it is a force-push to the default branch.
