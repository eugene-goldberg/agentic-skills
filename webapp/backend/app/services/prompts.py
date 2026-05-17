"""Prompt builders for the two agent roles the webapp exposes.

`build_po_prompt`         — decomposes a brief into BACKLOG.md (and REQUIREMENTS.md if helpful).
`build_engineer_prompt`   — implements one selected BL item end-to-end with a git commit.

Both prompts require the agent to finish with a single-line JSON status payload
so the UI can confirm success.
"""
from __future__ import annotations


PO_COMPLETION_PROTOCOL = """\
## Required Completion Steps
After decomposition is complete:
1. Write the full backlog to `.agile-v/BACKLOG.md` in this exact format:

   # Backlog: <Project Name>

   ## BL-0001: <Short Title>
   **Type:** Feature | Technical | Bug · **Priority:** CRITICAL | HIGH | MEDIUM | LOW
   **Story:** As a <user>, I want <capability> so that <value>.
   **Acceptance:**
   1. <testable criterion>
   2. ...
   **Effort:** <1-5> · **Dependencies:** <BL-xxxx, BL-yyyy or "none"> · **Status:** Ready

   ## BL-0002: ...

   Continue numbering sequentially with zero-padded 4-digit IDs.
2. If the brief contains numbered requirements, also write `REQUIREMENTS.md` mirroring them.
3. Run `git add -A` then `git commit` with a message of the form:
   `po: decompose brief into N backlog items`
4. Print ONLY this JSON as your final output (no extra prose):
   {"status":"complete","backlog_path":".agile-v/BACKLOG.md","item_count":<N>,"commit_sha":"<sha>"}
"""


ENG_COMPLETION_PROTOCOL = """\
## Required Completion Steps
After the work is complete:
1. Run any tests / build commands relevant to the change.
2. `git status` + `git diff --stat` to confirm scope.
3. `git add -A` (or stage selectively).
4. `git commit` with a structured message:
   `<bl_id>: <short description>` plus a body explaining what changed and why.
5. Print ONLY this JSON as your final assistant output (no extra prose):
   {"status":"complete","bl_id":"<BL-XXXX>","commit_sha":"<full sha>","files_changed":<n>,"summary":"<brief>"}
"""


def build_po_prompt(brief: str, project_name: str | None = None) -> str:
    name = project_name or "Project"
    return f"""You are an Agile Product Owner. Decompose the following brief into a backlog of small, testable items.

## Project Name
{name}

## Brief
{brief}

## Rules
- Each backlog item is a thin vertical slice an engineer can implement in a single increment.
- Bootstrap / scaffolding items come first.
- Every item has explicit, testable acceptance criteria — no vague language.
- Order items so dependencies are satisfied by earlier items.
- Use BL-0001, BL-0002, ... ids.
- Do not ask clarifying questions. Make reasonable decisions and document them in the brief comprehension notes if any.

{PO_COMPLETION_PROTOCOL}
"""


QA_COMPLETION_PROTOCOL = """\
## Required Completion Steps
After the QA work is complete:
1. Run `git status` then `git add -A` and `git commit` with a message of the form
   `qa(<BL-id>): <short description of what was verified or what bugs were found>`.
2. Print ONLY this JSON as your final assistant output (no extra prose):
   {"status":"complete","bl_id":"<BL-XXXX>","commit_sha":"<full sha>","tests_added":<n>,"bugs_found":<n>,"verdict":"PASS|PASS-W/R|FAIL","summary":"<brief>"}
"""

SCORE_COMPLETION_PROTOCOL = """\
## Required Completion Steps
You are SCORING only. Do NOT modify production code or tests.
1. Write your scorecard to `.agile-v/scorecards/<BL-id>.md` in the repo.
2. Stage and commit: `score(<BL-id>): scorecard <total>/75 verdict`.
3. Print ONLY this JSON as your final assistant output (no extra prose):
   {"status":"complete","bl_id":"<BL-XXXX>","commit_sha":"<full sha>","total":<n>,"core":<n>,"role":<n>,"verdict":"Pass|Pass W/R|Fail","summary":"<one paragraph>"}
"""


