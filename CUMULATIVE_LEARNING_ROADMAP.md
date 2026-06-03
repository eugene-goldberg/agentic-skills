# Cumulative Learning — architect strategy

> **Status: discussion / strategy, not a verified plan.** This captures the
> architect's assessment of how to make the mission's **cumulative**
> property ("what's learned on one target carries forward") more fully
> implemented. The *seeds* named below (priors injection, doctrine-meta,
> eng_patterns, retrieval layer) are confirmed to exist; the
> effort/sequencing estimates are judgment until the retrieval-injection
> seam is verified (see "Recommendation & honesty caveat").
>
> Framed throughout as **"what the crew gains"** per the THESIS — not
> operator-time. Written 2026-06-02.

---

## First, the honest current state — the seeds

Cumulative learning today is three disconnected fragments:

1. **Findings ledger + priors injection (§I.3 Batch E)** — the acceptance
   agent reads prior verdict counts *per classification, per feature* at
   spawn ("product_bug refuted 4× here → raise your bar"). Intra-target,
   intra-feature, **read by one role only**.
2. **Doctrine-meta-agent (I-7 / ABL-0003)** — reads a sprint's archived
   traces and *proposes* new R-rules to `.planning/doctrine_proposals/`.
   Operator approves. The framework learns *rules* from evidence.
3. **eng_patterns.md artifacts** — each engineer records the target's
   patterns/invariants/blast-radius per BL, but these are written once and
   never consolidated or re-read.

Map these onto the four parts any learning system needs, and the gaps are
stark:


| | substrate | write path | **read path** | promotion |
|---|---|---|---|---|
| have | findings ledger; doctrine_proposals; eng_patterns | append_from_report; doctrine-meta | **priors → acceptance only** | operator approves rules |
| missing | a per-target **lessons** store all roles share | outcome attribution | **PO/engineer/QA read nothing** | closed-loop rule efficacy |

**The single biggest gap: the read path.** Learning that no agent consults
at decision time isn't cumulative — it's an archive. An engineer about to
edit `billing/invoices.py` has *no idea* a PUT-bypass bug shipped there
last sprint. Fixing that is the highest-leverage move.

---

## The path — four stages, each a crew capability gain

### Stage 1 — Lessons-as-retrieval (highest leverage, lowest new-architecture risk)

Generalize the findings ledger into a per-target **Lessons store**:
confirmed acceptance findings + recurring gate failures + accepted doctrine
rules + blast-radius hotspots. Then wire it into the **retrieval layer** so
every role's pre-work context surfaces "relevant prior lessons for the
files/symbols in scope" — same channel, same grounding machinery as code
retrieval.

- *Crew gains:* the engineer touching invoices.py gets the prior PUT-bypass
  lesson injected as evidence; the PO planning a billing feature sees this
  codebase's recurring failure modes.
- *Why it's safe:* lessons are **advisory evidence the agent weighs**, not
  binding rules — the exact "falsification priors, not bans" framing §I.3
  already established. It rides the *mature* property (grounding) instead of
  inventing a new control surface.
- This is the natural extension of §I.3 priors injection from one role to
  all roles.

### Stage 2 — Close the doctrine-meta loop with outcome attribution

Today I-7 stops at "proposes" — open-loop. Add **outcome labels** to every
BL (clean-merge / gate-retry / awaiting_review / acceptance-caught-bug) and
**rule-efficacy tracking**: when an approved rule is enforced, measure
whether its targeted failure class actually dropped in later sprints. Rules
that don't help get flagged for retirement.

- *Crew gains:* self-hardening becomes *closed-loop* — the crew learns
  which of its own rules earn their keep, not just generates more of them.
  Without outcome attribution there is nothing to learn *from* at the
  engineering-decision level.

### Stage 3 — Cross-target transfer (makes the mission literally true)

Split the substrate into **global crew memory** (target-agnostic: doctrine
rules, failure taxonomies, retrieval strategies that generalize) vs
**per-target memory** (this codebase's conventions/hotspots). A fresh
target inherits the global layer on day one.

- *Crew gains:* "what's learned on one target carries forward" stops being
  aspirational — a new org's repo starts with the accumulated judgment of
  every prior engagement instead of cold.

### Stage 4 — Pattern/convention profile (deepest, slowest)

Consolidate the per-BL eng_patterns.md into a durable **per-target pattern
profile** (layering, naming, error handling, DI idioms) that seeds future
Pattern Matching instead of re-deriving it every sprint.

- *Crew gains:* Pattern Fidelity compounds — each sprint makes the next
  one's grounding cheaper and sharper.

---

## The governing discipline

Cumulative learning that *auto-applies* is dangerous (poisoned memory,
drift). The split that keeps it safe:

- **Doctrine** stays operator-gated forever (I-7 is explicit: propose,
  never auto-merge).
- **Lessons-as-retrieval** can be advisory and un-gated, because they're
  evidence the agent weighs against its own grounding — not rules that bind
  it. Same risk profile as the codebase retrieval the crew already trusts.

---

## Recommendation & honesty caveat

**Start with Stage 1.** It's the highest leverage (closes the read-path gap
for *all* roles), the lowest architectural risk (reuses grounding + extends
§I.3), and it directly unblocks the others (it builds the shared substrate
Stages 2–4 write into).

Before committing a real plan, **verify the exact retrieval-injection
seam** — how each role's pre-work context is assembled (the
`retrieval_kwargs_builder` path and the per-BL `codebase_context.md`
generation) — to size how hard "lessons-as-retrieval" wiring actually is.
That's the one technical unknown between this vision and an executable ABL.

*Confidence: this is architecture strategy, not a verified plan — the seeds
(priors injection, doctrine-meta, eng_patterns, retrieval layer) are
confident-to-exist; the effort/sequencing estimates are judgment until the
injection seam is verified.*
