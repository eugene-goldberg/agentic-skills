"""Hard pre-commit doctrine validator.

After a brownfield agent run completes, this module checks whether the
artifacts the doctrine (and the webapp prompt contract) require actually
exist in the agent's worktree. If anything is missing, the router can
either reject the commit, re-invoke the agent with a fix prompt, or both.

Each role has its own validator:

- validate_po(repo_root)             — checks CODEBASE_CONTEXT.md,
                                       per-BL context for every BL in
                                       BACKLOG.md, SPRINT_PLAN_C1.md.
- validate_engineer(repo_root, bl_id) — checks eng_patterns.md for the
                                        specific BL.
- validate_qa(repo_root, bl_id)       — checks qa_impact.md + the QA
                                        report (.agile-v/qa/<BL>.md).

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

import re
from pathlib import Path

from app.services import backlog as backlog_svc
from app.services.brownfield import pick_artifact_dir


MIN_ARTIFACT_BYTES = 120  # below this, the file is "empty" (e.g. just a heading)


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


def validate_engineer(repo_root: Path, bl_id: str) -> dict:
    art = pick_artifact_dir(repo_root)
    acc = {"missing": [], "empty": [], "dangling_refs": []}
    _check(repo_root, f"{art}/{bl_id}/eng_patterns.md", acc)
    return _finalize("engineer", acc)


def validate_qa(repo_root: Path, bl_id: str) -> dict:
    art = pick_artifact_dir(repo_root)
    acc = {"missing": [], "empty": [], "dangling_refs": []}
    _check(repo_root, f"{art}/{bl_id}/qa_impact.md", acc)
    _check(repo_root, f".agile-v/qa/{bl_id}.md", acc)
    return _finalize("qa", acc)


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
3. Write each missing/empty file with substantive content (≥120 characters; ideally the structure the doctrine specified).
4. `git add -A` and `git commit --amend --no-edit` so the artifacts join the existing commit (do NOT create a separate commit).
5. Print ONLY the same final JSON shape as your previous run, with the same `commit_sha` (it will change after --amend, use the new sha).

If any of the listed paths require parsing BACKLOG.md or another existing artifact to know what to write, do that first. Do NOT modify BACKLOG.md, do NOT change acceptance criteria — only add the missing companion artifacts.
"""
