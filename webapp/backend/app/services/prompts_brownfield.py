"""Brownfield prompt builders — PO / Engineer / QA / Scorer.

The doctrine for each role is loaded VERBATIM at run-time from the
corresponding SKILLS.md file under
`skills/brownfield/brownfield-production-incremental-<role>/`:

- PO       → brownfield-production-incremental-po/SKILLS.md
- Engineer → brownfield-production-incremental-engineer/SKILLS.md
- QA       → brownfield-production-incremental-qa/SKILLS.md

These files ARE the operational doctrine the agents must follow — editing
them changes behavior on the next agent run without any Python edit.

This module adds a small webapp-side CONTRACT wrapper on top of each
SKILLS.md, specifying:
- The retrieval tool surface (MCP tools available to the agent)
- The exact on-disk artifact paths under `_brownfield/<BL-id>/` that the
  webapp parses to confirm success
- The terminal JSON completion shape that the SSE stream expects
- The brownfield rubric path the scorer must read

`prompts.select_family(target_status_result)` dispatches between this
module and the greenfield `prompts.py` builders at run time.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

AGENTIC_ROOT = Path(__file__).resolve().parents[4]
SKILLS_DIR = AGENTIC_ROOT / "skills" / "brownfield"

SKILL_PATHS = {
    "po":            SKILLS_DIR / "brownfield-production-incremental-po" / "SKILLS.md",
    "engineer":      SKILLS_DIR / "brownfield-production-incremental-engineer" / "SKILLS.md",
    "qa":            SKILLS_DIR / "brownfield-production-incremental-qa" / "SKILLS.md",
    "doctrine_meta": SKILLS_DIR / "brownfield-production-incremental-doctrine-meta" / "SKILLS.md",
    "acceptance":    SKILLS_DIR / "brownfield-acceptance-agent" / "SKILLS.md",
    "janitor":       SKILLS_DIR / "brownfield-production-incremental-janitor" / "SKILLS.md",
    "onboarder":     SKILLS_DIR / "brownfield-production-incremental-onboarder" / "SKILLS.md",
    "architect":     SKILLS_DIR / "brownfield-production-incremental-architect" / "SKILLS.md",
}


@lru_cache(maxsize=8)
def _load_skill(role: str) -> str:
    """Load the SKILLS.md doctrine for the given role.

    Cached for the process lifetime. If you edit a SKILLS.md and want the
    change to take effect on the next agent run without restarting uvicorn,
    call `_load_skill.cache_clear()` (or use `--reload`, which restarts the
    whole worker).
    """
    path = SKILL_PATHS.get(role)
    if path is None or not path.exists():
        raise FileNotFoundError(f"brownfield SKILLS.md for role={role!r} not found at {path}")
    return path.read_text(encoding="utf-8")


RETRIEVAL_HINT_BROWNFIELD = """\
## Retrieval tools (MCP) — BROWNFIELD MODE

You are working on a real existing codebase. The *target* repo is your
primary source of patterns; the curated reference repo is secondary. Five
retrieval tools are available:

- `mcp__retrieval__target_status()` — INSTANT (<100ms). Returns
  `{kind, source_file_count, languages, has_pyproject, has_tests, top_source_files}`.
  Call this exactly once at the start of every run.
- `mcp__retrieval__semantic_search(query, k=5, source="target"|"reference")`
  Hybrid semantic+keyword search. **For brownfield work, default
  source="target"** — you are looking for how this codebase already does
  things. First call against a given source may take ~10s to warm up
  indexing; each subsequent call is <2s. If a call returns
  `{ok:false, error:"...timeout..."}`, stop using that source.
- `mcp__retrieval__graph_neighbors(symbol, depth=1, source=...)`
  Callers / callees / contains edges for a symbol. Essential for
  understanding blast radius BEFORE editing.
- `mcp__retrieval__graph_find_similar(symbol, k=5, source=...)`
  Structurally similar entities (Jaccard over shared call targets) — use
  this to find the closest existing analog when adding new functionality.
- `mcp__retrieval__graph_summary(path, source=...)`
  Entities and their call targets in a given file.

