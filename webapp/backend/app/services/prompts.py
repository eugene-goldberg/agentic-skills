"""Prompt builders for the two agent roles the webapp exposes.

`build_po_prompt`         — decomposes a brief into BACKLOG.md (and REQUIREMENTS.md if helpful).
`build_engineer_prompt`   — implements one selected BL item end-to-end with a git commit.

Both prompts require the agent to finish with a single-line JSON status payload
so the UI can confirm success.
"""
from __future__ import annotations


RETRIEVAL_HINT = """\
## Retrieval tools (MCP)
You have access to 5 retrieval tools that query a *reference* repo of curated
good patterns and the *target* repo you are currently working in:

- `mcp__retrieval__target_status()` — INSTANT (<100ms) scan of the target repo.
  Returns `{kind: "greenfield"|"brownfield", source_file_count, languages,
  has_pyproject, has_tests, top_source_files: [...]}`. Use this to classify
  the project before reaching for the slower tools.
- `mcp__retrieval__semantic_search(query, k=5, source="reference"|"target")`
  Hybrid semantic+keyword search; returns file + line range + snippet. The
  FIRST call against a given source may take ~10s to warm up indexing. Each
  subsequent call is <2s. Treat any `{ok:false, error:"...timeout..."}` as a
  hard signal to stop calling `semantic_search` against that source and use
  graph_* or what you already have.
- `mcp__retrieval__graph_neighbors(symbol, depth=1, source=...)`
  Callers / callees / contains edges for a symbol.
- `mcp__retrieval__graph_find_similar(symbol, k=5, source=...)`
  Structurally similar entities (Jaccard over shared call targets).
- `mcp__retrieval__graph_summary(path, source=...)`
  Entities and their call targets in a given file.

Rules:
- ALWAYS call `target_status` once before any other retrieval tool.
- If `kind="greenfield"`, NEVER call `semantic_search` or `graph_*` with
  `source="target"` — they will return empty after a wasted call.
- A per-task budget of 30 retrieval calls is enforced.
- Do NOT retry the same query after a timeout or `{ok:false}` — switch tools
  or proceed with what you have.
"""



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


ENG_DISCOVERY_PROTOCOL = """\
## Mandatory discovery phase (run BEFORE writing or editing any code)

Skipping this step yields lower-quality code and is enforced by the scorer.
Follow the protocol literally:

1. **Classify the target — call exactly one tool.**

       mcp__retrieval__target_status()

   Returns instantly (<100ms). Note `kind`, `source_file_count`, `languages`,
   `top_source_files`. Use these to choose your search strategy below.

2. **Reference-pattern lookup (ALWAYS, ≥2 calls).** This BL is one slice of a
   larger system. Find the closest analog in the reference repo before
   designing your solution:
   - `mcp__retrieval__semantic_search(query="<the capability this BL adds, phrased as a code problem>", source="reference", k=5)`
   - For the most relevant hit, follow up with one of:
     - `mcp__retrieval__graph_summary(path="<file from hit>", source="reference")`
       to see what symbols live in that file and what they call.
     - `mcp__retrieval__graph_neighbors(symbol="<key function from hit>", source="reference", depth=1)`
       to see callers, callees, and what types/helpers it depends on.
   If `semantic_search` returns `{ok:false}` or a timeout once, switch to
   `graph_summary`/`graph_neighbors` directly on a plausible file — do NOT
   retry the same query.

3. **Target-codebase lookup — ONLY if step 1 returned `kind="brownfield"`
   (≥2 calls).** Before adding new code, find what already exists and what
   you must integrate with:
   - `mcp__retrieval__semantic_search(query="<existing capability you'll plug into>", source="target", k=5)`
   - `mcp__retrieval__graph_neighbors(symbol="<the function or class you'll modify or call>", source="target", depth=2)`
   - For files you intend to edit: `mcp__retrieval__graph_summary(path="<file>", source="target")` to confirm what's there.
   If step 1 returned `kind="greenfield"`, SKIP this step entirely; target
   tools will short-circuit with `empty=true` but each call costs a turn.

4. **Cite findings in the commit body.** Your commit message body MUST
   include a short `Patterns:` block listing the reference files (with
   line ranges when you have them) you used as a template, and — for
   brownfield — a `Integration points:` block listing target symbols/files
   the new code calls into or extends.

5. The per-task retrieval budget is 30 calls; aim for 4–8 in step 2+3, not 30.
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


PO_DISCOVERY_PROTOCOL = """\
## Mandatory discovery phase (run BEFORE writing the backlog)