def build_engineer_prompt(bl_id: str, bl_section: str, repo_summary: str = "") -> str:
    repo_block = (
        f"\n## Current repo summary\n{repo_summary}\n" if repo_summary.strip() else ""
    )
    return f"""You are an autonomous Software Engineer implementing a single backlog item end-to-end.

## Backlog item to implement
{bl_section}
{repo_block}
## Execution Protocol
- Read existing code before editing.
- Run tests (or write tests) for the change.
- Stay within scope. Do NOT touch other backlog items.
- Do not ask clarifying questions; make reasonable decisions.

{ENG_COMPLETION_PROTOCOL}
"""


def build_qa_prompt(bl_id: str, bl_section: str) -> str:
    return f"""You are an autonomous QA Engineer validating the implementation of a single backlog item.

## Backlog item under test
{bl_section}

## QA Protocol
- Start by reading recent commits and the changed files for this BL via `git log --oneline -20` and `git show --stat HEAD`.
- Run the existing test suite (`pytest -q` or whatever the repo uses). Report results.
- Design and add NEW tests that cover the specific acceptance criteria of the BL above:
  * happy path
  * negative paths / 4xx behaviors
  * privacy / authorization invariants (non-members get 404, viewers get 403, etc.)
  * cross-tenant or cascade boundaries if the BL touches them
- Run the suite again. If anything fails, attempt one focused fix; otherwise file the defect in a `bug_report.md`.
- If real bugs exist in production code, fix the bug — do NOT relax the test.

## Reporting
- Add a markdown report at `.agile-v/qa/{bl_id}.md` summarizing what you verified, what you added, and any defects.
- Verdict guidance:
  * PASS = all acceptance criteria covered, all tests green.
  * PASS-W/R = acceptance met but with minor reservations (cite them).
  * FAIL = at least one acceptance criterion uncovered or broken.

{QA_COMPLETION_PROTOCOL}
"""


def build_score_prompt(bl_id: str, bl_section: str, rubric_text: str) -> str:
    return f"""You are a strict, fair scoring agent. You are evaluating ONE backlog item's implementation against the project rubric.

## Backlog item
{bl_section}

## Rubric (binding)
{rubric_text}

## Scoring Protocol
1. Read recent commits for the BL: `git log --oneline -20` and inspect with `git show <sha>` as needed.
2. Inspect the implementation files touched by the BL.
3. Run the test suite once (`pytest -q` or equivalent) and note results.
4. Score each dimension on the 0–5 scale defined in the rubric.
   - Core dimensions: 10 × 5 = 50 max.
   - Role dimensions: 5 × 5 = 25 max (use the **Engineer** role unless the BL is purely test/QA work, in which case use **QA**).
5. Compute totals: `total = core + role`, max 75.
6. Decision rules (strict):
   - `Fail`   if any acceptance criterion uncovered, build broken, or tests broken.
   - `Pass W/R` if all criteria met but ≥2 dimensions score ≤3.
   - `Pass`   otherwise.

## Scorecard format
Write `.agile-v/scorecards/{bl_id}.md` with the following sections:

```
# Scorecard {bl_id}

## Overall Decision
Decision: <Pass|Pass W/R|Fail>
Total Score: <total>/75 (core <core>/50 + role <role>/25)

## Core Dimensions (0–5 each)
| Dimension | Score | Evidence |
|---|---|---|
| Brief comprehension | <n> | ... |
| Scope control | <n> | ... |
| ... | ... | ... |

## Role-Specific Dimensions (0–5 each)
| Dimension | Score | Evidence |
| ... | ... | ... |

## Rationale
<one paragraph>
```

Be honest. Cite specific files / line ranges / commits as evidence. A perfect 75 is rare; only award it when you have direct evidence for every dimension.

{SCORE_COMPLETION_PROTOCOL}
"""
