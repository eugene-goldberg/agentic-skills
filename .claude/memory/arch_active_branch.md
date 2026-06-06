---
name: arch-active-branch
description: "followup-dispatch-ui — pushed @ b0c9b19; A52 fix ebcf4eb committed but UNPUSHED (push first next session). 2026-06-05 evening handoff. Search feature COMPLETE 6/6 + acceptance bug auto-fixed; acceptance SKILLS v0.2 (verified root-cause) shipped+enforced; Team Calendar (Horizon) run aborted cleanly at BL-0001 (auth-break capability wall). NEXT: push ebcf4eb, then decide the Horizon BL-0001 diagnosis."
metadata:
  node_type: memory
  type: project
  originSessionId: 326d1623-34a0-4f02-8c13-b7359c64685d
---

## State at 2026-06-05 (evening)

- **agentic-skills branch:** `followup-dispatch-ui`. **Pushed @ `b0c9b19`.**
  **`ebcf4eb` (A52 fix) is committed but UNPUSHED → push first next session.**
- **Target:** `full-stack-fastapi-template` @ `agentic-skills-work-search_and_discovery`
  `e74ac82` — **Search & Discovery COMPLETE (6/6 BLs)** + the acceptance
  browse-mode fix merged. Calendar/Horizon NOT merged. Broken Horizon BL-0001
  work isolated on `agent/fd5263480b39` (RED gate — DO NOT merge).
- **Tests:** 297 passed (`cd webapp/backend && .venv/bin/python -m pytest tests/`),
  deselect `test_findings_ledger.py::test_concurrent_append_no_torn_lines`
  (pre-existing parallel-exec flake; passes in isolation).
- **Clean:** Docker = Milvus only, worktrees=1, no active run, lock clear.
  uvicorn live on `ebcf4eb` (PID ~97469). ~96 GB disk free.

## What this session shipped (all pushed except ebcf4eb)
1. **3 deferred harness fixes** (`4773e67`): A39 playwright node-id expansion,
   A49 transient-marker annotation + explicit `--retries=2`, A45 wedge-proof
   (outer `except` backstop on `run_brief` + engineer-flow wrap). See
   [[arch-harness-hardening]].
2. **Search feature finished**: BL-0006 re-run → merged_full (6/6); acceptance
   found a real cross-BL `product_bug` (empty-query smart views → 0 rows);
   confirmed → ABL-0021 dispatch → fixed (browse mode `4ac7e27`) → merged →
   ledger synced. **Full deliver→diagnose→dispatch→fix→merge loop validated.**
3. **ABL-0015 Calibration Campaign plan** (`79bc978`, governance entry 24).
4. **Acceptance SKILLS v0.2 + binding enforcement** (`b0c9b19`). See
   [[arch-acceptance-v02]].
5. **A52 found + fixed** (`ebcf4eb`, UNPUSHED) — see [[arch-horizon-run]].

## ⭐ NEXT SESSION
1. **`git push`** (ebcf4eb).
2. **Decide Horizon BL-0001**: diagnose why its CalendarEvent foundation broke
   login (read `agent/fd5263480b39` diff — likely regenerated `client/*`, model
   relationship/migration, or router registration), then hand-fix + resume
   (`skip_po=True start_bl=BL-0002`) OR re-run OR stop. Full context in
   `CONTINUATION_PROMPT.md` + [[arch-horizon-run]].
3. Consider: a v0.2-style "root-cause before you patch" directive in the
   engineer's `build_gate_fix_prompt` (it chased symptom specs without
   root-causing the auth break).

Other deferred: ABL-0015 calibration Phase-0 (deferral hygiene + precision
report); A49 verdict-flip (operator sign-off); A39 sub-mode 39a (build
conflation); branch consolidation to a trunk.
