---
name: arch_findings_ledger_race
description: "The findings-ledger \"concurrent-append flake\" was a REAL data-loss race (flock on an inode-rotated file); fixed 2026-06-14 with a stable sidecar lock. Surfaced by remote-first testing."
metadata: 
  node_type: memory
  type: project
  originSessionId: 154fb558-ad8d-47e9-b9fa-cbac688b2031
---

**`test_concurrent_append_no_torn_lines` was NEVER a flake — it was a real concurrency
data-loss bug.** Prior sessions (and prior memory) mislabeled it "transient, passes on
re-run / deselect it." WRONG: it fails **deterministically on the remote 180** (git/Ubuntu
thread timing) and only *appeared* intermittent on the Mac. The remote-first workflow
([[feedback_remote_first_dev]]) is exactly what surfaced it — the canonical "passes here,
breaks there" case.

**Root cause:** `FindingsLedger` write methods (`append_from_report`, `set_verdict`,
`set_dispatch_state`) acquired `fcntl.flock` on `self.path` (`findings_log.jsonl`), but
`_write_all_unlocked` does `tmp.replace(self.path)` — which **rotates the inode**. flock
binds to the inode, so the lock did NOT serialize writers across the replace: a concurrent
writer locked the unlinked OLD inode, read a STALE snapshot, merged into it, and clobbered
the first writer (test recorded 5 of 12 findings). The shared-`.tmp` `FileNotFoundError` was
only the visible symptom; the lost writes were the inode-rotation race. (Note: a unique-tmp-
name fix alone — my first instinct — would have fixed the symptom but NOT the data loss; the
operator's "95% confident" gate caught that before I shipped the wrong fix.)

**Fix (commit `8e7d5ed`, remote-first):** flock a **STABLE sidecar lock file** `_lock_path()`
(OS-temp, keyed by `sha256(resolved data path)[:16]`, never renamed/committed) instead of the
data file — same proven flock-per-open mutual exclusion, but on an inode that never rotates.
`_write_all_unlocked` also uses a unique tmp name (defense). Concurrent test 5/5 pass (was
3/3 fail); findings_ledger 30/30; full remote suite **533 passed, 0 failed** (first fully-green
remote run after the git-2.25 fixture fix `a46990e`).

**Why it matters beyond the test:** the ledger records acceptance findings + auto-dispatch
candidates. Concurrent appends become common under **wave parallelism** (Phase 2+ runs
concurrent BLs/dispatch all writing findings) — this race would silently drop real bugs.
Relates to [[arch_inventory_run_and_wave_proposal]] (wave execution), [[feedback_honest_verification]].
