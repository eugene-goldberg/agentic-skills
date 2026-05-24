---
name: arch-gate-throughput
description: Open structural finding — playwright gate runs 79 e2e tests with 1 worker, PRE+POST per BL, ~80-160 min per BL. Industry-standard mitigations (workers, sharding, TIA, tiered gates) not yet applied. Filed as A28..A31 in DESIGN_SHORTCOMINGS.md.
metadata:
  type: project
---

# Regression-gate throughput is the dominant sprint-time cost

## The fact

The brownfield target's regression gate runs the full Playwright e2e suite
(~79 tests across 10 spec files: items, admin, login, sign-up,
user-settings, reset-password, notifications, api-keys, api-keys-qa,
bl0011-rbac-ui) twice per BL — once against `agent_branch` baseline
(PRE), once with the engineer's commit applied (POST). At 1 playwright
worker, this is **~80-160 min of gate wall-time per BL**.

For an 11-BL sprint like `documents` / `documents_1`, gate time alone
projects to **17-33 hours** even with zero retries. Every retry doubles
the BL's gate cost. This dominates sprint duration and operator-time
metrics; it is the single biggest throughput lever in the current
framework.

## Why this matters

The slow gate produces several second-order pathologies:
- Encourages skip_gate=true operator overrides → defeats the
  regression-protection contract
- Amplifies any infra noise (a flaky test on retry 1 means another
  80-160 min of gate work)
- Makes A25-class extractor improvements harder to validate because
  iteration is slow
- Sprint-completion observability lags by hours, delaying the
  doctrine-meta loop

## Industry comparison

What we do is at the *most conservative end* of the gating spectrum:
- Most CI shops use `--workers 4` to `--workers 8` (3-8× speedup)
- Mature shops shard across N runners (`--shard i/N`) for another N×
- Test Impact Analysis (TIA) tools (Bazel test cache, Launchable,
  Touca, Nx affected, Microsoft Test Impact) run only tests touching
  changed code paths — typically 5-20× reduction
- Tiered gates: PR runs fast smoke (≤3min), merge candidate runs
  integration (~15min), full e2e async post-merge (~60min)
- AI coding agents (Devin, SWE-agent, GitHub Copilot Workspace,
  Cursor, Aider) typically defer e2e to the repo's existing CI rather
  than gating on it inline — humans or downstream pipelines catch
  regressions

## Open items in the ledger

See [[arch-design-shortcomings]] entries A28..A31:

- **A28** — Increase playwright `--workers` from 1 to 4 in
  `regression_gate.sh`. ONE-LINE FIX. Expected 3-4× speedup.
- **A29** — Cache PRE result keyed by `agent_branch` HEAD SHA. Don't
  re-run PRE if the baseline hasn't moved since the last sprint. 2× per
  sprint after the first BL.
- **A30** — Test Impact Analysis: parse engineer's
  `git diff --name-only` → map to affected spec files (heuristic or
  explicit mapping) → run only those. 5-20× reduction on focused
  changes.
- **A31** — Tiered gate: per-BL runs fast unit+smoke; full e2e fires
  once at end-of-sprint or async post-merge. Restructures the contract
  but is the right long-term shape.

## When to apply

Defer until the current crew-quality fixes (A19, A20, A21, A22, A24,
A25a/b, A26, WI3A) have been validated by at least one green-path
sprint. The optimizations are correctness-neutral; they only change
timing. Once we have ANY green sprint, A28 (1-line fix) is the highest
ROI follow-up.

## Architect note (2026-05-24)

The operator was explicitly oriented to this gap during the
`documents_1` sprint when gate PRE phase alone projected to >40 min.
Filing here so future sessions inherit the awareness without needing
to re-derive the math.