Your acceptance criteria will be much better if they are grounded in real
code rather than only the brief. Follow this discovery protocol literally:

1. **Classify the project — call ONE tool.** Issue exactly one call:

       mcp__retrieval__target_status()

   This is instant (<100ms). It returns `{kind, source_file_count,
   languages, has_pyproject, has_tests, top_source_files}`. Do NOT use
   `semantic_search` or bash heuristics for classification — they are slower
   and less reliable. Trust the returned `kind`.

2. **Reference-repo grounding (always, ≥2 calls).** Issue at least **2**
   retrieval calls against `source="reference"` to surface concrete patterns
   the engineer will later be told to emulate. Examples:
   - `mcp__retrieval__semantic_search(query="<domain pattern from the brief>", source="reference", k=5)`
   - `mcp__retrieval__graph_summary(path="<promising file from the first hit>", source="reference")`
   Pick queries that mirror the main capabilities the brief asks for (auth,
   CRUD, search, pagination, validation, persistence, etc.). If the first
   `semantic_search` returns `{ok:false}` or a timeout, switch to
   `graph_summary`/`graph_neighbors` on a likely file — do NOT retry the same
   query.

3. **Brownfield target probe — ONLY if step 1 returned `kind="brownfield"`.**
   Issue at least **2** retrieval calls against `source="target"`:
   - `mcp__retrieval__semantic_search(query="<capability from brief>", source="target")`
   - `mcp__retrieval__graph_summary(path="<key file>", source="target")` or
     `mcp__retrieval__graph_neighbors(symbol="<key symbol>", source="target")`
   If step 1 returned `kind="greenfield"`, **skip this entire step**. The
   target tools will return `empty=true` immediately, but every skipped call
   still costs you a turn.

4. **Cite findings.** In the BACKLOG.md you will write, include a short
   `## Brief comprehension notes` section at the top that records:
   - whether the project is greenfield or brownfield (from step 1)
   - 2–5 bullets summarizing the patterns or existing-code findings you used
   - file:line references for the reference patterns each BL borrows from

5. The retrieval budget is 30 calls; stay well under it.
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
- Do not ask clarifying questions. Make reasonable decisions and document them in the brief comprehension notes.

{RETRIEVAL_HINT}

{PO_DISCOVERY_PROTOCOL}

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

{RETRIEVAL_HINT}

{ENG_DISCOVERY_PROTOCOL}

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

{RETRIEVAL_HINT}

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


# ──────────────────────────── Doctrine dispatcher ────────────────────────
# Selects greenfield vs brownfield prompt builders based on `target_status()`
# output. Called by routers/projects.py once per agent run.

from pathlib import Path as _Path
from app.services import prompts_brownfield as _bf
from app.services import lessons as _lessons
from app.services import global_lessons as _global_lessons
from app.services.brownfield import pick_artifact_dir as _pick_dir, feature_artifact_dir as _feature_dir, RUBRIC_PATHS as _RUBRIC_PATHS


def _resolve_art_dir(repo_root: _Path, feature_slug: str | None) -> str:
    """A18: per-feature isolation. When feature_slug is supplied, route all
    brownfield-prompt path references through ``_brownfield/features/<slug>``
    so each feature's artifacts live in their own subtree."""
    return _feature_dir(repo_root, feature_slug)