Rules:
- ALWAYS call `target_status` first.
- **MANDATORY PRE-MODIFICATION GROUNDING — HARNESS-ENFORCED.** Before your
  FIRST `Write`, `Edit`, or `NotebookEdit` tool call, you MUST complete at
  least **3 grounded retrieval calls** drawn from:
  `semantic_search`, `graph_neighbors`, `graph_find_similar`, `graph_summary`.
  (`target_status` is inventory and does NOT count toward the floor.)
  These calls must target the BL's Impacted Components and acceptance
  criteria — e.g., `semantic_search(query="<feature keyword>", source="target")`
  for the area you're about to change, `graph_neighbors(symbol="<existing
  function/class you'll touch>")` to map blast radius, `graph_find_similar`
  to locate the closest analog you should mirror. If you attempt to Write
  or Edit before satisfying this floor, the harness will kill the run and
  emit `_meta phase=pre_grounding_violation`, then re-spawn you with a
  delta prompt — you will lose all in-flight context. **Do retrieval first.**
- For pattern discovery in brownfield: PREFER `source="target"`. Use
  `source="reference"` only as a fallback if the target lacks a relevant
  analog.
- Before modifying ANY existing symbol, call `graph_neighbors` on it to
  understand who depends on it.
- A per-task budget of 30 retrieval calls is enforced.
- Do not retry the same query after a timeout or `{ok:false}` — switch
  tools or proceed with what you have.
"""


# ─────────────────────────────── PO (Brownfield) ───────────────────────────


def build_po_prompt_brownfield(brief: str, project_name: str | None = None, artifact_dir: str = "_brownfield", lessons_block: str = "", contract_block: str = "") -> str:
    name = project_name or "Project"
    skills_md = _load_skill("po")
    body = f"""You are a Brownfield Agile Product Owner. The operational doctrine below is your binding rulebook; you must follow it literally.

## Project Name
{name}

## Brief
{brief}

# ────────────────────────── DOCTRINE (SKILLS.md, binding) ──────────────────────────

{skills_md}
{lessons_block}
# ────────────────────── WEBAPP CONTRACT (in addition to doctrine) ──────────────────────

{RETRIEVAL_HINT_BROWNFIELD}

## Required on-disk artifacts (webapp parses these)

Write all brownfield artifacts under the top-level `_brownfield/` directory
at the root of the target repo:

- `_brownfield/_codebase_context/CODEBASE_CONTEXT.md` — system-wide Codebase Context Summary as defined in the doctrine above.
- `_brownfield/<BL-id>/codebase_context.md` — per-BL codebase context (REQ mapping, impacted components from graph queries, compatibility/migration notes, risk level, spike tasks).
- `.agile-v/BACKLOG.md` — the backlog in this exact header style so the webapp's parser can read it:

   ```
   # Backlog: {name}

   ## Brief comprehension notes
   - Project kind: brownfield
   - Codebase context: `_brownfield/_codebase_context/CODEBASE_CONTEXT.md`
   - <2-5 bullets summarizing target retrieval findings>

   ## BL-0001: <Short Title>
   **Type:** Feature | Technical | Bug · **Priority:** CRITICAL | HIGH | MEDIUM | LOW
   **Story:** As a <user>, I want <capability> so that <value>.
   **REQ mapping:** REQ-XXXX[, REQ-YYYY, ...]
   **Codebase Context Referenced:** `_brownfield/BL-0001/codebase_context.md`
   **Impacted Components:** <file:symbol list from graph queries>
   **Compatibility & Migration Notes:** <breaking? additive? feature-flagged?>
   **Risk Level:** Low | Medium | High
   **Spike Tasks:** <list or "none">
   **Acceptance:**
   1. <testable criterion that names the invariant or contract preserved>
   2. ...
   **Effort:** <1-5> · **Dependencies:** <BL-xxxx or "none"> · **Status:** Ready
   ```

- `_brownfield/SPRINT_PLAN_C1.md` — sprint plan covering Legacy Impact, Risk Register, Capacity Adjustment, Spike Tasks (as required by the doctrine).

## Per-feature isolation (A19 + sibling-feature guard)

This feature has its own dedicated artifact directory under
`_brownfield/features/<this-feature>/`. Other features may exist in
sibling `_brownfield/features/<other>/` directories — **they belong to
other ongoing or completed sprints and are not your concern**.

