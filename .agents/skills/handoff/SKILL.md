---
name: handoff
description: >-
  Automates the inter-model and cross-machine handoff workflow for ScanScribe.
  Use when wrapping up a coding session, switching AI models, or preparing to sync
  work between Windows and the live Ubuntu node by updating ACTIVE_CONTEXT.md.
---

# Agent Handoff Protocol

This skill executes a clean, structured handoff so the next agent (regardless of which model or machine it runs on) can immediately understand the latest changes, live environment impact, and active priorities without repeating mistakes or undoing refactor work.

## When to Run This Skill
- The user says "handoff", "wrap up", "leaving notes for the next model", or "switching to Ubuntu / other machine".
- Completing a multi-file feature or bug fix.
- Reaching the end of a long task before ending the session.

---

## Step-by-Step Execution Procedure

### Step 1: Inspect Changes
Run `git status` and inspect the diff:
```bash
git status --short
git diff --stat
```
Identify:
- Which files were created, modified, or deleted.
- Whether any database schemas, API contracts, or configuration files were touched.

### Step 2: Run Verification Checks
Ensure no regressions were introduced:
```bash
pytest tests/
```
If frontend files were modified:
```bash
cd app/frontend && npm run typecheck
```
Record the test results for the handoff entry.

### Step 3: Check Live Ingestion & Concurrency Impact
Evaluate if any of the changes could affect the live real-time ingestion loop on the Ubuntu server:
- Were audio ingestion queues, Silero VAD, or Whisper worker loops touched?
- Were database locks or schemas modified?
- Are any new environment variables or configuration keys required in `.env` / `config.yml`?

### Step 4: Update `ACTIVE_CONTEXT.md`
Read [`ACTIVE_CONTEXT.md`](file:///a:/Scanscribe_Projects/scanscribe/ACTIVE_CONTEXT.md) and append a new structured entry to **Section 3 (Model Handoff Log)** following this format:

```markdown
### [YYYY-MM-DD HH:MM] | <Current Model Name> (<Workstation: Windows/Ubuntu>)
- **Work Performed:** <Bullet points summarizing what was added, changed, or fixed>
- **Live Ingestion Impact:** <Explicit statement on impact to real-time audio pipeline or None>
- **Gotchas & Warnings for Next Model:** <Subtle details, known limitations, or critical reminders>
- **Verification Performed:** <e.g., pytest 14/14 passed, manual audio test passed>
- **Next Tasks / Unfinished Work:** <What the next model should tackle next>
```

Also review **Section 2 (In-Progress Features & Next Objectives)** and check off completed items or add newly discovered tasks.

### Step 5: Remind the Human Developer to Push
Advise the user to commit and push their changes:
```bash
git add .
git commit -m "feat/fix: <summary>"
git push
```
This ensures the live Ubuntu server or the next workstation receives both the code and the updated [`ACTIVE_CONTEXT.md`](file:///a:/Scanscribe_Projects/scanscribe/ACTIVE_CONTEXT.md) in a single pull.
