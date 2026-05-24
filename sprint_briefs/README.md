# Sprint Briefs

This directory is the canonical home for the briefs the operator submits to
`POST /api/projects/<repo>/run-brief`. Each brief is the **primary intent
record** for one sprint — what the operator (or architect on their behalf)
asked the autonomous crew to build, captured verbatim before the PO agent
interprets it into a backlog.

Filed in response to A17 in [`DESIGN_SHORTCOMINGS.md`](../DESIGN_SHORTCOMINGS.md):
prior to this convention, briefs lived only as inline strings in the curl
body and inside each sprint's PO trace — there was no durable, reviewable,
version-controllable record of intent at the agentic-skills source-tree
level.

## Naming

`sprint_briefs/<run_id>-<project-name-slug>.md`

- `<run_id>` is the orchestrator-minted id (`run-<UTC-timestamp>-<6 hex>`),
  guaranteed unique per `/run-brief` invocation.
- `<project-name-slug>` is the human-readable slug derived from
  `RunBriefRequest.project_name` (lowercase, non-alphanumeric → `-`,
  truncated to 40 chars).

Example: `run-20260524T144409Z-90e234-rbac-feature.md`

## Structure

Every brief carries a YAML frontmatter the server writes at run start:

```yaml
---
run_id: run-20260524T144409Z-90e234
project_name: rbac-feature
repo: full-stack-fastapi-template
started_at: 2026-05-24T14:44:09.251061+00:00
brief_hash: 61ac7aa04211a090b42e4caf1d9d440ff57a5c9f6645a8280c38d7056e10016e
---
```

After the frontmatter, the brief body is the verbatim text the operator
POSTed. The PO agent receives this same text (without the frontmatter) as
the `brief` field of its prompt.

## Lifecycle

1. Operator (or architect) POSTs to `/api/projects/<repo>/run-brief` with
   the brief in the request body.
2. **Server writes** the brief to `sprint_briefs/<run_id>-<slug>.md`
   immediately, before the orchestrator's first event. An
   `orchestrator.brief_persisted` SSE event surfaces the path.
3. **Server does NOT commit.** Per the R13-class architect-overreach
   prohibition (agents own files, orchestrator owns refs; the *agentic-skills
   repo's* refs are operator-owned), the server only writes to disk.
4. Operator commits the brief to the agentic-skills repo at their
   discretion — typically alongside any post-sprint ledger updates, so the
   brief + the PO's interpretation + the resulting commits on the target
   are all linked in one architect-prereqs-style atomic record.
5. If the same brief is re-POSTed (B9 idempotency path), the existing
   `sprint_briefs/` file is left untouched.

## What does NOT belong here

- Per-BL work packets (those live in the target repo under
  `_brownfield/<BL>/`).
- Doctrine proposals from the meta-agent (those live in
  `.planning/doctrine_proposals/`).
- Old-harness role artifacts (those live in `briefs/`, a separate
  pre-existing directory).
- Edits to a previously-persisted brief. Sprint briefs are immutable
  records of what was asked; if intent changes, file a new brief for a
  new run.
