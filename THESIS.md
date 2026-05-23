# Agentic Skills — Thesis

> **One sentence:** Build a completely AI-based multi-agent software-development team that can autonomously add significant, complex features to existing brownfield codebases — with no human in the loop for the bulk of the work.

This document supersedes prior framings (A/B model comparison harness, brownfield doctrine R&D). Those still exist as instruments, but they are not the goal. The goal is the **autonomous team**.

---

## 1. Vision

An organization should be able to:

1. Point the agentic-skills team at a real brownfield git repo (legacy code, technical debt, existing conventions, real users).
2. Hand it a product-level requirement ("add multi-tenant collaboration", "add billing", "add SSO").
3. Walk away.
4. Come back to a series of clean, regression-tested, grounded-in-context commits that ship the feature — plus an honest report of what was deferred, what's risky, and what genuinely needs a human eye.

The team should be:

- **Grounded** — every change is justified by retrieval evidence from the actual target codebase, not from model intuition.
- **Self-correcting** — when a gate fails or a doctrine check rejects work, an agent (not a person) decides whether to retry, rewrite, defer, or escalate.
- **Honest** — when something is genuinely outside scope or risky, the team flags it explicitly rather than producing slop.
- **Cumulative** — what the team learns on one brownfield target carries forward to the next.

---

## 2. What's true today (the 40% slice)

Sprint 1 (Team Collaboration Module on `full-stack-fastapi-template`, 12 merged BLs + 1 no-op, mean score ~92/100) proved a real but partial slice of the thesis. Honest accounting:

| Capability | State | Evidence |
|---|---|---|
| **Worker roles execute autonomously** (PO → Engineer → QA → Scorer) | ✅ | 13 BLs delivered end-to-end |
| **Quality-gated handoff between roles** | ✅ | Doctrine validator + regression gate v3 + ff merge |
| **Grounded edits** | ✅ | MCP retrieval + R5 (≥3 grounded calls) + Tier 1.5 pre-modification kill + R5b citation requirement |
| **Self-correction on real failures** | ✅ | R10.1 saved BL-0012 (broken nested-route layout) and BL-0013 (Playwright locator collision) without operator action |
| **No-op recognition** | ✅ | R11 caught BL-0003 (already shipped upstream) without forcing synthetic changes |
| **Sprint planning from product intent** | ❌ | BL specs were pre-written; no agent generated them this session |
| **Inter-BL orchestration** | ❌ | Today: shell `chain launcher` that I assemble per-BL. Cannot pick dependencies, cannot re-sequence on failure, cannot open the next sprint |
| **Escalation triage** | ❌ | `awaiting_review` still puts a branch in front of a human |
| **Self-hardening doctrine** | ❌ | Every R-rule from R5b through R12 + R10.1 was added by a human (me) when I saw an agent fail. No agent owns the doctrine |
| **Cross-project / cross-sprint memory** | ❌ | Every target gets a fresh `_brownfield/` dir with no shared institutional knowledge |
| **Concurrent execution** | ❌ | One agent at a time per role; no parallel BL work |
| **Cost / telemetry / observability** | ⚠ | Partial — SSE stream + trace dir per run, no aggregation, no $ tracking |

Roughly **40% of the full thesis is operational.** The remaining 60% — planning, orchestration, triage, meta — is the actual product backlog from here on.

---

## 3. Definition of "autonomous team"

The thesis is delivered when a human can do this and walk away:

```
$ agentic-skills onboard ~/dev/brownfield-target
$ agentic-skills feature "Add usage-based billing with Stripe; include admin dashboard for revenue + churn"
$ agentic-skills run
```

…and after some duration, return to:

- A series of fast-forward merge commits on the agent branch, each with a green regression gate
- A short summary of what shipped, what was deferred (with reasons), and any open questions for a human
- Scorecards per BL
- Zero new R-rules written by a human during the run (the doctrine agent owned that)

**Concretely, "done" means all of these are true:**

1. Given a product-level requirement + repo, the Sprint Planner agent produces a complete `BACKLOG.md` with dependency graph, sprints, and per-BL context — no human authoring.
2. The Orchestrator agent picks the next ready BL based on the dependency graph, handles retries vs escalation, and opens the next sprint when one closes.
3. The Triage agent resolves every `awaiting_review` outcome into one of: rewrite-and-retry, defer-with-justification, split-into-smaller-BLs, or genuine-human-question (with the question framed precisely).
4. The Doctrine agent observes failure patterns across BLs and proposes new R-rules + validator updates as PRs against the agentic-skills repo itself.
5. The Retrospective agent runs at sprint close, updates `cross-project-memory`, and seeds the next sprint's PO context with relevant institutional knowledge.
6. The Escalation Bridge sends focused questions to a real human via Slack/Linear/email when (and only when) a Triage agent decides a human is needed. Operator can answer in plain text; the team resumes.
7. The Telemetry layer reports per-sprint $ spent, time-to-merge per BL, R-rule trigger counts, and a scorecard mean trend across sprints.

Nothing in that list is currently automated end-to-end.

---

## 4. Roadmap (sprint themes)

Sprint numbering continues from Sprint 1 (the Team Collaboration Module on the brownfield target). These are *agentic-skills' own* sprints — work on the framework, not on a target repo.

| Sprint | Theme | Why this one |
|---|---|---|
| **Sprint 2** | **Autonomy & orchestration** | Closes the largest operator-time sink. Today I am the orchestrator; that has to stop. |
| **Sprint 3** | **Planning & sprint kickoff** | Closes the input side — agents take real product intent and produce backlogs |
| **Sprint 4** | **Meta & self-improvement** | The doctrine hardens itself; institutional learnings flow forward |
| **Sprint 5** | **Scale** | Concurrent BL execution, multi-target ops, telemetry, cost visibility |

Sprint 2 is the starting point because every other sprint assumes orchestration exists.

See `BACKLOG.md` for the per-BL breakdown.

---

## 5. Non-goals (explicit)

- **Replacing a senior engineer's judgment on architecture-level decisions.** The team should flag those, not bluff through them.
- **Working on truly novel domains with no analog in the target codebase.** The retrieval-grounded thesis breaks when there's nothing to retrieve.
- **Real-time interaction during a sprint.** The team is async by design. Operator answers questions when convenient; the team waits.
- **Greenfield-from-zero work.** The thesis is specifically about *brownfield* — repos with existing conventions, tests, debt, and users.

---

## 6. How to read this repo through the thesis lens

- `langgraph_engine/` — the original A/B harness. Still useful for comparing providers but no longer the headline.
- `webapp/` — the current execution surface. Hosts the agent runners, doctrine validators, and gate infrastructure. This is where Sprint 2 work lands.
- `skills/brownfield/` — the role doctrines (PO, Engineer, QA). Sprint 2 adds three new role doctrines (Orchestrator, Triage, Doctrine-meta).
- `rubrics/production_grade_scorecard_brownfield.md` — the scoring rubric. Sprint 4 work may add a meta-rubric that scores the team's *process*, not just its output.
- `reference-repos/` — curated good-pattern repos the retrieval layer queries. The library expands as new domains come into scope.

---

## 7. Success metric

The thesis is delivered when this is true on a target repo the team has never seen before:

> **operator-time-per-feature < 1 hour, including kickoff and final review combined.**

Today that number is ~10–15 hours per Sprint-1-sized feature (mostly mine, watching pipelines and adding R-rules). Sprint 2 should drop it to ~3 hours. Sprint 4 should drop it to ~1 hour. Beyond that, the limit becomes Anthropic API throughput, not human time.
