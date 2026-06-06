# Audit & Consolidation Proposal — 2026-06-06

> Architect deliverable requested by the operator after the complexity
> question ("is the harness becoming too complex?"). Two parts:
> (1) a by-class audit of the A-ledger against I-6, and
> (2) a governance-document consolidation proposal.
>
> **This is a proposal. Nothing here is applied.** Per the architect role
> boundary, I do not archive a doc, rewrite the ledger, or change an
> invariant without operator sign-off. This file is itself a *dated,
> point-in-time* doc — it archives once acted on (the same discipline it
> recommends for EVALUATION_2026-05-28).
>
> Evidence base: 50 ledger entries (A1–A52; A18 & A42 never assigned) and
> 32 governance markdown docs, each read with git dates — not inferred from
> titles.

---

## Part 1 — A-ledger by-class audit (against I-6)

### 1.1 Counts by invariant

| Invariant | Instances | Open/Partial | Over I-6 ">3" trigger? |
|---|---|---|---|
| **I-2** doctrine contract | **~16** | A8,A11,A12,A36,A40,A41,A45,A47,A49(p),A39(p) | **YES — 2× any other** |
| I-1 resource lifecycle | ~8 | A9,A34,A35,A44(p),A45,A48b | yes |
| I-3 closure postconditions | ~8 | A34,A37,A48b | yes |
| I-7 self-hardening | ~4 | A14,A43(p) | yes (at line) |
| I-5 observability | ~3 | A44(p) | no |
| I-4 run identity | 1 | — | no |
| **no `class:` field** | **~25** | mixed | — (convention breach) |

Rollup: **~29 resolved · ~20 open · 4 partial (A39, A43, A44, A49).**

All four major axes exceed the trigger — expected, since they are the
primary structural dimensions. The *signal* is not "I-2 > 3"; it is
**I-2's dominance (2×) combined with its internal heterogeneity.** I-2 has
become a catch-all label for four genuinely different failure modes.

### 1.2 The core finding — I-2 should be split

The ~16 I-2 entries decompose into four distinct sub-classes. Continuing to
file each new instance under "I-2" guarantees per-site patching, because the
label is too coarse to point at a structural fix.

**Sub-class A — Gate verdict fidelity (5–6 instances): A21, A25a, A25b,
A32, A39, A49.**
The regression gate's verdict has repeatedly been imprecise, non-honest, or
non-deterministic: false-green on non-zero exit (A21), infra-vs-test
conflation (A25), 30-min hangs (A32), build-fail inflating the regression
count with an empty list (A39), and transient flakes flipping the verdict
(A49). Five-plus instances of one coherent failure mode.
→ **Recommendation: promote to a dedicated invariant.** Proposed
**I-8 (Gate Fidelity):** *the regression gate's verdict is (a) precise — it
names the actual failing node-ids; (b) honest — a non-zero exit never reads
green; (c) deterministic — transient/infra failures are classified, not
allowed to flip a pass/fail verdict.* A39 and A49 are already the partial
fixes toward (a) and (c); this names the rule they're serving.

**Sub-class B — Enforcement completeness (4): A8, A11, A36, A40.**
R-rule floors that *warn* but never *fail* the run. R9 (graph-grounding) is
still advisory two years of ledger later (A8/A11); R5 counts calls without
layer coverage (A36); auto-fix tooling isn't required (A40).
→ **Recommendation: tighten I-2's existing intent**, not a new invariant.
I-2 already says "every R-rule maps to one enforcement point + one test."
Add the missing half: *an enforcement point must be able to **fail** the
run, not only annotate.* Then A8/A11/A36/A40 become a single conformance
sweep against the doctrine-spec registry (ABL-0020), not four patches.

**Sub-class C — Prompt↔rule consistency (3): A12, A16, A41.**
What an agent is *told* (SKILLS/prompt) contradicts or omits what it is
*checked against* (validator/rule): filename drift (A12), R5b never taught
(A16), meta-agent prompt says "commit" while SKILLS forbids it (A41).
→ **Recommendation: tighten I-2** with a consistency clause: *the prompt/
SKILLS an agent receives must not contradict the rule it is enforced
against; a CI check diffs the two* (mirrors the existing
prose-table↔registry drift test).

**Sub-class D — Tool/MCP containment (2): A47, A51.**
Agents reaching tools/MCP servers they shouldn't (built-in CLI bypass A47;
corporate MCP fleet A51). Below threshold; leave under I-2 for now, revisit
if a 3rd appears.

### 1.3 Secondary findings

- **~25 entries lack a `class:` field.** CLAUDE.md states "patches that
  don't classify get flagged." The breach is concentrated in pre-convention
  entries (A1–A7) and operational entries (A19–A33). → **Recommendation:**
  draw an explicit line — backfill `class:` for everything ≥ A32 (the
  convention era), and mark A1–A31 "pre-taxonomy (historical)" in a single
  ledger note rather than retrofitting 25 fields.

- **A28–A31 are performance enhancements, not shortcomings.** Playwright
  workers, PRE caching, TIA, tiered gates — these are a throughput roadmap
  miscategorized in a *defect* ledger. → **Recommendation: move A28–A31 to
  BACKLOG.md** (they relate to the proposed I-8 gate work but are
  optimizations, not correctness defects).

