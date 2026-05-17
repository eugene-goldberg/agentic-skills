# PO To Engineering Handoff Protocol

## Purpose

Convert Product Owner output into engineering-agent input without losing traceability or letting the engineering agent overbuild.

The handoff unit is one backlog item at a time:

```text
REQs + one BL item + sprint context + engineering constraints -> implemented slice + tests + verification
```

## Why One Backlog Item Per Engineering Run

One backlog item is the right default unit because it is:

- Small enough for incremental implementation.
- Traceable to explicit `REQ-XXXX` identifiers.
- Easy to verify independently.
- Easy to compare across engineering skills.
- Less likely to cause scope drift than "build the whole app".

If a backlog item has hard dependencies, the engineering packet may include those dependency items as context, but the implementation scope must still name exactly what is in and out.

## Required Inputs

Each engineering work packet must include:

- Run ID.
- Engineering skill ID.
- Target repo path and baseline commit.
- Selected backlog item ID.
- Backlog item text copied verbatim.
- Related requirement excerpts copied verbatim.
- Relevant sprint-plan context.
- Explicit in-scope behavior.
- Explicit out-of-scope behavior.
- Expected files or artifact shape.
- Verification commands.
- Production-grade quality bar.

## Engineering Agent Prompt Shape

The engineering agent should receive context in this order:

1. Engineering skill instructions.
2. Target repo `README.md` and `ENGINEERING_GUIDE.md`.
3. Selected work packet.
4. Relevant excerpts from `REQUIREMENTS.md`.
5. Selected backlog item from `.agile-v/BACKLOG.md`.
6. Relevant sprint-plan lines from `.agile-v/sprints/C1/SPRINT_PLAN_C1.md`.

Do not paste unrelated backlog items unless needed as dependency context.

## Execution Rules

- Implement one thin vertical slice.
- Write or update tests for the selected behavior.
- Keep the target repo runnable after every meaningful increment.
- Run verification before scoring.
- Do not change `REQUIREMENTS.md`, `.agile-v/BACKLOG.md`, or `.agile-v/sprints/C1/SPRINT_PLAN_C1.md`.
- Record any requirement issue as a blocker instead of silently changing scope.

## Verification Strategy

For each backlog item, use three layers:

1. Static or structural sanity checker for the specific BL item.
2. Project test suite, usually `python -m pytest -q`.
3. Compilation/import check, usually `python -m py_compile app.py`.

As the app grows, BL-specific sanity checks should become less important than canonical HTTP tests.

## Scoring Implication

The engineering skill is scored on whether it can take a bounded PO backlog item and produce production-grade code for that slice without:

- Skipping tests.
- Violating REQ semantics.
- Implementing unrelated backlog items.
- Breaking the repo between increments.
- Requiring human rescue.

The current first engineering packet is `BL-0001`, the authenticated account foundation.