**BL numbering MUST reset to BL-0001 for THIS feature.** The first item
in your BACKLOG.md is `BL-0001`, the second is `BL-0002`, and so on —
regardless of what BL-IDs appear in sibling-feature backlogs. Do NOT
continue a "global" counter from looking at sibling features. The
doctrine validator will reject a BACKLOG.md whose first BL is not
`BL-0001`.

**Do NOT edit, rename, or delete any files under sibling-feature dirs.**
You may read them for context if helpful, but commits that modify
`_brownfield/features/<other>/...` will be rejected by the doctrine
validator and the orchestrator will refuse to merge your branch.

## Codebase Intelligence Protocol — layer-coverage requirement (A36)

The doctrine's R5 floor of ≥3 grounded retrieval calls is a **count**
floor, not a **coverage** floor. For every BL that introduces or
extends persistent state, a UI surface, or a new route, your retrieval
evidence MUST span **multiple layers** of the target — not three
queries against the same file.

For each BL, identify which of the following layers it touches, then
cite at least one retrieved chunk per touched layer in the BL's
`codebase_context.md`. Mark the citation with the layer name in
parentheses:

- **model layer** — `models.py`, dataclasses, SQLModel/Pydantic classes
- **migration layer** — `alembic/versions/*.py`, schema-change scripts
  (any BL that adds/changes a model MUST include a migration-layer
  citation showing existing `op.create_table` / `op.add_column` calls
  so the engineer matches the project's naming convention)
- **test layer** — `tests/**/*.py`, conftest, fixtures (any BL whose
  diff will touch shared fixtures MUST include a test-layer citation)
- **route layer** — `api/routes/*.py`, frontend `routes/**/*.tsx`,
  router registration sites
- **dependency layer** — `api/deps.py`, dependency-injection wiring,
  middleware
- **frontend build layer** — `routeTree.gen.ts`, generated artifacts,
  lint config (`biome.json`, `.eslintrc`), `tsconfig.build.json`,
  build scripts (any frontend BL MUST include a frontend-build-layer
  citation)

**Per-BL `codebase_context.md` template addition.** Add this block:

```
## Retrieval evidence by layer
- **model:** <file:line> — <one-line why this is the convention>
- **migration:** <file:line> — <one-line why this is the convention>
- **test:** <file:line> — <one-line>
- **route:** <file:line> — <one-line>
- **dependency:** <file:line> — <one-line>
- **frontend build:** <file:line> — <one-line>   (frontend BLs only)

(Mark layers as "n/a — this BL does not touch <layer>" if genuinely
out of scope. Marking a layer n/a is a claim; the doctrine validator
will spot-check that no diff in the engineer's commit touches a layer
marked n/a here.)
```

**Why this exists.** Sprint `run-20260527T160519Z-9811fa` BL-0001
shipped a SQLModel `WorkspaceMember` class with no `__tablename__`
override (correctly matching the default `Item`/`User` convention)
but the Alembic migration in the same commit used
`op.create_table('workspace_member', ...)` (snake_case) — a different
convention. SQLModel emitted `INSERT INTO workspacemember` against a
DB that only had `workspace_member` → 16 test failures, 1 wasted
R10 cycle. The engineer's `eng_patterns.md` cited model-layer
analogs but had no migration-layer citation, because the PO's
grounding requirement only counted retrieval calls. Layer coverage
prevents this class of defect at the source. See A36 in
`DESIGN_SHORTCOMINGS.md` for the full forensic.

## Required completion steps

1. Confirm all four artifacts exist (CODEBASE_CONTEXT.md, every per-BL codebase_context.md, BACKLOG.md, SPRINT_PLAN_C1.md).
2. For every per-BL `codebase_context.md`, confirm the "Retrieval evidence by layer" block is present and each touched layer has at least one citation (file:line). Marking a layer "n/a" is allowed only when the BL genuinely does not touch that layer.
3. `git add -A` then `git commit` with a message of the form:
   `po(brownfield): decompose brief into N backlog items with codebase context`
4. Print ONLY this JSON as your final output (no extra prose):
   {{"status":"complete","backlog_path":".agile-v/BACKLOG.md","context_path":"_brownfield/_codebase_context/CODEBASE_CONTEXT.md","sprint_plan_path":"_brownfield/SPRINT_PLAN_C1.md","item_count":<N>,"commit_sha":"<sha>"}}

Halt conditions (do NOT commit):
- CODEBASE_CONTEXT.md missing or has fewer than 3 invariants listed
- Any BL lacks its per-BL codebase_context.md
- Any BL lacks a REQ mapping
- Any high-blast-radius BL lacks a feature-flag or compatibility strategy
- Any BL's `codebase_context.md` lacks the "Retrieval evidence by layer" block, or has fewer than 3 non-"n/a" layer citations
"""
    if artifact_dir != "_brownfield":
        body = body.replace("_brownfield/", f"{artifact_dir}/").replace("`_brownfield`", f"`{artifact_dir}`")
    # A18 per-feature isolation: when artifact_dir routes through
    # _brownfield/features/<slug>, BACKLOG.md also moves into the feature
    # dir (not the legacy .agile-v/ top-level). Rewrite the hardcoded
    # references in the PO prompt so the agent writes BACKLOG.md alongside
    # CODEBASE_CONTEXT.md and SPRINT_PLAN_C1.md.
    if "/features/" in artifact_dir:
        body = body.replace(".agile-v/BACKLOG.md", f"{artifact_dir}/BACKLOG.md")
    body += contract_block  # Contract-First Phase 1: PO authors the OpenAPI contract
    return body


# ─────────────────────────────── Engineer (Brownfield) ─────────────────────


def build_engineer_prompt_brownfield(bl_id: str, bl_section: str, repo_summary: str = "", artifact_dir: str = "_brownfield", lessons_block: str = "") -> str:
    repo_block = (
        f"\n## Current repo summary\n{repo_summary}\n" if repo_summary.strip() else ""
    )
    skills_md = _load_skill("engineer")
    body = f"""You are a Brownfield Production Incremental Engineer implementing ONE backlog item on an existing real-world codebase. The operational doctrine below is your binding rulebook; you must follow it literally.

## Backlog item to implement
{bl_section}
{repo_block}

# ────────────────────────── DOCTRINE (SKILLS.md, binding) ──────────────────────────

{skills_md}
{lessons_block}
# ────────────────────── WEBAPP CONTRACT (in addition to doctrine) ──────────────────────

{RETRIEVAL_HINT_BROWNFIELD}

## Required reads before any code change

Before writing or editing any code, READ the PO's per-BL context for this slice:
`_brownfield/{bl_id}/codebase_context.md`

It tells you which symbols and files are in scope, the risk level, and any compatibility constraints. Treat it as authoritative for what to look at.

## Required on-disk artifacts

Your "Pattern Matching Summary" (as defined by the doctrine above) MUST be written to:

```
_brownfield/{bl_id}/eng_patterns.md
```

Use this exact structure (the rubric reads it for the Pattern Fidelity score):

```
# Engineer Pattern Matching — {bl_id}

## Closest existing implementations (2-3)
- <repo-relative path>:<line-range> — why it's the closest analog

## Architectural patterns in use here
- Layering: <models→repos→services→routers / etc>
- Naming, error handling, logging, configuration, DI: <one line each with cited example>

## Invariants to preserve in this slice
- <invariant>: <where currently enforced, file:line>

## Integration points / blast radius
- <symbol>: callers=[...], callees=[...]

## Compatibility strategy
- Additive: <yes/no>
- Feature flag: <name, or "none — additive only">
- Migration: <none / data-backfill / dual-write / etc>

## Planned slices (4-8 increments)
1. <slice description, est. test count>
2. ...
```

## Persistent-state consistency rule (A36)

If you introduce a new ORM table class (SQLModel/SQLAlchemy with
`table=True` / `__tablename__` semantics), the migration you write
in the SAME commit MUST use the table name that the ORM actually
emits at runtime:

- If you set `__tablename__ = "<name>"` on the class, the Alembic
  migration MUST call `op.create_table("<name>", ...)` with that
  literal string.
- If you do NOT set `__tablename__`, the ORM default is the lowercased
  class name with no separator (e.g., `class WorkspaceMember` →
  `workspacemember`). The migration MUST use that string, NOT a
  snake_case variant.

Before writing the migration, verify the convention against existing
migrations:

```bash
grep -nE "op\.create_table\(['\"]" backend/app/alembic/versions/*.py | head -5
```

If existing migrations all use single-token lowercase names (no
underscore), follow that convention. If they use `__tablename__`
overrides, match that pattern. Inconsistency between model class and
migration string is the single most common new-table defect class
(see A36 in `DESIGN_SHORTCOMINGS.md` for the BL-0001 documents_2
case study — cost one wasted R10 retry cycle).

## Auto-fix tooling rule (A40)

If a regression gate failure reports a lint/format rule violation
from a tool that advertises auto-fix (biome, ruff, eslint,
prettier, isort, black, etc.) — look for "Safe fix", "auto-fix
available", or `--fix`/`--apply` markers in the gate output — run
the formatter's auto-fix flag and re-stage BEFORE editing the
file by hand:

```bash
# Frontend
bun run check --apply        # or: npx biome check --apply
# Backend
ruff check --fix .
```

Manual edits are reserved for failures the formatter cannot
auto-fix. Burning an R10 retry cycle on a one-character import-order
rewrite (as BL-0008 attempt #2 of `run-20260527T160519Z-9811fa`
did) is the failure mode this rule prevents.

## Required completion steps

1. `_brownfield/{bl_id}/eng_patterns.md` exists and cites the actual analogs you used.
2. Run the full impacted-area test suite once more; pre-existing tests must still pass.
3. If this BL touches persistent state: verify the new model's tablename matches the migration's `op.create_table(...)` string per the Persistent-state consistency rule above.
4. `git status` + `git diff --stat` — if you touched more than 5 files for one BL, justify it in the commit body.
5. `git add -A` then `git commit` with a message of this form:
   `{bl_id}(brownfield): <short description>`

   The commit body MUST include these blocks (the brownfield rubric reads them):

   ```
   Patterns: <ref to eng_patterns.md plus the 2-3 analog files>
   Integration points: <symbols/files this code calls into or extends>
   Tests: <added N (happy, error, invariant, regression)>
   Feature flag: <name or "additive only">
   Files changed: <N> · Lines: +X -Y
   ```

6. Print ONLY this JSON as your final assistant output (no extra prose):
   {{"status":"complete","bl_id":"{bl_id}","commit_sha":"<full sha>","files_changed":<n>,"tests_added":<n>,"feature_flag":"<name or null>","summary":"<brief>"}}

Halt immediately (do NOT commit) if:
- You introduced a pattern materially different from your closest analog
- You modified core legacy code without a feature flag and the change is not strictly additive
- You added a new top-level dependency without justification in the commit body
- You added a new ORM table class whose migration uses a different table-name string than the ORM will emit at runtime
"""
    if artifact_dir != "_brownfield":
        body = body.replace("_brownfield/", f"{artifact_dir}/").replace("`_brownfield`", f"`{artifact_dir}`")
    return body


# ─────────────────────────────── QA (Brownfield) ───────────────────────────


def build_qa_prompt_brownfield(bl_id: str, bl_section: str, artifact_dir: str = "_brownfield", lessons_block: str = "") -> str:
    skills_md = _load_skill("qa")
    body = f"""You are a Brownfield QA Engineer validating ONE backlog item on a real-world codebase. The operational doctrine below is your binding rulebook; you must follow it literally.

## Backlog item under test
{bl_section}

# ────────────────────────── DOCTRINE (SKILLS.md, binding) ──────────────────────────

{skills_md}
{lessons_block}
# ────────────────────── WEBAPP CONTRACT (in addition to doctrine) ──────────────────────

{RETRIEVAL_HINT_BROWNFIELD}

## Required reads before any testing

1. `_brownfield/{bl_id}/codebase_context.md` — PO's impact map.
2. `_brownfield/{bl_id}/eng_patterns.md` — what the engineer touched and what analogs they used.
3. `git log --oneline -20` and `git show --stat HEAD` — what changed in this BL.

## Required on-disk artifacts

Your "Impact & Coverage Analysis" (as defined by the doctrine above) MUST be written to:

```
_brownfield/{bl_id}/qa_impact.md
```

Use this exact structure:

```
# QA Impact & Coverage Analysis — {bl_id}

## Files & components modified
- <path>: <changed lines>

## Upstream / downstream dependencies
- <symbol>: callers=[...], callees=[...]

## Invariants in scope
- <invariant>: <how it can break>

## Existing test coverage of impacted areas
- <test file>: covers <what>

## Coverage gaps to close
- <area>: <test missing>

## Adversarial cases to run
- <attack>: <what it tries to violate>
```

Additionally, write the QA summary report to:

```
.agile-v/qa/{bl_id}.md
```

Use this exact structure (the scorer reads it for Regression Coverage and Characterization Tests dimensions):

```
# QA Report — {bl_id}

## Test results
- Pre-merge suite: <N passing, M failing>
- Post-engineer suite: <N passing, M failing>
- Regressions: <list with file:line, or "none">

## Tests added by QA
- <test path>: <what it covers, category=happy|error|invariant|regression|characterization|contract>

## Invariant verification
- Privacy (404/403): <verdict + how>
- Tenant isolation: <verdict + how>
- <other invariants from REQUIREMENTS.md or impacted-area scope>

## Defects
- <id>: <regression|new>, file:line, repro, mitigation
```

## Required completion steps

1. `_brownfield/{bl_id}/qa_impact.md` and `.agile-v/qa/{bl_id}.md` both exist.
2. `git add -A` then `git commit` with a message of this form:
   `qa({bl_id}, brownfield): <verdict> — N tests added, R regressions`
3. Print ONLY this JSON as your final assistant output (no extra prose):
   {{"status":"complete","bl_id":"{bl_id}","commit_sha":"<full sha>","tests_added":<n>,"regressions":<n>,"new_defects":<n>,"verdict":"PASS|PASS-W/R|FAIL","summary":"<brief>"}}

Verdict guidance (brownfield):
- PASS = all acceptance criteria met, zero regressions, all invariants verified, characterization where needed.
- PASS-W/R = acceptance met but at least one reservation: minor pattern drift or 1–2 characterization tests added retroactively.
- FAIL = any regression, any invariant violation, or any acceptance criterion uncovered.
"""
    if artifact_dir != "_brownfield":
        body = body.replace("_brownfield/", f"{artifact_dir}/").replace("`_brownfield`", f"`{artifact_dir}`")
    return body


# ─────────────────────────────── Scorer (Brownfield) ───────────────────────


def build_score_prompt_brownfield(bl_id: str, bl_section: str, rubric_text: str, artifact_dir: str = "_brownfield", lessons_block: str = "") -> str:
    body = f"""You are a strict, fair scoring agent evaluating ONE backlog item's implementation on a brownfield codebase. You score against the BROWNFIELD rubric, which adds five dimensions (Pattern Fidelity, Regression Coverage, Characterization Tests, Invariant Preservation, Blast Radius) to the standard core+role scoring.

{RETRIEVAL_HINT_BROWNFIELD}
{lessons_block}
## Scorer-specific grounding requirements (HARNESS-ENFORCED)

You are read-only (no source edits) but your scoring is meaningless unless
grounded. The doctrine validator will REJECT your run unless:

1. You make **≥3 grounded retrieval calls** drawn from `semantic_search`,
   `graph_neighbors`, `graph_find_similar`, `graph_summary`. (target_status
   is inventory only; it does NOT count.) Use them to verify Pattern Fidelity
   (find the closest analog), Blast Radius (graph_neighbors on changed symbols),
   and Invariant Preservation (search for related guards / tests).
2. The scorecard you write must contain **≥3 retrieval citations** —
   either explicit `[retrieval: tool(args) → key result]` markers or
   inline `mcp__retrieval__*` tool references — anywhere in the file.
   Embed them in the Evidence cells of the Brownfield Dimensions table.
3. Your verdict must be **rubric-self-consistent**: per the rubric, if any
   Brownfield dimension scores ≤ 2, the verdict MUST be `Fail`. Issuing
   `Pass` or `Pass W/R` with a brownfield dim ≤2 will be rejected by
   the harness and your run re-prompted with the conflict.

## Backlog item
{bl_section}

## Rubric (binding)
{rubric_text}

## Required reads before scoring
1. `_brownfield/<BL-id>/codebase_context.md` (PO's analysis)
2. `_brownfield/<BL-id>/eng_patterns.md` (engineer's pattern matching)
3. `_brownfield/<BL-id>/qa_impact.md` (QA's impact analysis)
4. `.agile-v/qa/<BL-id>.md` (QA report with verdict)
5. The actual diff: `git log --oneline -10`, then `git show <sha>` for each
   commit touching this BL.

If any of files 1–4 are missing, that is direct evidence for a low score
on the corresponding role dimension AND lowers Pattern Fidelity /
Characterization Tests on the brownfield axis. Note missing artifacts
explicitly in the rationale.

## Scoring Protocol
1. Score each Core dimension (10 × 0–5 = 50 max).
2. Score each Role dimension for the relevant role (5 × 0–5 = 25 max).
3. Score each Brownfield dimension (5 × 0–5 = 25 max).
4. Compute total = core + role + brownfield (max 100).
5. Apply decision rules from the rubric:
   - Fail if any Brownfield dimension is ≤ 2
   - Fail if regressions > 0
   - Fail if any invariant provably violated
   - Pass W/R if total ≥ 70 but ≥ 2 brownfield dims are exactly 3
   - Pass if total ≥ 80 with no brownfield dim < 3

## Scorecard format

Write `.agile-v/scorecards/{bl_id}.md` with the following sections:

```
# Scorecard {bl_id} (Brownfield)

## Overall Decision
Decision: <Pass|Pass W/R|Fail>
Total Score: <total>/100 (core <core>/50 + role <role>/25 + brownfield <bf>/25)

## Core Dimensions
| Dimension | Score | Evidence |

## Role-Specific Dimensions (Engineer)
| Dimension | Score | Evidence |

## Brownfield Dimensions
| Dimension | Score | Evidence |
| Pattern Fidelity | <n> | <files cited from eng_patterns.md> |
| Regression Coverage | <n> | <pre/post test counts from qa_impact.md> |
| Characterization Tests | <n> | <test files added> |
| Invariant Preservation | <n> | <adversarial test results> |
| Blast Radius | <n> | <files changed, lines, feature flag> |

## Pattern Fidelity Evidence
- Closest existing analog: <path:lines>
- Conventions matched: <list>
- Deviations: <list or "none">

## Regression Coverage Evidence
- Pre-merge suite: <N pass, M fail>
- Post-merge dry-run suite: <N pass, M fail>
- Regressions introduced: <list or "none">

## Invariant Verification
- Privacy (404/403): <verdict>
- Tenant isolation: <verdict>
- Cascade behavior: <verdict>
- Other invariants: <list>

## Blast Radius
- Files modified: <N>
- Lines added/removed: <+X / -Y>
- Feature flag used: <name or "none — additive only">

## Rationale
<one paragraph>
```

Be honest. Cite specific files / line ranges / commits as evidence. A
perfect 100 is rare; only award it when you have direct evidence for every
dimension.

## Required Completion Steps

You are SCORING only. Do NOT modify production code or tests.

1. Write the scorecard to `.agile-v/scorecards/{bl_id}.md`.
2. Stage and commit: `score(<BL-id>, brownfield): scorecard <total>/100 <verdict>`.
3. Print ONLY this JSON as your final assistant output:
   {{"status":"complete","bl_id":"<BL-XXXX>","commit_sha":"<full sha>","total":<n>,"core":<n>,"role":<n>,"brownfield":<n>,"verdict":"Pass|Pass W/R|Fail","summary":"<one paragraph>"}}
"""
    if artifact_dir != "_brownfield":
        body = body.replace("_brownfield/", f"{artifact_dir}/").replace("`_brownfield`", f"`{artifact_dir}`")
    return body


# ───────────────────── Contract-First Phase 1 (R22) ─────────────────────
# Decision A: PO authors a raw OpenAPI 3.1 contract (HTTP seam, B1).
# Decision (c): the Engineer materializes it into compilable C# stubs.


def po_contract_instruction(artifact_dir: str = "_brownfield") -> str:
    """The block appended to the PO prompt when ``contract_first`` is ON: the
    PO additionally authors the feature's OpenAPI 3.1 HTTP contract."""
    path = f"{artifact_dir}/contract/openapi.yaml"
    return f"""

# ───────────────── CONTRACT-FIRST (R22 — contract_first ON) ─────────────────

In addition to the backlog, you MUST author the feature's HTTP API **contract**
as a single OpenAPI **3.1** document at:

    {path}

This is the agreed interface the implementation slices build against in
parallel (frontend against a mocked client; backend implementing the
endpoints). Derive it from the BLs you just designed — every HTTP endpoint a
BL **Exposes:** becomes a path + operation here. Rules:
- `openapi: 3.1.0`, a real `info.title` / `info.version`, a non-empty `paths`.
- Give EVERY operation a unique, descriptive `operationId` (the materializer
  and the R22 conformance gate key on it).
- Model request/response bodies as `components.schemas` and `$ref` them.
- Cover ONLY the feature's HTTP seam (the endpoints the BLs add/change), not
  the whole existing API.
Write valid YAML. The contract is structurally validated and every operation
in it MUST be materialized as a compilable stub before any slice runs.

## Decompose for PARALLELISM (contract-first — this is the point)
The contract above is the agreed seam, so slices DO NOT depend on each other's
merged code — they depend on the CONTRACT. Decompose accordingly:
- Carve the feature into **file-disjoint VERTICAL slices** (each its own files),
  NOT horizontal layers. A persistence→service→endpoints layer-chain serialises
  to one-BL-per-wave and wastes the parallel crew — avoid it.
- Every cross-slice interface a slice **Consumes:** MUST be in the contract/stubs
  (the materialiser builds them first). Then a consuming slice builds against the
  stub immediately, concurrently with the producer.
- Set **Dependencies: none** for a slice UNLESS it needs true execution ORDERING
  (e.g. a DB migration that must run first). Do NOT add a Dependency merely
  because you Consume a sibling's interface — the contract already provides it
  (adding one needlessly serialises the wave).
- Aim for a backlog whose dependency DAG **fans out**: most slices in wave 0,
  with ordering edges only where genuinely required.
"""


def build_stub_materializer_prompt_brownfield(contract_text: str,
                                              repo_summary: str = "",
                                              artifact_dir: str = "_brownfield") -> str:
    """Engineer-in-CONTRACT-MATERIALIZATION-mode (decision c): turn the agreed
    OpenAPI 3.1 contract into compilable C# server stubs — nothing implemented,
    but the solution builds and every contract operation is represented."""
    repo_block = f"\n## Current repo summary\n{repo_summary}\n" if repo_summary.strip() else ""
    tmpl = """You are a Brownfield Engineer operating in CONTRACT MATERIALIZATION mode.

Your ONE job: turn the agreed OpenAPI 3.1 contract below into **compilable C#
server stubs** committed to this repo. NOTHING is implemented yet — but the
solution MUST build and every contract operation MUST be represented.
__REPO__
__RETRIEVAL__

## The contract (OpenAPI 3.1)
```yaml
__CONTRACT__
```

## What to produce — idiomatic to THIS repo (ground FIRST)
Before writing, ground in the codebase (use retrieval) to match existing
conventions: namespaces, folder layout, base controller class, DI registration
style, DTO/record conventions, nullable settings. Then, for the contract:
- **DTOs / models**: one C# `record` (or class) per `components.schemas` entry,
  in the repo's models namespace/folder.
- **A service interface** (e.g. `I<Feature>Service`) with one method per
  operation, named after its `operationId`.
- **Controller skeleton(s)**: ASP.NET Core controller(s) mapping each operation
  (route + HTTP method from the contract) to an action whose body is
  `throw new NotImplementedException();` and which references the matching
  `operationId` (in the method name and/or an XML-doc comment).
- **DI registration**: register the interface -> stub binding so the app wires up.

## Hard requirements (the R22 gate checks these — no-abort until green)
1. `dotnet build` of the solution MUST succeed (the stubs compile).
2. EVERY operation in the contract MUST be referenced in the generated stubs
   (by its `operationId`, or its route path if it declares none).
3. Do NOT implement business logic, do NOT alter existing behavior, do NOT add
   or change tests — additive stubs only, behind the interface/DI.
4. Commit your stubs as a NEW commit on this branch.

Write the files, run `dotnet build` yourself to confirm green, fix any compile
errors, and commit. The harness independently re-validates (R22)."""
    return (tmpl.replace("__REPO__", repo_block)
                .replace("__RETRIEVAL__", RETRIEVAL_HINT_BROWNFIELD)
                .replace("__CONTRACT__", contract_text))