- **I-1/I-3 open items share one cluster: abnormal-exit cleanup.** A9 (gate
  pgroup leak), A34 (SSE-disconnect abort), A35 (graphify symlink), A37 (QA
  merge swallow), A48b (force-kill worktree orphan). These are I-1/I-3
  *enforcement* still being incomplete on non-happy exit paths. →
  **Recommendation:** one consolidated "abnormal-exit closure" hardening
  pass keyed to I-3's closure postconditions, rather than five separate
  fixes. *(Note: A34 "run-brief dies on SSE disconnect" reads as possibly
  stale — today's run survived the SSE-consumer exit and ran to completion
  server-side; verify before working it.)*

### 1.4 Net of Part 1

Three concrete structural moves replace ~13 would-be per-site patches:
1. **New invariant I-8 (Gate Fidelity)** ← absorbs A21/A25/A32/A39/A49.
2. **Tighten I-2** with an "enforcement must fail, not warn" clause
   (A8/A11/A36/A40) and a "prompt↔rule consistency" clause (A12/A16/A41).
3. **Reclassify**: A28–A31 → BACKLOG; draw the pre-taxonomy line at A32.

---

## Part 2 — Governance-document consolidation

32 governance markdown docs exist (24 in the CLAUDE.md map + 8 at root not
in the map). The live set is too large to keep consistent by hand — and it
is *already* drifting, with a measured cost this session (the
CONTINUATION_PROMPT recorded `agent/fd5263480b39` as the broken calendar
branch; it was actually invoice-soft-delete — I lost time chasing the wrong
branch).

### 2.1 Archive now — work is complete (6 docs)

| Doc | Why archivable |
|---|---|
| IMPLEMENTATION_PLAN.md | Sprint-2 hardening; CLAUDE.md calls it "the **completed** pass" |
| IMPLEMENTATION_TRACKER.md | "18/18 in-scope landed"; 7 unchecked all labeled "deferred" |
| ABL-0020_DOCTRINE_SPEC_REGISTRY.md | CLAUDE.md: "Complete; fulfills I-2" |
| ABL-0021_ONDEMAND_DISPATCH_UI.md | Self-declares "Status: COMPLETE — A+B shipped" |
| ABL-0015_AUTO_DISPATCH_DESIGN.md | Superseded by ABL-0015_CALIBRATION_CAMPAIGN |
| EVALUATION_2026-05-28.md | Point-in-time; ledger frozen at A43 (now A52) |

→ Move to `archive/` (new dir). They stay in git history and remain
readable; they leave the *live* working set.

### 2.2 Fix drift (4 fixes)

- **BROWNFIELD_PROGRESS.md** — stale since 2026-05-20; names working branch
  `agentic-skills-work` and `master@32ebacf` while the operational tip is
  `followup-dispatch-ui` on `agentic-skills-work-v3`. → Archive or rewrite.
- **CLAUDE.md footer** "Last updated 2026-05-23" — content references A52 /
  ABL-0021 (post-dates that). → Correct the footer.
- **Two ABL-0015 docs** overlap. → Fold any still-live design detail from
  AUTO_DISPATCH_DESIGN into CALIBRATION_CAMPAIGN; archive the former.
- **CONTINUATION_PROMPT.md transcribes volatile branch SHAs into prose.**
  This is the wrong-branch root cause. → Convention change: the handoff
  references *verifiable* state (a command to run, a branch to `git log`),
  it does not transcribe SHAs/branch-ids that rot between sessions.

### 2.3 Map hygiene (decide)

Docs that are LIVE and substantial but **absent from the CLAUDE.md map**:
- **ABL-0014_ACCEPTANCE_AGENT_IMPLEMENTATION.md** (588 lines, "Batch C in
  flight") — should be in the map.
- **HARNESS.md** (799 lines) — harness-engineering primer; live.
- **README.md** — outside-reviewer entry point.
→ Either add them to the map, or explicitly designate README/HARNESS as
"external-facing, outside the governance map." Don't leave them ambiguous.

### 2.4 Net of Part 2

Live governance set drops from **32 → ~20**: 6 archived, BROWNFIELD_PROGRESS
retired, 1 ABL-0015 merged, drift corrected, 3 unlisted live docs reconciled
with the map. The map becomes something a session can actually hold.

---

## Recommended sequencing (all operator-gated)

1. **Cheap & safe first:** archive the 6 completed docs + fix the 4 drift
   items (Part 2.1–2.2). Pure hygiene, no behavior change, immediate
   complexity reduction.
2. **Reclassify the ledger** (Part 1.3): A28–A31 → BACKLOG; pre-taxonomy
   line at A32. Mechanical.
3. **Structural (needs your approval on doctrine):** add **I-8 Gate
   Fidelity**, tighten I-2 (enforce-not-warn + prompt↔rule). This touches
   ARCHITECTURE_INVARIANTS.md and the doctrine-spec registry — the highest-
   value move, and the one that actually slows future per-site accretion.

Steps 1–2 I can execute immediately on approval (no doctrine change). Step 3
I would bring as a specific ARCHITECTURE_INVARIANTS.md + doctrine_spec.py
diff for review before applying.
