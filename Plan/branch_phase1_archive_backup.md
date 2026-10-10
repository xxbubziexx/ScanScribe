# Phase 1 — Archive & Back Up Legacy Branches

**Status:** PLANNED · **Parent:** [branch_consolidation_master_plan.md](branch_consolidation_master_plan.md)
**Objective:** Freeze the current `main` and `ui-upgrade-react` so they can be recovered exactly, before anything else changes.
**Risk:** None. Only adds tags and a local bundle file. No branch is moved or deleted in this phase.

---

## Why tags (not just backup branches)

Branches move, and someone can accidentally commit to `main-legacy`. Annotated tags are immutable references with a message and date. They are the right tool for an archive. Backup branches are optional on top of tags.

## Steps

### 1.1 Sync and record exact SHAs
```bash
git fetch --all --prune
git rev-parse origin/main               # expect 4692e50...
git rev-parse origin/ui-upgrade-react   # expect 04755d3...
```
If either SHA differs from the expected value, **stop** and re-run the analysis in the master plan. Someone pushed in the meantime.

### 1.2 Create annotated archive tags
```bash
git tag -a archive/main-legacy-2026-10-10 origin/main \
  -m "Archive: main before snapshot promotion (pre-refactor codebase). Tip 4692e50."
git tag -a archive/ui-upgrade-react-2026-10-10 origin/ui-upgrade-react \
  -m "Archive: ui-upgrade-react before consolidation. Contains 50019a9 (root scanscribe bash helper)."
git push origin archive/main-legacy-2026-10-10 archive/ui-upgrade-react-2026-10-10
```

### 1.3 Offline backup (git bundle)
This protects against GitHub-side mistakes, such as an accidental force-push or a deleted repo.
```bash
git bundle create ../scanscribe-backup-2026-10-10.bundle --all
git bundle verify ../scanscribe-backup-2026-10-10.bundle
```
Store the bundle outside the repo, for example on the Ubuntu node or in cloud storage. Do not commit it.

### 1.4 Optional: human-friendly backup branches
```bash
git push origin origin/main:refs/heads/legacy/main-pre-refactor
git push origin origin/ui-upgrade-react:refs/heads/legacy/ui-upgrade-react
```

### 1.5 Confirm `ui-upgrade-react` has nothing unique worth keeping
- Diff `50019a9`'s root `scanscribe` script against `bin/scanscribe` + `app/cli.py` on `snapshot`.
- If it has any behavior that's missing on `snapshot`, note it under a follow-up section in the master plan. Do **not** port it in this phase.

### 1.6 Optional, needs a decision: retire the remote `ui-upgrade-react` branch
Do this only after 1.2 is pushed and verified, and only if Open Decision #3 says to delete it:
```bash
git push origin --delete ui-upgrade-react
git branch -d ui-upgrade-react
```

---

## Exit checks (all must pass before Phase 2)

- [ ] `git ls-remote --tags origin "archive/*"` lists both tags.
- [ ] `git rev-parse archive/main-legacy-2026-10-10^{commit}` = `4692e50…`
- [ ] `git rev-parse archive/ui-upgrade-react-2026-10-10^{commit}` = `04755d3…`
- [ ] `git bundle verify` succeeds, and the bundle is stored off-machine.
- [ ] Step 1.5 is done, and its findings are recorded.
- [ ] Handoff entry added to `ACTIVE_CONTEXT.md`.

## Rollback
Nothing to roll back. Tags can be deleted with `git push origin :refs/tags/<name>` if they were created by mistake.