def _lessons_block(repo_root: _Path, feature_slug: str | None, inject_lessons: bool,
                   inject_global_lessons: bool = False) -> str:
    """ABL-0016 Batch B + ABL-0018 Stage 3: render the advisory prior-lessons
    block(s) for a brownfield role prompt. Empty string when both flags are OFF
    or there are no lessons (silent injection).

    - ``inject_lessons``: the per-target block (target-scoped union over feature
      ledgers; feature_slug biases ranking). See lessons.py.
    - ``inject_global_lessons``: the cross-target block (failure modes confirmed
      across multiple codebases) — independent flag so the higher-blast-radius
      global push rolls out separately. Renders even when the target has no
      per-target lessons, so a fresh target inherits the global layer day one.
    """
    parts: list[str] = []
    if inject_lessons:
        parts.append(_lessons.render_lessons_block(
            _lessons.list_lessons(repo_root, feature_slug, cap=_lessons.DEFAULT_LESSON_CAP)
        ))
    # ABL-0018 push — gated by the request flag AND the Stage-3 master switch
    # (operator 2026-06-11: dormant by default; even an explicit flag does not
    # surface global lessons unless STAGE3_CROSS_TARGET=1 re-enables transfer).
    if inject_global_lessons and _global_lessons.enabled():
        parts.append(_global_lessons.render_global_lessons_block(
            _global_lessons.list_global_lessons(cap=_global_lessons.GLOBAL_PUSH_CAP)
        ))
    return "".join(p for p in parts if p)


def select_family(target_status_result: dict | None) -> str:
    """Return 'brownfield' or 'greenfield' based on target_status output.

    `target_status_result` is the dict returned by mcp_servers.retrieval_server
    target_status, or None if classification could not be performed (treat as
    greenfield to keep the existing notes-app demo behavior).
    """
    if not isinstance(target_status_result, dict):
        return "greenfield"
    return "brownfield" if target_status_result.get("kind") == "brownfield" else "greenfield"


def build_po(family: str, brief: str, project_name: str | None, repo_root: _Path,
             feature_slug: str | None = None, inject_lessons: bool = False,
             inject_global_lessons: bool = False, contract_first: bool = False) -> str:
    if family == "brownfield":
        art = _resolve_art_dir(repo_root, feature_slug)
        return _bf.build_po_prompt_brownfield(brief, project_name,
                                              artifact_dir=art,
                                              lessons_block=_lessons_block(repo_root, feature_slug, inject_lessons, inject_global_lessons),
                                              contract_block=(_bf.po_contract_instruction(art) if contract_first else ""))
    return build_po_prompt(brief, project_name)


def build_stub_materializer(family: str, contract_text: str, repo_root: _Path,
                            repo_summary: str = "", feature_slug: str | None = None) -> str:
    """Contract-First Phase 1 (decision c): the Engineer-as-materializer prompt."""
    return _bf.build_stub_materializer_prompt_brownfield(
        contract_text, repo_summary=repo_summary,
        artifact_dir=_resolve_art_dir(repo_root, feature_slug))


def build_engineer(family: str, bl_id: str, bl_section: str, repo_root: _Path,
                   repo_summary: str = "", feature_slug: str | None = None,
                   inject_lessons: bool = False, inject_global_lessons: bool = False,
                   contract_first: bool = False) -> str:
    if family == "brownfield":
        return _bf.build_engineer_prompt_brownfield(bl_id, bl_section, repo_summary,
                                                    artifact_dir=_resolve_art_dir(repo_root, feature_slug),
                                                    lessons_block=_lessons_block(repo_root, feature_slug, inject_lessons, inject_global_lessons),
                                                    contract_first=contract_first)
    return build_engineer_prompt(bl_id, bl_section, repo_summary)


def build_qa(family: str, bl_id: str, bl_section: str, repo_root: _Path,
             feature_slug: str | None = None, inject_lessons: bool = False,
             inject_global_lessons: bool = False) -> str:
    if family == "brownfield":
        return _bf.build_qa_prompt_brownfield(bl_id, bl_section,
                                              artifact_dir=_resolve_art_dir(repo_root, feature_slug),
                                              lessons_block=_lessons_block(repo_root, feature_slug, inject_lessons, inject_global_lessons))
    return build_qa_prompt(bl_id, bl_section)


def build_score(family: str, bl_id: str, bl_section: str, repo_root: _Path,
                feature_slug: str | None = None, inject_lessons: bool = False,
                inject_global_lessons: bool = False) -> str:
    rubric_path = _RUBRIC_PATHS[family]
    rubric_text = rubric_path.read_text(encoding="utf-8") if rubric_path.exists() else ""
    if family == "brownfield":
        return _bf.build_score_prompt_brownfield(bl_id, bl_section, rubric_text,
                                                 artifact_dir=_resolve_art_dir(repo_root, feature_slug),
                                                 lessons_block=_lessons_block(repo_root, feature_slug, inject_lessons, inject_global_lessons))
    return build_score_prompt(bl_id, bl_section, rubric_text)
