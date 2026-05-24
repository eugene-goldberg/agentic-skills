"""Hard pre-commit doctrine validator.

After a brownfield agent run completes, this module checks whether the
artifacts the doctrine (and the webapp prompt contract) require actually
exist in the agent's worktree. If anything is missing, the router can
either reject the commit, re-invoke the agent with a fix prompt, or both.

Each role has its own validator:

- validate_po(repo_root)             — checks CODEBASE_CONTEXT.md,
                                       per-BL context for every BL in
                                       BACKLOG.md, SPRINT_PLAN_C1.md.
- validate_engineer(repo_root, bl_id, base_ref, retrieval_log)
                                       — checks eng_patterns.md,
                                         source-code diff, retrieval grounding.
- validate_qa(repo_root, bl_id, retrieval_log)
                                       — checks qa_impact.md, QA report,
                                         retrieval grounding.

All validators return a dict:
    {
      "ok": bool,
      "missing": [<path>],            # paths that must exist but don't
      "empty":   [<path>],            # paths that exist but are <120 chars
      "dangling_refs": [<path>],      # BACKLOG.md cites these, none exist
      "summary": "<one-line>"
    }
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from app.services import backlog as backlog_svc
from app.services.brownfield import pick_artifact_dir


MIN_ARTIFACT_BYTES = 120  # below this, the file is "empty" (e.g. just a heading)

# Tools that ground the agent in the codebase. target_status is inventory only
# (file counts, metadata) and does not count as grounding evidence.
GROUNDED_RETRIEVAL_TOOLS = {
    "semantic_search",
    "graph_neighbors",
    "graph_find_similar",
    "graph_summary",
}
MIN_GROUNDED_RETRIEVAL_CALLS = 3
MIN_RETRIEVAL_CITATIONS = 3  # number of `mcp__retrieval__` / `[retrieval:` markers in an artifact
MAX_BROWNFIELD_FAIL_FLOOR = 2  # any brownfield dim ≤ this forces Fail verdict


# A citation is any reference like `mcp__retrieval__semantic_search` or
# `[retrieval: tool(args) → result]` inside a doctrine artifact. Distinct
# from just having made the calls — this proves the agent *used* the findings.
CITATION_PATTERN = re.compile(
    r"(?:mcp__retrieval__(?:semantic_search|graph_neighbors|graph_find_similar|graph_summary|target_status)"
    r"|\[retrieval:\s*[^\]]+\])",
    re.IGNORECASE,
)


def _count_retrieval_citations(artifact_path: Path) -> int:
    """Count distinct retrieval citations inside an artifact markdown file."""
    if not artifact_path.exists():
        return 0
    try:
        text = artifact_path.read_text(encoding="utf-8")
    except OSError:
        return 0
    return len(CITATION_PATTERN.findall(text))


def _check_citations(repo_root: Path, artifact_rel: str, accumulator: dict) -> None:
    """R5b: artifact must contain ≥MIN_RETRIEVAL_CITATIONS retrieval markers."""
    p = repo_root / artifact_rel
    n = _count_retrieval_citations(p)
    if n < MIN_RETRIEVAL_CITATIONS:
        accumulator["missing"].append(
            f"<retrieval citations in {artifact_rel}: {n} found, need ≥{MIN_RETRIEVAL_CITATIONS} "
            f"references to mcp__retrieval__* tools or [retrieval: ...] markers>"
        )


def _count_grounded_retrieval(retrieval_log: Path | None) -> int:
    """Count entries in retrieval.jsonl whose tool is a grounding tool.

    Returns 0 if the log is missing, unreadable, or has no grounded calls.
    """
    if retrieval_log is None or not retrieval_log.exists():
        return 0
    n = 0
    try:
        for line in retrieval_log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("tool") in GROUNDED_RETRIEVAL_TOOLS:
                n += 1
    except OSError:
        return 0
    return n


def _check(repo_root: Path, rel: str, accumulator: dict) -> None:
    p = repo_root / rel
    if not p.exists():
        accumulator["missing"].append(rel)
        return
    try:
        sz = len(p.read_text(encoding="utf-8").strip())
    except OSError:
        accumulator["missing"].append(rel)
        return
    if sz < MIN_ARTIFACT_BYTES:
        accumulator["empty"].append(rel)


def _finalize(role: str, acc: dict) -> dict:
    acc["ok"] = not (acc["missing"] or acc["empty"])
    if acc["ok"]:
        acc["summary"] = f"{role}: doctrine artifacts complete"
    else:
        parts = []
        if acc["missing"]:
            parts.append(f"missing={len(acc['missing'])}")
        if acc["empty"]:
            parts.append(f"empty={len(acc['empty'])}")
        if acc.get("dangling_refs"):
            parts.append(f"dangling_refs={len(acc['dangling_refs'])}")
        acc["summary"] = f"{role}: doctrine incomplete — " + ", ".join(parts)
    return acc


def validate_po(repo_root: Path) -> dict:
    art = pick_artifact_dir(repo_root)
    acc = {"missing": [], "empty": [], "dangling_refs": []}

    backlog_path = ".agile-v/BACKLOG.md"
    _check(repo_root, backlog_path, acc)
    _check(repo_root, f"{art}/_codebase_context/CODEBASE_CONTEXT.md", acc)
    _check(repo_root, f"{art}/SPRINT_PLAN_C1.md", acc)

    # Per-BL contexts — parse the BACKLOG and ensure each BL-XXXX has a file.
    bf = repo_root / backlog_path
    if bf.exists():
        items = backlog_svc.parse(bf.read_text(encoding="utf-8"))
        for it in items:
            # backlog_svc.parse returns BacklogItem objects/dicts; tolerate both.
            bl_id = it.get("id") if isinstance(it, dict) else getattr(it, "id", None)
            if not bl_id:
                continue
            rel = f"{art}/{bl_id}/codebase_context.md"
            p = repo_root / rel
            if not p.exists():
                acc["missing"].append(rel)
                acc["dangling_refs"].append(rel)
            else:
                _check(repo_root, rel, acc)
    return _finalize("po", acc)


def validate_engineer(
    repo_root: Path,
    bl_id: str,
    base_ref: str | None = None,
    retrieval_log: Path | None = None,
) -> dict:
    """Engineer doctrine: artifact, non-empty source diff, AND retrieval grounding.

    Without the source-diff check, an engineer run that committed only the
    doctrine doc (e.g. after an API-overload retry storm) would slip through
    a green regression gate trivially — zero code change implies zero
    regressions. The diff guard refuses to declare engineer-doctrine OK
    unless at least one non-artifact, non-pure-doc file changed.

    The retrieval-grounding check ensures the agent actually used
    `semantic_search` / `graph_*` (and not just file I/O or the cheap
    `target_status` inventory tool) — otherwise scores measured against
    the retrieval-grounded brownfield doctrine become meaningless.
    Pass retrieval_log=None to skip this check (e.g. in unit tests).

    R11 no-op terminal state: if base_ref is provided AND the worktree has
    zero file changes vs base_ref AND the eng_patterns.md artifact already
    exists at HEAD (inherited from an earlier BL that delivered this work),
    return ok=True with no_op=True instead of failing on missing source diff.
    This handles the legitimately-redundant-backlog-item case (e.g. BL-0003
    after BL-0005 cascaded the workspace router in early).
    """
    art = pick_artifact_dir(repo_root)
    acc = {"missing": [], "empty": [], "dangling_refs": []}
    artifact_rel = f"{art}/{bl_id}/eng_patterns.md"

    # R11: detect true no-op (zero diff vs base AND artifact already present)
    if base_ref:
        changed_for_noop = _changed_files(repo_root, base_ref)
        artifact_path = repo_root / artifact_rel
        if not changed_for_noop and artifact_path.exists():
            result = _finalize("engineer", acc)  # acc still empty → ok=True
            result["no_op"] = True
            result["summary"] = (
                f"engineer: no-op for {bl_id} — work already satisfied upstream "
                f"(zero diff vs {base_ref}, eng_patterns.md present at HEAD)"
            )
            return result

    _check(repo_root, artifact_rel, acc)
    # R5b: artifact must cite the retrieval evidence used.
    _check_citations(repo_root, artifact_rel, acc)

    if base_ref:
        # R9 fast-forward enforcement: the agent branch must be a clean
        # descendant of target_ref so auto-merge can fast-forward. If the
        # agent rebased / reset / created a sibling commit, the regression
        # gate would still run (wasting ~10 min) and the merge would then
        # fail with non_ff, dumping into awaiting_review. Catch it here.
        if not _is_fast_forward(repo_root, base_ref):
            acc["missing"].append(
                f"<fast-forward to {base_ref}: HEAD is not a descendant of {base_ref} "
                f"(agent rebased or reset history); merge would be non-ff>"
            )

        changed = _changed_files(repo_root, base_ref)
        # Source-y files = anything outside the artifact dir that isn't pure markdown.
        # We deliberately don't enumerate "code extensions" because brownfield targets
        # vary wildly (Python, TS, Go, etc.) — exclusion is the safer floor.
        code_files = [
            f for f in changed
            if not f.startswith(f"{art}/")
            and not f.startswith(".agile-v/")
            and not f.endswith(".md")
        ]
        if not code_files:
            acc["missing"].append(
                f"<source code change for {bl_id}; commit changed only docs/artifacts: "
                f"{', '.join(changed[:5]) or '(no files)'}>"
            )

    if retrieval_log is not None:
        n = _count_grounded_retrieval(retrieval_log)
        if n < MIN_GROUNDED_RETRIEVAL_CALLS:
            acc["missing"].append(
                f"<retrieval grounding: {n} grounded call(s), need ≥{MIN_GROUNDED_RETRIEVAL_CALLS} "
                f"of {sorted(GROUNDED_RETRIEVAL_TOOLS)}>"
            )

    return _finalize("engineer", acc)


def _changed_files(repo_root: Path, base_ref: str) -> list[str]:
    """Return files changed between base_ref and HEAD in the given worktree. Best-effort."""
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            cwd=repo_root, capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return []
        return [line.strip() for line in r.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return []


def _is_fast_forward(repo_root: Path, base_ref: str) -> bool:
    """True iff base_ref is an ancestor of HEAD (i.e. HEAD can fast-forward base_ref).

    Returns False on git error (e.g. unknown ref) — safer to fail loud than
    let an unreachable check declare a divergent branch fast-forwardable.
    """
    try:
        r = subprocess.run(
            ["git", "merge-base", "--is-ancestor", base_ref, "HEAD"],
            cwd=repo_root, capture_output=True, text=True, timeout=15,
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def validate_qa(
    repo_root: Path,
    bl_id: str,
    base_ref: str | None = None,
    retrieval_log: Path | None = None,
) -> dict:
    art = pick_artifact_dir(repo_root)
    acc = {"missing": [], "empty": [], "dangling_refs": []}
    qa_impact_rel = f"{art}/{bl_id}/qa_impact.md"
    _check(repo_root, qa_impact_rel, acc)
    _check(repo_root, f".agile-v/qa/{bl_id}.md", acc)
    # R5b: QA's qa_impact.md must cite retrieval evidence.
    _check_citations(repo_root, qa_impact_rel, acc)

    # R9 fast-forward enforcement: catch divergent QA branches before the gate.
    if base_ref and not _is_fast_forward(repo_root, base_ref):
        acc["missing"].append(
            f"<fast-forward to {base_ref}: HEAD is not a descendant of {base_ref} "
            f"(agent rebased or reset history); merge would be non-ff>"
        )

    if retrieval_log is not None:
        n = _count_grounded_retrieval(retrieval_log)
        if n < MIN_GROUNDED_RETRIEVAL_CALLS:
            acc["missing"].append(
                f"<retrieval grounding: {n} grounded call(s), need ≥{MIN_GROUNDED_RETRIEVAL_CALLS} "
                f"of {sorted(GROUNDED_RETRIEVAL_TOOLS)}>"
            )

    return _finalize("qa", acc)


def _parse_brownfield_dims(scorecard_path: Path) -> list[tuple[str, int]]:
    """Extract (dimension, score) rows from the scorecard's Brownfield table.

    Looks under the `## Brownfield Dimensions` heading for markdown table
    rows like `| Pattern Fidelity | 4 | <evidence> |`. Skips header/separator
    rows. Returns [] if the section is missing or unparseable — caller treats
    that as a missing-section error.
    """
    if not scorecard_path.exists():
        return []
    try:
        text = scorecard_path.read_text(encoding="utf-8")
    except OSError:
        return []
    # Slice from "## Brownfield Dimensions" to next H2 (or EOF)
    m = re.search(
        r"##\s+Brownfield\s+Dimensions\s*\n(.*?)(?=\n##\s|\Z)",
        text, re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return []
    rows: list[tuple[str, int]] = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        dim = cells[0]
        # Skip header (Dimension) and separator (---).
        if dim.lower() == "dimension" or set(dim) <= {"-", ":"}:
            continue
        try:
            score = int(re.search(r"-?\d+", cells[1]).group(0))
        except (AttributeError, ValueError):
            continue
        rows.append((dim, score))
    return rows


def _parse_scorecard_verdict(scorecard_path: Path) -> str:
    """Extract the Decision line (Pass | Pass W/R | Fail). Empty string if missing."""
    if not scorecard_path.exists():
        return ""
    try:
        text = scorecard_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r"Decision:\s*(Pass W/R|Pass|Fail)", text, re.IGNORECASE)
    return m.group(1) if m else ""


def validate_scorer(
    repo_root: Path,
    bl_id: str,
    base_ref: str | None = None,
    retrieval_log: Path | None = None,
) -> dict:
    """Scorer doctrine: scorecard exists, brownfield-axis rubric self-consistent,
    fast-forward to target, AND ≥3 grounded retrieval calls (R12).

    R7: per the brownfield rubric, "Fail if any Brownfield dimension is ≤ 2".
    A scorer that scored a brownfield dim ≤2 but issued Pass / Pass W/R has
    drifted from its own rubric — reject the run.

    Scorer makes no source-code changes (it's read-only), so R3 does not
    apply. R9 fast-forward still applies (a divergent scorer branch can't
    be merged cleanly).
    """
    acc = {"missing": [], "empty": [], "dangling_refs": []}
    scorecard_rel = f".agile-v/scorecards/{bl_id}.md"
    scorecard_path = repo_root / scorecard_rel
    _check(repo_root, scorecard_rel, acc)
    # R5b: scorecard must cite the retrieval evidence the scorer used.
    _check_citations(repo_root, scorecard_rel, acc)

    if base_ref and not _is_fast_forward(repo_root, base_ref):
        acc["missing"].append(
            f"<fast-forward to {base_ref}: HEAD is not a descendant of {base_ref} "
            f"(agent rebased or reset history); merge would be non-ff>"
        )

    # R7: rubric self-consistency.
    if scorecard_path.exists():
        dims = _parse_brownfield_dims(scorecard_path)
        verdict = _parse_scorecard_verdict(scorecard_path)
        if not dims:
            acc["missing"].append(
                "<scorecard parsing: no '## Brownfield Dimensions' table rows found>"
            )
        else:
            low = [(d, s) for d, s in dims if s <= MAX_BROWNFIELD_FAIL_FLOOR]
            if low and verdict.lower() != "fail":
                offenders = ", ".join(f"{d}={s}" for d, s in low)
                acc["missing"].append(
                    f"<rubric self-consistency: brownfield dim(s) {offenders} "
                    f"≤ {MAX_BROWNFIELD_FAIL_FLOOR} but verdict is {verdict or '<missing>'}; "
                    f"rubric requires Fail>"
                )
        if not verdict:
            acc["missing"].append(
                "<scorecard parsing: 'Decision: Pass|Pass W/R|Fail' line not found>"
            )

    # R12: scorer must ground its evaluation in retrieval (semantic_search /
    # graph_*), not just file reads — otherwise scores are model intuition.
    if retrieval_log is not None:
        n = _count_grounded_retrieval(retrieval_log)
        if n < MIN_GROUNDED_RETRIEVAL_CALLS:
            acc["missing"].append(
                f"<retrieval grounding: {n} grounded call(s), need ≥{MIN_GROUNDED_RETRIEVAL_CALLS} "
                f"of {sorted(GROUNDED_RETRIEVAL_TOOLS)}>"
            )

    return _finalize("scorer", acc)


# ─────────────────────── Fix-prompt builder ────────────────────────


def build_fix_prompt(role: str, validation: dict, *, bl_id: str | None = None) -> str:
    """Construct the delta prompt for a re-invocation when the validator fails."""
    missing = validation.get("missing", [])
    empty = validation.get("empty", [])
    items = "\n".join([f"- MISSING: `{p}`" for p in missing] + [f"- EMPTY (<120 bytes): `{p}`" for p in empty])
    role_label = role.upper()
    bl_clause = f" for {bl_id}" if bl_id else ""
    return f"""Your previous {role_label} run committed without writing the doctrine-required artifacts{bl_clause}.

The webapp's pre-merge validator has REJECTED the commit. You are now being re-invoked in the SAME worktree. Write the missing artifacts now, following the SKILLS.md doctrine and the webapp contract for paths.

## Artifacts to produce

{items}

## Required steps

1. Re-read the original prompt's doctrine + contract blocks. The required content of each artifact is defined there in detail.
2. Use retrieval tools (`mcp__retrieval__semantic_search`, `mcp__retrieval__graph_summary`, `mcp__retrieval__graph_neighbors`) to ground the content in the actual target codebase — not just from memory.
3. Write each missing/empty file with substantive content (≥120 characters; ideally the structure the doctrine specified). If the validator flagged "<source code change …>" as missing, you MUST also write the actual implementation source code (e.g. the SQLModel class, FastAPI route, dep, alembic migration, tests) — the artifact doc alone is not the deliverable.
4. `git add -A` and `git commit -m "fix: add doctrine-required artifacts"` to add a NEW commit on top of your previous work.

   **R13 boundary:** the orchestrator owns refs. You must NOT run
   `git commit --amend`, `git rebase`, or `git reset --hard` on your
   branch. The streaming layer will kill any such command. Adding a
   new commit is the only legitimate path; the orchestrator's
   fast-forward merge handles the lineage.

5. Print ONLY the same final JSON shape as your previous run. Use the NEW `commit_sha` (the tip of your branch after step 4).

If any of the listed paths require parsing BACKLOG.md or another existing artifact to know what to write, do that first. Do NOT modify BACKLOG.md, do NOT change acceptance criteria — only add the missing companion artifacts.
"""


# ─────────────────────── R10.2: focused failure extraction ─────────────


_PYTEST_FAIL_HDR = re.compile(r"^_{3,}\s+(?P<name>\S+)\s+_{3,}\s*$", re.MULTILINE)
_PYTEST_RESULT = re.compile(r"^(?P<name>tests?/[\w./:\[\]-]+)\s+FAILED\b", re.MULTILINE)
# Playwright reports failures with a "  N) [chromium] › tests/foo.spec.ts:42:1 › Title" header.
_PLAYWRIGHT_FAIL_HDR = re.compile(
    r"^\s*\d+\)\s+\[\S+\]\s+›\s+(?P<spec>[\w./:-]+)\s+›\s+(?P<title>[^\n]+)$",
    re.MULTILINE,
)


def _extract_test_failures(text: str, *, max_blocks: int = 8, max_block_lines: int = 18) -> str:
    """Pull pytest + Playwright failure blocks out of a noisy gate stdout dump.

    Returns a markdown-ready string. If no structured failures are detected,
    returns the last ~60 lines of the input as a fallback.
    """
    if not text:
        return "(no gate output captured)"

    lines = text.splitlines()
    blocks: list[str] = []

    # pytest: "____ name ____" + body up to next blank-then-non-indented line
    for m in _PYTEST_FAIL_HDR.finditer(text):
        if len(blocks) >= max_blocks:
            break
        start = text[: m.start()].count("\n")
        chunk = lines[start : start + max_block_lines]
        blocks.append("\n".join(chunk))

    # Playwright: "N) [chromium] › spec › title" + ~15 lines of context
    for m in _PLAYWRIGHT_FAIL_HDR.finditer(text):
        if len(blocks) >= max_blocks:
            break
        start = text[: m.start()].count("\n")
        chunk = lines[start : start + max_block_lines]
        blocks.append("\n".join(chunk))

    if blocks:
        return "\n\n---\n\n".join(blocks)
    # Fallback — last 60 lines of input
    return "\n".join(lines[-60:])


def build_gate_fix_prompt(
    role: str,
    gate_result: dict,
    *,
    bl_id: str | None = None,
    attempt: int,
    max_attempts: int,
) -> str:
    """R10.1: delta prompt for an agent whose run failed the regression gate.

    The agent is re-invoked in the SAME worktree. It MUST add a new commit
    on top of its prior work (R13: history-rewriting commands are blocked
    at the streaming layer). The branch stays a fast-forward of target_ref
    automatically; the orchestrator handles ref lineage.
    """
    role_label = role.upper()
    bl_clause = f" for {bl_id}" if bl_id else ""
    regressions = gate_result.get("regressions") or []
    new_failures = gate_result.get("new_failures") or []
    failed_tests = sorted(set(regressions + new_failures))
    post_tail = gate_result.get("post_tail") or ""
    excerpt = _extract_test_failures(post_tail)
    failed_list = "\n".join(f"- `{t}`" for t in failed_tests) or "- (see excerpt below)"

    return f"""Your previous {role_label} run{bl_clause} PASSED doctrine but FAILED the regression gate.

The harness has re-invoked you in the SAME worktree. You have {max_attempts - attempt + 1} retries left (this is attempt {attempt}/{max_attempts}).

## Failing tests (gate reported these as regressions / new failures)

{failed_list}

## Focused failure detail

These are the most-relevant blocks extracted from the gate's stdout (pytest + Playwright). Use them to diagnose root cause. If your tests reference UI affordances, test-ids, or strings that your implementation doesn't actually emit, fix EITHER side so they match — but they MUST be consistent.

```
{excerpt}
```

## Required steps

1. Diagnose: read the failure blocks above. Identify whether the bug is in implementation, in tests, or in setup (fixtures, seed data, env).
2. Fix in source: edit the implementation file(s) and/or test file(s) so the failing tests would pass against a real running stack. Do not delete failing tests just to make the gate green — fix them properly or document why they were wrong.
3. Re-ground if needed: if your fix touches a different area than your original retrieval, call `mcp__retrieval__semantic_search` / `graph_*` again to make sure you understand the new area.
4. `git add -A` and `git commit -m "fix: <one-line summary of the regression fix>"` to add a NEW commit on top of your prior work.

   **R13 boundary:** the orchestrator owns refs. You must NOT run
   `git commit --amend`, `git rebase`, `git reset --hard`, or
   `git push --force` on your branch. The streaming layer will kill
   any such command. Adding a new commit is the only legitimate path;
   the orchestrator's fast-forward merge (or A1 auto-rebase if
   needed) handles the lineage. New commits are always a fast-forward
   of your branch tip.

5. Print ONLY the same final JSON shape as your previous run with the new `commit_sha` (your branch's new tip after step 4).

Doctrine and gate will both re-run after this attempt. If both pass, the branch auto-merges. If either fails after {max_attempts} attempts, the branch is left in awaiting_review for operator decision.
"""
