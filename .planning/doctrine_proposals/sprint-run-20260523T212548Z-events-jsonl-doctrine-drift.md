# Proposal: Resolve `events.jsonl` doctrine-vs-reality drift in trace archive

**Sprint:** run-20260523T212548Z-5bfff3
**Topic:** events-jsonl-doctrine-drift
**Invariant:** I-2
**Class:** enforcement-gap
**Direction:** new-rule
**Evidence count:** 12

## Summary

The doctrine-meta-agent's `SKILLS.md` (Inputs §1) instructs the agent to read
`webapp/backend/traces_archive/<run_id>/<trace>/events.jsonl` and to scan it
for `phase=doctrine_check`, `phase=regression_gate`, etc. No `events.jsonl`
file exists in any sealed trace dir in this sprint, nor in any live trace
dir on disk. The harness writes `stream.jsonl` instead, which carries
Claude SDK transport messages plus a handful of `_meta phase=...` lines.
This is a doctrine-vs-reality drift: the meta-agent's binding rulebook
references an artifact the harness does not produce. The meta-agent can
still partially operate by reading `stream.jsonl`, but every claim a
reviewer might want to verify against "the events file" is unrooted. Fix
is structural, not per-instance: either the doctrine should be updated to
reference `stream.jsonl` and a clear extraction predicate, or the
TraceWriter should emit a phase-only `events.jsonl` derived from
`stream.jsonl` so the meta-agent's stated input contract holds.

## Evidence

Each citation is a directory listing or absent-file observation; the file
inventory per trace was produced by walking the sealed archive and
listing each subdir.

- `traces_archive/run-20260523T212548Z-5bfff3/20260523T212734Z-engineer-BL-0001-e3799ce1364a/` — directory contents: `meta.json`, `retrieval.jsonl`, `stream.jsonl`. No `events.jsonl`.
- `traces_archive/run-20260523T212548Z-5bfff3/20260523T213002Z-engineer-BL-0002-68bcf05226c3/` — `meta.json`, `retrieval.jsonl`, `stream.jsonl`. No `events.jsonl`.
- `traces_archive/run-20260523T212548Z-5bfff3/20260523T213220Z-engineer-BL-0003-1e1ac27741fb/` — same.
- `traces_archive/run-20260523T212548Z-5bfff3/20260523T213515Z-engineer-BL-0004-39a07842eb91/` — `meta.json`, `stream.jsonl`. Neither `events.jsonl` nor `retrieval.jsonl`.
- `traces_archive/run-20260523T212548Z-5bfff3/20260523T213539Z-qa-BL-0004-36b05cc6662f/` — `meta.json`, `retrieval.jsonl`, `stream.jsonl`. No `events.jsonl`.
- `traces_archive/run-20260523T212548Z-5bfff3/20260523T220006Z-scorer-BL-0004-ce51130eb126/` — same.
- `traces_archive/run-20260523T212548Z-5bfff3/20260523T220351Z-engineer-BL-0005-12d0a7c1934d/` — same.
- `traces_archive/run-20260523T212548Z-5bfff3/20260523T220433Z-qa-BL-0005-2f5090343d0e/` — same.
- `traces_archive/run-20260523T212548Z-5bfff3/20260523T222755Z-scorer-BL-0005-a6cb41773e32/` — same.
- `traces_archive/run-20260523T212548Z-5bfff3/20260523T223104Z-engineer-BL-0006-25a87d49309c/` — same.
- `traces_archive/run-20260523T212548Z-5bfff3/20260523T235547Z-qa-BL-0006-9b2fe89bcc67/` — same.
- Live (non-archived) trace tree `webapp/backend/traces/`: a recursive
  `find … -name events.jsonl` returns zero results. The artifact named in
  the meta-agent's input contract is produced nowhere on the filesystem.

## Proposed change

Pick exactly one of the two options below; do not implement both.

**Option 1 (cheap, recommended): update the meta-agent's input contract.**
Edit `skills/doctrine_meta/.../SKILLS.md` §Inputs to:

> Each trace subdirectory holds:
> - `stream.jsonl` — Claude SDK transport events plus `_meta` records
>   (filter for `type == "_meta"` and inspect `phase`).
> - `retrieval.jsonl` — every retrieval / graph / target tool call …
> - `meta.json` — task_id, role, BL, harness_sha, prompt, …

Then add an extraction predicate the meta-agent must apply:
`phase_events = [r for r in stream.jsonl if r.get("type")=="_meta" and r.get("phase")]`.
This grounds every future citation in a real file.

**Option 2 (more work, more robust): have TraceWriter emit a derived
`events.jsonl`.** On every `_meta`-typed write to `stream.jsonl`, also
append the same record (sans large payload fields) to a sibling
`events.jsonl`. This keeps the meta-agent's existing contract intact and
makes phase-event lookup O(L_events) instead of O(L_stream). Recommend
deferring Option 2 until a separate need for fast phase-only scans
materializes; Option 1 closes the drift now.

## Risk

- (Option 1) Updating the doctrine touches `SKILLS.md` files that are
  themselves under the meta-agent's `forbidden_targets` clause — so this
  edit must be operator-applied, not agent-applied. The proposal is
  consistent with that: meta-agent never edits its own SKILLS.md.
- (Option 2) Doubling phase events to two files risks divergence if one
  writer flushes and the other crashes. Crash-consistency must be
  asserted.
- Either option, low risk: any in-flight meta-agent run that already
  reads `stream.jsonl` keeps working.

## Mitigations

- For Option 1: the operator applies the SKILLS.md edit and bumps the
  meta-agent's `metadata.version` from `0.1-brownfield` to `0.2-brownfield`
  so the change is visible in artifact provenance.
- For Option 1: add a one-line precondition check in
  `_doctrine_meta_flow` that fails fast if any trace subdir is missing
  `stream.jsonl`, surfacing the drift loudly on day 1 instead of
  meta-agent producing empty output.
- For Option 2: TraceWriter writes `events.jsonl` AFTER `stream.jsonl` is
  flushed, and the meta-agent treats `events.jsonl` as best-effort,
  falling back to `stream.jsonl` filtering on absence.

## Test

Synthetic harness invocation:

1. Run a short brownfield brief (1 BL, e.g. `BL-0001`) on the configured
   target with `run_doctrine_meta=true`.
2. Assert: for each trace subdir in `traces_archive/<run_id>/`,
   `(subdir / "stream.jsonl").exists() is True` AND, under Option 1,
   the meta-agent's `done` event reports `traces_read_count == N` with
   `N == #subdirs`; under Option 2, `(subdir / "events.jsonl").exists()
   is True` AND `events.jsonl` line count ≥ count of `_meta` lines in
   `stream.jsonl`.
3. Negative test: corrupt one `stream.jsonl` (truncate mid-line). Confirm
   meta-agent marks it `traces_truncated_count += 1` and continues.

Test lives at `webapp/backend/tests/test_doctrine_meta_inputs.py` (new).

## Rollback

- Option 1: revert the SKILLS.md edit; bump `metadata.version` back to
  `0.1-brownfield`. Meta-agent reverts to its prior (broken) input
  contract. No data loss.
- Option 2: delete the `events.jsonl` derivation block from TraceWriter;
  delete any sidecar `events.jsonl` files (they are gitignored under
  `traces/`). Meta-agent falls back to Option-1 behavior.
