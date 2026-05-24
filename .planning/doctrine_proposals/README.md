# Doctrine Proposals

This directory is the canonical home for proposals written by the
**doctrine-meta-agent** (see
`skills/brownfield/brownfield-production-incremental-doctrine-meta/SKILLS.md`).

Each file is one proposal. Proposals are **markdown only**, **operator-gated**,
and **never auto-applied**. They are evidence the framework has noticed a
recurring pattern across one or more sprints and is asking whether the
doctrine should change in response.

This file (`README.md`) and `.gitkeep` are committed so the directory exists
on a fresh clone. All other `*.md` files in this directory are gitignored —
the proposals themselves are session-local until the operator decides to
promote one. Promotion = the operator pulls the proposal's recommended change
into the canonical doctrine document (`ARCHITECTURE_INVARIANTS.md`,
`CLAUDE.md`, a `SKILLS.md`, or a `doctrine_validator.py` rule) by hand. The
proposal file MAY then be deleted, or moved to a `accepted/` subdirectory
for audit-trail.

## Lifecycle

```
sprint completes
  └─→ orchestrator runs _doctrine_meta_flow (B-3)
        └─→ meta-agent reads traces_archive/<run_id>/
              └─→ writes <run_id>-<topic-slug>.md HERE
                    └─→ orchestrator.doctrine_meta.proposals SSE event surfaces count
                          └─→ (later) framework-reviewer (Batch C) reads and challenges
                                └─→ (later) operator approves OR rejects
                                      └─→ on approve: change applied BY HAND to canonical doc
```

## Schema

Every proposal MUST follow the skeleton in the doctrine-meta-agent's
SKILLS.md §"Proposal Schema". Key requirements:

- Top of file declares `Invariant:` (I-1..I-7 or UNCLASSIFIED), `Class:`
  (from I-6 taxonomy), `Direction:` (tighten / loosen / new-rule /
  new-invariant), and `Evidence count:` (integer).
- An `## Evidence` section listing `(trace_path, event_id, observed_value)`
  triples that the framework-reviewer can re-open and verify.
- `## Risk` enumerating what could go wrong if the proposal lands.
- `## Mitigations` pairing each risk with a concrete mitigation. Risks
  without mitigations = proposal incomplete.
- `## Test` naming a runnable test that proves the change has the intended
  effect.
- `## Rollback` describing how to revert.

Proposals that fail this schema MAY land on disk (the validator inside
`_doctrine_meta_flow` is lenient — it only checks for `## Evidence` and a
`traces_archive/` citation). They will be flagged `valid=false` in the
`orchestrator.doctrine_meta.proposals` event, and the framework-reviewer
(once it exists, Batch C) is expected to block them.

## What does NOT belong here

- Doctrine proposals from humans. Those go through the normal governance
  flow: a ledger entry in `DESIGN_SHORTCOMINGS.md` and a tracked plan
  (e.g., `IMPLEMENTATION_PLAN.md` or `ARCHITECT_PLAN.md`).
- Code patches. The meta-agent's hard constraint is "writes proposal
  markdown only, never code." Any non-markdown file here is a bug.
- Proposals about the doctrine-meta-agent's own SKILLS.md or the
  framework-reviewer's SKILLS.md. These are `forbidden_targets` in the
  meta-agent's constraint set (anti-runaway-self-modification per I-7).
