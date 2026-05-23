---
name: arch-run-identity
description: I-4 — a run has exactly one run_id, minted in exactly one place, threaded through every artifact
metadata:
  type: project
---

`run_id` is the foreign key joining lock metadata, trace dirs, retrieval logs, disk state, archive dirs, and logs. Today most of these honor it, but trace dirs and the `webapp/backend/logs/orchestrator/<timestamp>/` directory still use their own identity schemes (per-agent task_id, per-launcher timestamp).

**Why:** A7 + B14 + B15 each invented their own identity convention before they were unified through the `run_id` parameter. The Sprint-2 hardening pass mostly stitched these together, but the gaps (trace dir path doesn't include run_id; log dir uses timestamp) mean cross-artifact joins still require scans rather than lookups.

**How to apply:**
- Router (`projects.py:run_brief`) is the ONLY place that mints run_id. Anything else accepts it as a parameter.
- New artifacts MUST include `run_id` in their identifying path or key — not as a metadata field only.
- Target future state: `traces/<repo>/<run_id>/<role>-<bl>-<task_id>/`, `logs/orchestrator/<run_id>/run.log`. Today's flat structure works but requires `find` to join.

Compliance audit (today): lock metadata ✓, orchestrator-internal ✓ (A7 unified), trace `harness_sha` ✓ (B14), state file ✓, archive dir ✓ (B15). Trace dir path ⚠ (only task_id), log dir ⚠ (only timestamp).

Source: `ARCHITECTURE_INVARIANTS.md` § I-4.
