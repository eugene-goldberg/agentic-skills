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
