"""ABL-0001 — Sprint orchestrator.

Replaces the Sprint-1 `nohup bash -c '...'` chain launchers. Runs the full
brief-to-merged-feature pipeline as a single SSE stream:

    preflight → index_initial → po → for each BL: engineer → reindex
                                          → qa → reindex → scorer
    → sprint_complete

Per-role execution is delegated to `stream_agent_task` (the same primitive
the per-role endpoints use), so doctrine validators, retrieval enforcement,
R10.1 gate-failure retries, and regression gates all fire identically to the
hand-driven flow.

All events emitted by this module carry `phase=orchestrator.<step>` so the
v2 UI can render a step-by-step timeline. Per-role SSE events are passed
through verbatim with an added `orchestrator_step` tag so they can be routed
to the correct row in the timeline.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from app.services import backlog as backlog_svc
from app.services import doctrine_validator as doctrine_svc
from app.services import prompts as prompts_svc
from app.services import prompts_brownfield as prompts_brownfield_svc
from app.services import regression_gate as regression_gate_svc
from app.services import retrieval_warmup as retrieval_warmup_svc
from app.services import repo_config as repo_config_svc
from app.services import run_state as run_state_svc
from app.services import closure_check as closure_check_svc
from app.services import acceptance_validator as acceptance_validator_svc
from app.services import volume_reaper as volume_reaper_svc
from app.services import findings_ledger as findings_ledger_svc
from app.services import lessons as lessons_svc
from app.services import lessons_index as lessons_index_svc
from app.services import pattern_profile as pattern_profile_svc
from app.services import global_lessons as global_lessons_svc
from app.services import doctrine_efficacy as doctrine_efficacy_svc
from app.services import doctrine_spec as doctrine_spec_svc
from app.services import traces as traces_svc
from app.services.brownfield import classify_target, feature_artifact_dir
from app.services.claude_agent import stream_agent_task
from app.services.git_worktree import (
    Worktree,
    create_worktree,
    fast_forward_target,
    get_commit_sha,
    has_new_commits,
    merge_branch_into_target,
    remove_worktree,
    reset_target_to,
    rev_parse,
)
from app.services.indexing import run_claude_context_index, run_graphify_update
from app.services.traces import TraceWriter


# ─── helpers ───────────────────────────────────────────────────────────────


def _evt(phase: str, **kwargs) -> dict:
    """Construct an orchestrator-tagged SSE event dict."""
    e = {"type": "_meta", "phase": f"orchestrator.{phase}"}
    e.update(kwargs)
    return e


# A56 part 2: the 4 grounded retrieval tools (target_status is inventory and
# does NOT count toward grounding, matching the R5 floor definition).
_GROUNDED_RETRIEVAL_TOOLS = frozenset({
    "semantic_search", "graph_neighbors", "graph_find_similar", "graph_summary",
})


def _count_po_grounding(trace_dir: str | None) -> int:
    """Count grounded retrieval calls (the 4 tools above) in a PO trace's
    ``retrieval.jsonl``. Returns 0 if the file is absent/empty/unreadable — used
    to surface a grounding-blind PO (A56). Never raises."""
    if not trace_dir:
        return 0
    log = Path(trace_dir) / "retrieval.jsonl"
    if not log.exists():
        return 0
    n = 0
    try:
        for line in log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (ValueError, TypeError):
                continue
            if rec.get("tool") in _GROUNDED_RETRIEVAL_TOOLS:
                n += 1
    except OSError:
        return 0
    return n


async def _rebase_in_worktree(wt_path: Path, target_ref: str) -> dict:
    """A1: rebase the agent branch in its OWN worktree onto target_ref.

    The probe confirmed this must happen inside the worktree (not the main
    checkout) so the agent branch's HEAD advances without disturbing the
    main repo's working tree.

    Returns a merge-shaped dict: {"ok": bool, "kind": "rebased"|"rebase_failed",
    "error": str|None}. On any non-zero exit, attempts `git rebase --abort`
    so the worktree is left clean for the fall-through to awaiting_review.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "rebase", target_ref,
            cwd=str(wt_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)
    except (asyncio.TimeoutError, OSError) as exc:
        return {"ok": False, "kind": "rebase_failed",
                "error": f"{type(exc).__name__}: {exc}"}
    if proc.returncode != 0:
        # Abort so the worktree isn't left in detached-rebase state.
        try:
            abort = await asyncio.create_subprocess_exec(
                "git", "rebase", "--abort",
                cwd=str(wt_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(abort.wait(), timeout=10.0)
        except (asyncio.TimeoutError, OSError):
            pass
        err_text = (stderr or b"").decode(errors="replace")[:500] or f"exit={proc.returncode}"
        return {"ok": False, "kind": "rebase_failed", "error": err_text}
    return {"ok": True, "kind": "rebased", "error": None}


def _qa_commit_landed(repo_dir: Path, bl_id: str, agent_branch: str) -> bool:
    """B12: confirm a `qa(<bl>...)` commit on agent_branch actually touches
    .agile-v/qa/<bl>.md.

    Sprint 2/3 partial_resume relied solely on file existence — a half-written
    QA file from a crashed run would silently bypass real QA. Cross-checking
    git log catches that case. Returns False on any subprocess error so the
    safer path (run QA) wins.
    """
    import subprocess as _subproc
    qa_rel = f".agile-v/qa/{bl_id}.md"
    try:
        out = _subproc.run(
            ["git", "-C", str(repo_dir), "log", agent_branch, "--format=%s", "--", qa_rel],
            capture_output=True, text=True, timeout=5.0, check=False,
        )
    except (_subproc.SubprocessError, OSError):
        return False
    if out.returncode != 0:
        return False
    for subject in (out.stdout or "").splitlines():
        s = subject.strip()
        if s.startswith(f"qa({bl_id}") or s.startswith("qa(") and bl_id in s:
            return True
    return False


def _archive_traces_since(repo_name: str, started_at: datetime, run_id: str) -> int:
    """B15: move trace dirs created during this orchestrator run into
    traces_archive/<run_id>/, keeping the live traces dir clean.

    Only moves dirs whose meta.json carries `finished_at` — skips any trace
    whose writer is still mid-write, eliminating race risk against subprocess
    cleanup. Called from a finally block so it fires on both `sprint_complete`
    and any `orchestrator.aborted` exit path.
    """
    from app.services import traces as traces_mod  # avoid circular at import

    src_root = traces_mod.TRACES_ROOT / traces_mod._slug(repo_name)
    if not src_root.exists():
        return 0
    archive_root = traces_mod.BACKEND_DIR / "traces_archive" / run_id
    started_str = started_at.strftime("%Y%m%dT%H%M%SZ")
    moved = 0
    for child in src_root.iterdir():
        if not child.is_dir():
            continue
        # Trace dir name pattern: <YYYYMMDDTHHMMSSZ>-<role>[-<bl>]-<task_id>
        ts = child.name.split("-", 1)[0]
        if len(ts) != 16 or ts < started_str:
            continue
        meta = child / "meta.json"
        try:
            data = json.loads(meta.read_text())
        except (OSError, ValueError):
            continue
        if "finished_at" not in data:
            continue  # writer still active — leave in place
        archive_root.mkdir(parents=True, exist_ok=True)
        dst = archive_root / child.name
        try:
            shutil.move(str(child), str(dst))
            moved += 1
        except OSError:
            pass
    return moved


def _tag(event: dict, step: str, bl_id: str | None = None) -> dict:
    """Tag a passed-through per-role event with its orchestrator context."""
    event["orchestrator_step"] = step
    if bl_id is not None:
        event.setdefault("bl_id", bl_id)
    return event


def _ptag(event: dict, step: str, bl_id: str | None = None, *, trace=None) -> dict:
    """M2-4 / A13: like _tag, but ALSO persists the event into the per-agent
    trace dir's ``phase_events.jsonl`` when a TraceWriter is given.

    Use for orchestrator-constructed ``_meta phase=...`` events. The
    streaming forward case (passing through agent SDK events) keeps using
    ``_tag`` — those are not phase events from the orchestrator's
    perspective, so they belong only in the agent's stream.jsonl.

    Closes A13's primary failure mode (sealed agent traces lacked the
    enforcement-phase events a reviewer would re-open to verify the
    orchestrator's decisions).
    """
    if (trace is not None
            and event.get("type") == "_meta"
            and "phase" in event):
        trace.write_phase_event(event)
    return _tag(event, step, bl_id)


def _slugify(name: str, *, max_len: int = 40) -> str:
    """Filesystem-safe slug for a project_name. Lowercase alphanumeric+hyphen."""
    import re as _re
    s = _re.sub(r"[^a-zA-Z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return s[:max_len] or "untitled"


def _persist_brief_in_worktree(
    *,
    wt_path: Path,
    artifact_dir: str,
    brief: str,
    run_id: str,
    project_name: str,
    repo_name: str,
    brief_hash: str | None,
    started_at: str,
) -> Path | None:
    """A17: write the operator's verbatim brief into
    ``<worktree>/<artifact_dir>/sprint_briefs/<run_id>-<slug>.md`` so it
    lands inside the PO's brownfield tree. The existing PO copy-back
    (``copytree wt/<art> → repo_dir/<art>``) and ``git add <art>`` flow
    naturally carry it onto the target's agent branch.

    Idempotent: returns the existing path if already written. Best-effort:
    OSError is swallowed so persistence failure never blocks the sprint.
    """
    if not brief or not run_id:
        return None
    target = wt_path / artifact_dir / "sprint_briefs" / f"{run_id}-{_slugify(project_name)}.md"
    if target.exists():
        return target
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        header = (
            f"---\n"
            f"run_id: {run_id}\n"
            f"project_name: {project_name}\n"
            f"repo: {repo_name}\n"
            f"started_at: {started_at}\n"
            f"brief_hash: {brief_hash or '(unset)'}\n"
            f"---\n\n"
        )
        target.write_text(header + brief, encoding="utf-8")
        # A20: also write a canonical `brief.md` at the feature dir root so
        # operators and tooling can find the brief without knowing the run_id.
        # Overwrites on resubmit (latest run wins). The run_id-keyed file
        # above remains as the audit/history copy.
        canonical = wt_path / artifact_dir / "brief.md"
        canonical.write_text(header + brief, encoding="utf-8")
    except OSError:
        return None
    return target


async def _run_indexers(repo_dir: Path, label: str,
                        reindex_incremental: bool = True) -> AsyncIterator[dict]:
    """Run claude-context + graphify, in parallel.

    claude-context op selection (graphify is always its own incremental AST cache):
    - reindex_incremental OFF -> "index" everywhere (full re-embed; the pre-2026-06-15
      behaviour, byte-identical rollback).
    - ON -> index_initial uses "index_baseline" (full embed + establishes the merkle
      snapshot) and every reindex_after_* barrier uses "reindex" (embeds ONLY files
      changed since the snapshot; full-index fallback if the collection is missing).
    """
    if not reindex_incremental:
        _cc_op = "index"
    elif label == "index_initial":
        _cc_op = "index_baseline"
    else:
        _cc_op = "reindex"
    yield _evt(f"{label}.start", cc_op=_cc_op)
    cc_task = asyncio.create_task(run_claude_context_index(repo_dir, op=_cc_op))
    gr_task = asyncio.create_task(run_graphify_update(repo_dir))
    cc, gr = await asyncio.gather(cc_task, gr_task, return_exceptions=True)
    yield _evt(
        f"{label}.done",
        claude_context={"ok": getattr(cc, "get", lambda *_: None)("ok") if isinstance(cc, dict) else False,
                        "summary": cc if isinstance(cc, dict) else str(cc)},
        graphify={"ok": getattr(gr, "get", lambda *_: None)("ok") if isinstance(gr, dict) else False,
                  "summary": gr if isinstance(gr, dict) else str(gr)},
    )


# ─── per-role flows (extracted from projects.py, simplified) ──────────────
#
# Each returns an async iterator of SSE-shaped dicts AND a final outcome dict
# (passed via a sentinel `_orchestrator_outcome` event).


async def _po_flow(
    repo_dir: Path,
    repo_name: str,
    brief: str,
    project_name: str,
    timeout: int,
    retrieval_kwargs_builder,
    *,
    run_id: str | None = None,
    brief_hash: str | None = None,
    feature_slug: str | None = None,
    inject_lessons: bool = False,
    inject_global_lessons: bool = False,
    contract_first: bool = False,
) -> AsyncIterator[dict]:
    cfg = repo_config_svc.load(repo_dir)
    family = cfg.doctrine or prompts_svc.select_family(classify_target(repo_dir))
    prompt = prompts_svc.build_po(family, brief, project_name, repo_dir, feature_slug=feature_slug,
                                  inject_lessons=inject_lessons,
                                  inject_global_lessons=inject_global_lessons,
                                  contract_first=contract_first)
    if inject_lessons and run_id:
        lessons_svc.record_injection(
            run_id, "po",
            lessons_svc.list_lessons(repo_dir, feature_slug, cap=lessons_svc.DEFAULT_LESSON_CAP),
        )
    wt: Worktree | None = None
    trace: TraceWriter | None = None
    try:
        wt = await create_worktree(repo_dir, base_ref=cfg.agent_branch)
        trace = TraceWriter(repo=repo_name, role="po", task_id=wt.task_id)
        yield _ptag({"type": "_meta", "phase": "worktree_ready", "task_id": wt.task_id,
                    "branch": wt.branch, "role": "po", "trace_dir": str(trace.dir)}, "po", trace=trace)

        # A17 + A18: persist the operator's verbatim brief into the worktree's
        # per-feature artifact dir BEFORE the PO subprocess spawns. The PO's
        # copy-back (wt/_brownfield → repo_dir/_brownfield, dirs_exist_ok=True)
        # + git-add carry it onto the target's agent branch naturally.
        # Located inside _brownfield/features/<feature_slug>/ so each feature
        # has its own self-contained artifact tree.
        if run_id:
            _art_for_brief = feature_artifact_dir(repo_dir, feature_slug)
            _brief_path = _persist_brief_in_worktree(
                wt_path=wt.path,
                artifact_dir=_art_for_brief,
                brief=brief,
                run_id=run_id,
                project_name=project_name,
                repo_name=repo_name,
                brief_hash=brief_hash,
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            if _brief_path is not None:
                yield _ptag({"type": "_meta", "phase": "brief_persisted",
                            "path": str(_brief_path.relative_to(wt.path)),
                            "bytes": _brief_path.stat().st_size,
                            "run_id": run_id,
                            "feature_slug": feature_slug}, "po", trace=trace)

        rk = retrieval_kwargs_builder(wt, "po", None, trace)
        async for event in stream_agent_task(prompt, wt.path, timeout_seconds=timeout, trace=trace, **rk):
            yield _tag(event, "po")
        # doctrine
        validation = doctrine_svc.validate_po(wt.path, feature_slug=feature_slug, contract_first=contract_first)
        attempt = 0
        while not validation["ok"] and attempt < 2:
            attempt += 1
            yield _ptag({"type": "_meta", "phase": "doctrine_check", "kind": "incomplete",
                        "attempt": attempt, **validation}, "po", trace=trace)
            fix = doctrine_svc.build_fix_prompt("po", validation)
            async for event in stream_agent_task(fix, wt.path, timeout_seconds=max(300, timeout // 2),
                                                  trace=trace, **rk):
                yield _tag(event, "po")
            validation = doctrine_svc.validate_po(wt.path, feature_slug=feature_slug, contract_first=contract_first)
        yield _ptag({"type": "_meta", "phase": "doctrine_check",
                    "kind": "complete" if validation["ok"] else "give_up",
                    "attempts": attempt, "summary": validation["summary"]}, "po", trace=trace)
        # A18: import artifacts back to repo if doctrine passed.
        # Copy-back uses dirs_exist_ok=True so the events.jsonl and brief.md
        # that already exist in <target>/_brownfield/features/<slug>/ (written
        # by the router and by _persist_brief_in_worktree) are preserved.
        if validation["ok"]:
            from shutil import copytree
            import subprocess
            # Pre-A18 sprints used .agile-v/BACKLOG.md; keep it as a fallback
            # copy when no feature_slug is set.
            if not feature_slug:
                from shutil import copy2
                src_bl = wt.path / ".agile-v" / "BACKLOG.md"
                if src_bl.exists():
                    dst_bl = repo_dir / ".agile-v" / "BACKLOG.md"
                    dst_bl.parent.mkdir(parents=True, exist_ok=True)
                    copy2(src_bl, dst_bl)
            # Always copy the whole _brownfield/ subtree (carries A18
            # features/<slug>/{brief.md, BACKLOG.md, CODEBASE_CONTEXT.md, …}
            # plus any pre-A18 legacy artifacts).
            src_bf = wt.path / "_brownfield"
            if src_bf.exists():
                dst_bf = repo_dir / "_brownfield"
                dst_bf.parent.mkdir(parents=True, exist_ok=True)
                copytree(src_bf, dst_bf, dirs_exist_ok=True)
            add_paths = ["_brownfield/"]
            if not feature_slug:
                add_paths.insert(0, ".agile-v/")
            subprocess.run(["git", "add", *add_paths], cwd=repo_dir, check=False)
            subprocess.run(["git", "commit", "-m", f"po: import backlog from {wt.branch}",
                           "--author", "Claude PO Agent <po@webapp.local>"],
                          cwd=repo_dir, check=False)
        yield {"_orchestrator_outcome": True, "role": "po", "doctrine_ok": validation["ok"]}
    finally:
        if trace is not None:
            trace.close()
        if wt is not None:
            try:
                await remove_worktree(repo_dir, wt)
            except Exception:
                pass


def _resolve_engineer_section(
    repo_dir: Path,
    bl_id: str,
    feature_slug: str | None,
    section_override: str | None,
) -> str:
    """Resolve the bl_section fed to ``build_engineer``.

    ABL-0015: when ``section_override`` is provided (auto-dispatch
    follow-up), use it verbatim and skip the BACKLOG lookup entirely — a
    synthetic ``BL-ACCEPT-…`` has no BACKLOG entry, so
    ``extract_section`` would fail. Overriding only the *section* (not the
    whole prompt) keeps every doctrine scaffold from
    ``build_engineer_prompt_brownfield`` intact (eng_patterns.md artifact
    path, retrieval-grounding, R5b citations), so the follow-up engineer
    clears ``validate_engineer`` on the same terms as any BL.
    """
    if section_override is not None:
        return section_override
    bf = backlog_svc.find_backlog(repo_dir, feature_slug=feature_slug)
    return backlog_svc.extract_section(bf.read_text(encoding="utf-8"), bl_id)


async def _engineer_flow(
    repo_dir: Path,
    repo_name: str,
    bl_id: str,
    timeout: int,
    retrieval_kwargs_builder,
    *,
    run_id: str | None = None,
    feature_slug: str | None = None,
    section_override: str | None = None,
    task_id: str | None = None,
    inject_lessons: bool = False,
    inject_global_lessons: bool = False,
    defer_merge: bool = False,  # wave-concurrency Strategy A: gate-pass leaves the
                                # work on wt.branch (which survives worktree removal)
                                # instead of FF-merging into agent_branch; the wave
                                # barrier assembles work-branches in BL-id order.
    contract_first: bool = False,  # Phase C: per-BL engineer builds against the
                                   # materialized contract stubs + mocks collaborators.
) -> AsyncIterator[dict]:
    cfg = repo_config_svc.load(repo_dir)
    family = cfg.doctrine or prompts_svc.select_family(classify_target(repo_dir))
    section = _resolve_engineer_section(repo_dir, bl_id, feature_slug, section_override)
    prompt = prompts_svc.build_engineer(family, bl_id, section, repo_dir, feature_slug=feature_slug,
                                        inject_lessons=inject_lessons,
                                        inject_global_lessons=inject_global_lessons,
                                        contract_first=contract_first)
    if inject_lessons and run_id:
        lessons_svc.record_injection(
            run_id, "engineer",
            lessons_svc.list_lessons(repo_dir, feature_slug, cap=lessons_svc.DEFAULT_LESSON_CAP),
            bl_id=bl_id,
        )

    wt: Worktree | None = None
    trace: TraceWriter | None = None
    merged = False
    no_op = False
    # No-abort doctrine: always-defined so the escalation dossier can be built
    # on any not-merged exit (doctrine never passed, gate never went green, …).
    gate: dict | None = None
    # A58: the MERGE result is a distinct failure surface from the gate. A
    # green gate followed by a failed merge_to_target (e.g. dirty target
    # checkout) must still route to the Janitor and produce an honest dossier,
    # so keep the merge outcome always-defined for the not-merged exit.
    merge: dict | None = None
    gate_attempt = 0
    gate_signatures: list[str] = []
    try:
        # ABL-0015: a caller-supplied task_id gives the worktree a
        # scannable, run_id-bearing name so closure_check can detect a
        # leak (see scan_stale_followup_worktrees). Normal BLs pass None
        # and get the auto-generated uuid as before.
        wt = await create_worktree(repo_dir, task_id, base_ref=cfg.agent_branch)
        trace = TraceWriter(repo=repo_name, role="engineer", bl_id=bl_id, task_id=wt.task_id)
        yield _ptag({"type": "_meta", "phase": "worktree_ready", "task_id": wt.task_id,
                    "branch": wt.branch, "bl_id": bl_id, "role": "engineer",
                    "trace_dir": str(trace.dir)}, "engineer", bl_id, trace=trace)
        rk = retrieval_kwargs_builder(wt, "engineer", bl_id, trace)
        async for event in stream_agent_task(prompt, wt.path, timeout_seconds=timeout,
                                              trace=trace, min_pregrounding=3, **rk):
            yield _tag(event, "engineer", bl_id)

        validation = doctrine_svc.validate_engineer(wt.path, bl_id, base_ref=cfg.agent_branch,
                                                    retrieval_log=trace.retrieval_path, feature_slug=feature_slug)
        if validation.get("no_op"):
            yield _ptag({"type": "_meta", "phase": "no_op", "bl_id": bl_id,
                        "summary": validation["summary"]}, "engineer", bl_id, trace=trace)
            no_op = True
            yield {"_orchestrator_outcome": True, "role": "engineer", "bl_id": bl_id,
                   "merged": False, "no_op": True}
            return
        # doctrine retries (no-abort doctrine: deep, not the old cap of 2)
        attempt = 0
        while not validation["ok"] and attempt < MAX_FIX_ATTEMPTS:
            attempt += 1
            yield _ptag({"type": "_meta", "phase": "doctrine_check", "kind": "incomplete",
                        "attempt": attempt, **validation}, "engineer", bl_id, trace=trace)
            fix = doctrine_svc.build_fix_prompt("engineer", validation, bl_id=bl_id)
            async for event in stream_agent_task(fix, wt.path, timeout_seconds=max(300, timeout // 2),
                                                  trace=trace, **rk):
                yield _tag(event, "engineer", bl_id)
            validation = doctrine_svc.validate_engineer(wt.path, bl_id, base_ref=cfg.agent_branch,
                                                        retrieval_log=trace.retrieval_path, feature_slug=feature_slug)
        yield _ptag({"type": "_meta", "phase": "doctrine_check",
                    "kind": "complete" if validation["ok"] else "give_up",
                    "attempts": attempt, "summary": validation["summary"]}, "engineer", bl_id, trace=trace)

        new_commits = await has_new_commits(wt, base_ref="HEAD~1")
        if validation["ok"] and new_commits > 0:
            # Simple gating model (operator 2026-06-06): run ONLY this BL's own
            # unit tests (the test files its commits added) — NOT the full suite,
            # NOT Playwright. Whole-feature E2E + full-suite regression run once
            # at the acceptance phase.
            gate = await regression_gate_svc.run_bl_tests(repo_dir, agent_branch=wt.branch,
                                                          base_ref=cfg.agent_branch, run_id=run_id,
                                                          bl_id=bl_id, feature_slug=feature_slug)
            yield _ptag({"type": "_meta", "phase": "bl_tests",
                        **{k: gate.get(k) for k in ("ok", "kind", "regressions", "failing_tests", "reason", "post_tail", "uncovered_criteria")}},
                       "engineer", bl_id, trace=trace)
            gate_attempt = 0
            gate_signatures.append(f"{gate.get('kind')}:{','.join(sorted((gate.get('regressions') or []) + (gate.get('new_failures') or [])))}")
            # No-abort doctrine: keep fixing until the BL's tests are GREEN.
            # Retry on `failed` (a real unit-test failure to fix), `no_tests`
            # (engineer must add the required unit tests), or `coverage_gap` (R19:
            # a PO acceptance criterion has no covering test). `error` is
            # operator-infra → break and escalate with a dossier.
            while not gate.get("ok") and gate.get("kind") in ("failed", "no_tests", "coverage_gap") and gate_attempt < MAX_FIX_ATTEMPTS:
                gate_attempt += 1
                if gate.get("kind") == "no_tests":
                    fix = (f"Your BL {bl_id} added no unit tests. Doctrine requires comprehensive "
                           "unit tests covering this BL's behavior. Add them now (e.g. under "
                           "`backend/tests/...` as `test_*.py`), make them pass, and commit a NEW "
                           "commit. The harness will run ONLY your BL's tests.")
                elif gate.get("kind") == "coverage_gap":
                    uncovered = gate.get("uncovered_criteria") or []
                    fix = (f"R19 — your BL {bl_id} left these PO acceptance criteria UNCOVERED by "
                           f"any test: {', '.join(uncovered)}. Each acceptance criterion is the "
                           "contract and MUST have at least one dedicated test that references its "
                           "id (put the id, e.g. `AC-BL-0001-2`, in the test name, docstring, or a "
                           "comment) and asserts the exact behavior that criterion specifies — "
                           "success paths AND the failure/edge paths it names. Add a covering test "
                           "for EACH uncovered criterion, make them pass, and commit a NEW commit.")
                else:
                    fix = doctrine_svc.build_gate_fix_prompt("engineer", gate, bl_id=bl_id,
                                                             attempt=gate_attempt, max_attempts=MAX_FIX_ATTEMPTS)
                async for event in stream_agent_task(fix, wt.path,
                                                      timeout_seconds=max(300, timeout // 2),
                                                      trace=trace, **rk):
                    yield _tag(event, "engineer", bl_id)
                validation = doctrine_svc.validate_engineer(wt.path, bl_id,
                                                            base_ref=cfg.agent_branch,
                                                            retrieval_log=trace.retrieval_path, feature_slug=feature_slug)
                if not validation["ok"]:
                    break
                gate = await regression_gate_svc.run_bl_tests(repo_dir, agent_branch=wt.branch,
                                                              base_ref=cfg.agent_branch, run_id=run_id,
                                                              bl_id=bl_id, feature_slug=feature_slug)
                yield _ptag({"type": "_meta", "phase": "bl_tests",
                            "gate_attempt": gate_attempt,
                            **{k: gate.get(k) for k in ("ok", "kind", "regressions", "failing_tests", "reason", "post_tail")}},
                           "engineer", bl_id, trace=trace)
            if validation["ok"] and gate.get("ok") and defer_merge:
                # wave-concurrency Strategy A: the gate PASSED but we do NOT
                # integrate into agent_branch here. The engineer's commits live on
                # wt.branch, which SURVIVES the finally worktree removal; the wave
                # barrier assembles work-branches deterministically in BL-id order.
                yield _ptag({"type": "_meta", "phase": "work_ready",
                            "branch": wt.branch, "bl_id": bl_id},
                           "engineer", bl_id, trace=trace)
                yield {"_orchestrator_outcome": True, "role": "engineer", "bl_id": bl_id,
                       "merged": False, "deferred_ready": True, "work_branch": wt.branch,
                       "no_op": no_op}
                return
            if validation["ok"] and gate.get("ok"):
                merge = await fast_forward_target(repo_dir, wt.branch, target_ref=cfg.agent_branch)
                # If transient (lock race, etc.), one retry with a short sleep
                # before falling through to awaiting_review.
                if not merge.get("ok") and merge.get("kind") == "error":
                    await asyncio.sleep(2)
                    merge_retry = await fast_forward_target(repo_dir, wt.branch, target_ref=cfg.agent_branch)
                    if merge_retry.get("ok"):
                        merge = merge_retry
                # A1: non_ff caused by an operator commit racing the agent
                # worktree (Sprint 3 BL-0005 root cause). Rebase the agent
                # branch in its OWN worktree onto target_ref, re-run the
                # gate (the new SHA wasn't tested), and re-attempt the ff.
                if not merge.get("ok") and merge.get("kind") == "non_ff":
                    yield _ptag({"type": "_meta", "phase": "merge_rebase_attempt",
                                "branch": wt.branch, "target_ref": cfg.agent_branch},
                               "engineer", bl_id, trace=trace)
                    rebase = await _rebase_in_worktree(wt.path, cfg.agent_branch)
                    if rebase.get("ok"):
                        yield _ptag({"type": "_meta", "phase": "merge_rebase_succeeded",
                                    "branch": wt.branch}, "engineer", bl_id, trace=trace)
                        gate2 = await regression_gate_svc.run_gate(repo_dir, agent_branch=wt.branch,
                                                                   target_ref=cfg.agent_branch, run_id=run_id)
                        yield _ptag({"type": "_meta", "phase": "regression_gate", "post_rebase": True,
                                    **{k: gate2.get(k) for k in ("ok","kind","regressions","failing_tests","reason","post_tail")}},
                                   "engineer", bl_id, trace=trace)
                        if gate2.get("ok"):
                            merge = await fast_forward_target(repo_dir, wt.branch,
                                                              target_ref=cfg.agent_branch)
                        else:
                            # Gate failed on rebased SHA — leave for review.
                            merge = {"ok": False, "kind": "non_ff_gate_failed_post_rebase",
                                     "error": gate2.get("reason")}
                    else:
                        yield _ptag({"type": "_meta", "phase": "merge_rebase_failed",
                                    "error": rebase.get("error"), "branch": wt.branch},
                                   "engineer", bl_id, trace=trace)
                merged = bool(merge.get("ok"))
                yield _ptag({"type": "_meta", "phase": "merge_to_target",
                            "ok": merge.get("ok"), "merged_sha": merge.get("merged_sha"),
                            "kind": merge.get("kind"), "error": merge.get("error"),
                            "branch": wt.branch},
                           "engineer", bl_id, trace=trace)
            else:
                yield _ptag({"type": "_meta", "phase": "awaiting_review",
                            "reason": gate.get("reason") or "doctrine incomplete"},
                           "engineer", bl_id, trace=trace)
        # No-abort doctrine (Option A): a not-merged engineer has exhausted its
        # deep investigate→fix→re-test loop without a green gate. This is NOT a
        # routine abort — surface a full dossier so the orchestrator escalates to
        # the operator with the complete picture of what was tried and why it's
        # blocked. (no_op returned earlier; merged falls through to plain outcome.)
        if not merged and not no_op:
            last_failing = sorted((gate.get("regressions") or []) + (gate.get("new_failures") or [])) if gate else []
            # A58: a MERGE-step failure (the gate was green but the branch could
            # not be integrated — e.g. a dirty target checkout) is a NON-CODE
            # blocker the Janitor owns, NOT a code defect the engineer's own
            # investigate→fix→re-test loop owns. Detect it so (a) the Janitor
            # trigger fires (it keyed only off `last_gate_kind`, which is "green"
            # here) and (b) the escalation reason names the real blocker instead
            # of the canned "could not reach a green gate".
            merge_failed = bool(gate and gate.get("ok")) and merge is not None and not merge.get("ok")
            dossier = {
                "role": "engineer", "bl_id": bl_id,
                "doctrine_ok": bool(validation.get("ok")),
                "doctrine_attempts": attempt,
                "gate_attempts": gate_attempt,
                "last_gate_kind": gate.get("kind") if gate else None,
                "last_gate_reason": (gate.get("reason") if gate else None) or validation.get("summary"),
                "last_failing_tests": last_failing[:50],
                "first_failure_signature": gate_signatures[0] if gate_signatures else None,
                "exhausted_ceiling": gate_attempt >= MAX_FIX_ATTEMPTS,
                # ABL-0002: the failed attempt branch survives worktree removal — record
                # it so the Architect can `git diff` exactly what the engineer tried.
                "agent_branch_failed": wt.branch if wt is not None else None,
            }
            if merge_failed:
                dossier["blocker"] = "merge_error"
                dossier["merge_kind"] = merge.get("kind")
                dossier["merge_error"] = merge.get("error")
                # A59: the agent branch survives worktree removal — record it so
                # the orchestrator can RE-ATTEMPT the merge after the Janitor
                # repairs the environment (full resolution, not repair-and-escalate).
                dossier["merge_branch"] = wt.branch
            yield {"_orchestrator_outcome": True, "role": "engineer", "bl_id": bl_id,
                   "merged": False, "no_op": False, "escalated": True, "dossier": dossier}
            return
        yield {"_orchestrator_outcome": True, "role": "engineer", "bl_id": bl_id,
               "merged": merged, "no_op": no_op}
    finally:
        if trace is not None:
            trace.close()
        if wt is not None:
            try:
                await remove_worktree(repo_dir, wt)
            except Exception:
                pass


async def _qa_or_scorer_flow(
    repo_dir: Path,
    repo_name: str,
    bl_id: str,
    role: str,  # "qa" or "scorer"
    timeout: int,
    retrieval_kwargs_builder,
    *,
    run_id: str | None = None,
    feature_slug: str | None = None,
    inject_lessons: bool = False,
    inject_global_lessons: bool = False,
    bl_base_ref: str | None = None,
    base_branch_override: str | None = None,  # wave-concurrency: fork the QA/scorer
                                              # worktree from the engineer's work_branch
                                              # (not agent_branch) so it sees that BL's work.
    merge_target_override: str | None = None,  # wave-concurrency: QA FF-merges its tests
                                               # back into the work_branch, NOT agent_branch.
) -> AsyncIterator[dict]:
    cfg = repo_config_svc.load(repo_dir)
    family = cfg.doctrine or prompts_svc.select_family(classify_target(repo_dir))
    # wave-concurrency Strategy A: in concurrent mode the QA/scorer worktree forks
    # from (and the doctrine diff is computed against) the engineer's work_branch,
    # and QA FF-merges back into that same work_branch. Default (overrides None) ⇒
    # the serial behaviour is byte-identical (both resolve to cfg.agent_branch).
    _base_ref = base_branch_override or cfg.agent_branch
    _merge_target = merge_target_override or cfg.agent_branch
    bf = backlog_svc.find_backlog(repo_dir, feature_slug=feature_slug)
    section = backlog_svc.extract_section(bf.read_text(encoding="utf-8"), bl_id)
    if role == "qa":
        prompt = prompts_svc.build_qa(family, bl_id, section, repo_dir, feature_slug=feature_slug,
                                      inject_lessons=inject_lessons,
                                      inject_global_lessons=inject_global_lessons)
    else:
        prompt = prompts_svc.build_score(family, bl_id, section, repo_dir, feature_slug=feature_slug,
                                         inject_lessons=inject_lessons,
                                         inject_global_lessons=inject_global_lessons)
    if inject_lessons and run_id:
        lessons_svc.record_injection(
            run_id, role,
            lessons_svc.list_lessons(repo_dir, feature_slug, cap=lessons_svc.DEFAULT_LESSON_CAP),
            bl_id=bl_id,
        )

    wt: Worktree | None = None
    trace: TraceWriter | None = None
    merged = False
    # No-abort doctrine: always-defined for the escalation dossier.
    gate: dict | None = None
    gate_attempt = 0
    try:
        wt = await create_worktree(repo_dir, base_ref=_base_ref)
        trace = TraceWriter(repo=repo_name, role=role, bl_id=bl_id, task_id=wt.task_id)
        yield _ptag({"type": "_meta", "phase": "worktree_ready", "task_id": wt.task_id,
                    "branch": wt.branch, "bl_id": bl_id, "role": role,
                    "trace_dir": str(trace.dir)}, role, bl_id, trace=trace)
        rk = retrieval_kwargs_builder(wt, role, bl_id, trace)
        pregrounding = 3 if role == "qa" else 0
        async for event in stream_agent_task(prompt, wt.path, timeout_seconds=timeout,
                                              trace=trace, min_pregrounding=pregrounding, **rk):
            yield _tag(event, role, bl_id)

        if role == "qa":
            validation = doctrine_svc.validate_qa(wt.path, bl_id, base_ref=_base_ref,
                                                  retrieval_log=trace.retrieval_path, feature_slug=feature_slug)
        else:
            validation = doctrine_svc.validate_scorer(wt.path, bl_id, base_ref=_base_ref,
                                                     retrieval_log=trace.retrieval_path, feature_slug=feature_slug)
        attempt = 0
        # No-abort doctrine: deep doctrine-fix loop (was a shallow cap of 2).
        while not validation["ok"] and attempt < MAX_FIX_ATTEMPTS:
            attempt += 1
            yield _ptag({"type": "_meta", "phase": "doctrine_check", "kind": "incomplete",
                        "attempt": attempt, **validation}, role, bl_id, trace=trace)
            fix = doctrine_svc.build_fix_prompt(role, validation, bl_id=bl_id)
            async for event in stream_agent_task(fix, wt.path, timeout_seconds=max(300, timeout // 2),
                                                  trace=trace, **rk):
                yield _tag(event, role, bl_id)
            if role == "qa":
                validation = doctrine_svc.validate_qa(wt.path, bl_id, base_ref=_base_ref,
                                                      retrieval_log=trace.retrieval_path, feature_slug=feature_slug)
            else:
                validation = doctrine_svc.validate_scorer(wt.path, bl_id, base_ref=_base_ref,
                                                         retrieval_log=trace.retrieval_path, feature_slug=feature_slug)
        yield _ptag({"type": "_meta", "phase": "doctrine_check",
                    "kind": "complete" if validation["ok"] else "give_up",
                    "attempts": attempt, "summary": validation["summary"]}, role, bl_id, trace=trace)

        new_commits = await has_new_commits(wt, base_ref="HEAD~1")
        if role == "qa" and validation["ok"] and new_commits > 0:
            # Simple gating model: QA executes the BL's own tests. base_ref is the
            # PRE-BL sha (before the engineer merged) so the diff captures the
            # engineer's BL tests + any QA characterization tests — not the full
            # suite, not Playwright (those run once at acceptance).
            _bl_base = bl_base_ref or cfg.agent_branch
            gate = await regression_gate_svc.run_bl_tests(repo_dir, agent_branch=wt.branch,
                                                          base_ref=_bl_base, run_id=run_id,
                                                          bl_id=bl_id, feature_slug=feature_slug)
            yield _ptag({"type": "_meta", "phase": "bl_tests",
                        **{k: gate.get(k) for k in ("ok", "kind", "regressions", "failing_tests", "reason", "post_tail", "uncovered_criteria")}},
                       role, bl_id, trace=trace)
            gate_attempt = 0
            while not gate.get("ok") and gate.get("kind") in ("failed", "no_tests", "coverage_gap") and gate_attempt < MAX_FIX_ATTEMPTS:
                gate_attempt += 1
                if gate.get("kind") == "no_tests":
                    fix = (f"No unit tests are associated with BL {bl_id}. Doctrine requires the "
                           "BL to carry comprehensive unit tests. Add the missing tests (e.g. under "
                           "`backend/tests/...` as `test_*.py`), make them pass, and commit.")
                elif gate.get("kind") == "coverage_gap":
                    uncovered = gate.get("uncovered_criteria") or []
                    fix = (f"R19 — BL {bl_id} left these PO acceptance criteria UNCOVERED by any "
                           f"test: {', '.join(uncovered)}. Add a dedicated test per uncovered "
                           "criterion that references its id (e.g. `AC-BL-0001-2`) and asserts the "
                           "behavior it specifies, make them pass, and commit a NEW commit.")
                else:
                    fix = doctrine_svc.build_gate_fix_prompt("qa", gate, bl_id=bl_id,
                                                             attempt=gate_attempt, max_attempts=MAX_FIX_ATTEMPTS)
                async for event in stream_agent_task(fix, wt.path,
                                                      timeout_seconds=max(300, timeout // 2),
                                                      trace=trace, **rk):
                    yield _tag(event, role, bl_id)
                validation = doctrine_svc.validate_qa(wt.path, bl_id, base_ref=_base_ref,
                                                      retrieval_log=trace.retrieval_path, feature_slug=feature_slug)
                if not validation["ok"]:
                    break
                gate = await regression_gate_svc.run_bl_tests(repo_dir, agent_branch=wt.branch,
                                                              base_ref=_bl_base, run_id=run_id,
                                                              bl_id=bl_id, feature_slug=feature_slug)
                yield _ptag({"type": "_meta", "phase": "bl_tests",
                            "gate_attempt": gate_attempt,
                            **{k: gate.get(k) for k in ("ok", "kind", "regressions", "failing_tests", "reason", "post_tail", "uncovered_criteria")}},
                           role, bl_id, trace=trace)
            if validation["ok"] and gate.get("ok"):
                merge = await fast_forward_target(repo_dir, wt.branch, target_ref=_merge_target)
                if not merge.get("ok") and merge.get("kind") == "error":
                    await asyncio.sleep(2)
                    merge_retry = await fast_forward_target(repo_dir, wt.branch, target_ref=_merge_target)
                    if merge_retry.get("ok"):
                        merge = merge_retry
                # A1: same non_ff auto-rebase as the engineer flow — operator
                # commits race QA worktrees too.
                if not merge.get("ok") and merge.get("kind") == "non_ff":
                    yield _ptag({"type": "_meta", "phase": "merge_rebase_attempt",
                                "branch": wt.branch, "target_ref": _merge_target},
                               role, bl_id, trace=trace)
                    rebase = await _rebase_in_worktree(wt.path, _merge_target)
                    if rebase.get("ok"):
                        yield _ptag({"type": "_meta", "phase": "merge_rebase_succeeded",
                                    "branch": wt.branch}, role, bl_id, trace=trace)
                        gate2 = await regression_gate_svc.run_gate(repo_dir, agent_branch=wt.branch,
                                                                   target_ref=_merge_target, run_id=run_id)
                        yield _ptag({"type": "_meta", "phase": "regression_gate", "post_rebase": True,
                                    **{k: gate2.get(k) for k in ("ok","kind","regressions","failing_tests","reason","post_tail")}},
                                   role, bl_id, trace=trace)
                        if gate2.get("ok"):
                            merge = await fast_forward_target(repo_dir, wt.branch,
                                                              target_ref=_merge_target)
                        else:
                            merge = {"ok": False, "kind": "non_ff_gate_failed_post_rebase",
                                     "error": gate2.get("reason")}
                    else:
                        yield _ptag({"type": "_meta", "phase": "merge_rebase_failed",
                                    "error": rebase.get("error"), "branch": wt.branch},
                                   role, bl_id, trace=trace)
                merged = bool(merge.get("ok"))
                yield _ptag({"type": "_meta", "phase": "merge_to_target",
                            "ok": merge.get("ok"), "merged_sha": merge.get("merged_sha"),
                            "kind": merge.get("kind"), "error": merge.get("error"),
                            "branch": wt.branch},
                           role, bl_id, trace=trace)
            else:
                yield _ptag({"type": "_meta", "phase": "awaiting_review",
                            "reason": gate.get("reason")}, role, bl_id, trace=trace)
        elif role == "scorer" and validation["ok"] and new_commits > 0:
            # Scorecard persistence (open-item #2, 2026-06-07): the scorer is
            # READ-ONLY (validate_scorer: "makes no source-code changes, so R3
            # does not apply"), so A55's QA-only regression gate has nothing to
            # run for it. Doctrine validation alone gates the merge. The QA-only
            # *gate* above is correct under A55; what was wrong is that the
            # *merge* was also QA-only, so the committed, ff-validated scorecard
            # (.agile-v/scorecards/<bl>.md) was dropped on the reaped scorer
            # worktree and never reached the agent_branch. Persist it via a
            # gate-FREE fast-forward (mirrors the QA merge mechanics minus the
            # gate + post-rebase gate re-run, which a read-only branch can't
            # regress).
            merge = await fast_forward_target(repo_dir, wt.branch, target_ref=_merge_target)
            if not merge.get("ok") and merge.get("kind") == "error":
                await asyncio.sleep(2)
                merge_retry = await fast_forward_target(repo_dir, wt.branch, target_ref=_merge_target)
                if merge_retry.get("ok"):
                    merge = merge_retry
            # A1: same non_ff auto-rebase as the QA/engineer flows — QA worktrees
            # advance the agent_branch under the scorer. No post-rebase gate:
            # the scorer changes no source, so nothing can regress.
            if not merge.get("ok") and merge.get("kind") == "non_ff":
                yield _ptag({"type": "_meta", "phase": "merge_rebase_attempt",
                            "branch": wt.branch, "target_ref": _merge_target},
                           role, bl_id, trace=trace)
                rebase = await _rebase_in_worktree(wt.path, _merge_target)
                if rebase.get("ok"):
                    yield _ptag({"type": "_meta", "phase": "merge_rebase_succeeded",
                                "branch": wt.branch}, role, bl_id, trace=trace)
                    merge = await fast_forward_target(repo_dir, wt.branch, target_ref=_merge_target)
                else:
                    yield _ptag({"type": "_meta", "phase": "merge_rebase_failed",
                                "error": rebase.get("error"), "branch": wt.branch},
                               role, bl_id, trace=trace)
            merged = bool(merge.get("ok"))
            yield _ptag({"type": "_meta", "phase": "merge_to_target",
                        "ok": merge.get("ok"), "merged_sha": merge.get("merged_sha"),
                        "kind": merge.get("kind"), "error": merge.get("error"),
                        "branch": wt.branch},
                       role, bl_id, trace=trace)
        # No-abort doctrine: an escalation dossier the per-BL loop attaches if QA
        # could not complete (doctrine give-up or merge failure) — so the run
        # escalates to the operator with the full picture, never silently aborts.
        _last_failing = sorted((gate.get("regressions") or []) + (gate.get("new_failures") or [])) if gate else []
        qa_dossier = {
            "role": role, "bl_id": bl_id,
            "doctrine_ok": bool(validation.get("ok")),
            "doctrine_attempts": attempt,
            "gate_attempts": gate_attempt,
            "last_gate_kind": gate.get("kind") if gate else None,
            "last_gate_reason": (gate.get("reason") if gate else None) or validation.get("summary"),
            "last_failing_tests": _last_failing[:50],
            "exhausted_ceiling": gate_attempt >= MAX_FIX_ATTEMPTS,
        }
        yield {"_orchestrator_outcome": True, "role": role, "bl_id": bl_id,
               "merged": merged, "doctrine_ok": validation["ok"],
               # A2: surface doctrine summary so the per-BL loop can emit
               # qa_doctrine_failed with diagnostic detail.
               "doctrine_summary": validation.get("summary"),
               "dossier": qa_dossier}
    finally:
        if trace is not None:
            trace.close()
        if wt is not None:
            try:
                await remove_worktree(repo_dir, wt)
            except Exception:
                pass


# ─── janitor flow (Janitor / Ops-Steward — environment-anomaly investigator) ──
# Operator directive 2026-06-07: wire the Janitor with full §6 authority. The
# orchestrator DETECTS a non-code failure (merge precondition error, infra_fail,
# git/worktree/config error) and spawns this agent to INVESTIGATE → REPAIR →
# VERIFY → signal retry — the no-abort doctrine applied to the *environment*.
#
# Architecturally distinct from engineer/QA/scorer: it runs in the REAL repo_dir
# (NOT an isolated worktree) because its whole job is to repair the harness's
# relationship to the target (branch checkout, working-tree hygiene, leaked
# resources, config). R13's universal FORBIDDEN_GIT_RE streaming-kill in
# stream_agent_task is the hard backstop on its §6 forbidden ops (history
# rewrite, force-push, reset --hard, …) — which is what makes "full authority"
# safe. See PROPOSAL_OPS_STEWARD_ROLE.md + R16 in doctrine_spec.py.

# Non-code failure kinds that warrant a Janitor spawn. Code-defect gate kinds
# (failed / no_tests / regressed / inconclusive) are OWNED by the engineer/QA
# no-abort loop and must NOT route here — clean separation prevents the Janitor
# masking a real test failure (SKILLS "Why you were spawned").
JANITOR_NONCODE_KINDS = frozenset({"error", "infra_fail"})


def _engineer_janitor_trigger(dossier: dict, run_janitor: bool) -> bool:
    """A58: should the engineer-path Janitor fire for this escalation dossier?

    Two non-code blocker surfaces, both owned by the Janitor (NOT the engineer's
    own investigate→fix→re-test loop, which owns code-defect gate kinds):

    1. a non-code GATE kind (``error`` / ``infra_fail``); or
    2. a MERGE-step failure that escalated AFTER a green gate
       (``blocker == "merge_error"``) — the engineer-path analogue of the QA
       merge-failed branch. This previously slipped through because the guard
       inspected only ``last_gate_kind``, which is ``"green"`` when the gate
       passed but ``merge_to_target`` failed (e.g. a dirty target checkout).
    """
    if not run_janitor:
        return False
    return (dossier.get("last_gate_kind") in JANITOR_NONCODE_KINDS
            or dossier.get("blocker") == "merge_error")


def _should_remerge_after_janitor(dossier: dict) -> bool:
    """A59: after the Janitor runs on a merge failure, RE-ATTEMPT the merge iff
    it was a merge_error, the Janitor reported the environment ``repaired``, and
    we recorded the branch to merge. This is the "agent fully resolves its own
    issue" standard — a dirty checkout is something a competent engineer just
    cleans and re-merges, so the Janitor must complete the resolution in-loop
    rather than repair-and-still-escalate.
    """
    return (dossier.get("blocker") == "merge_error"
            and (dossier.get("janitor") or {}).get("status") == "repaired"
            and bool(dossier.get("merge_branch")))


def _build_janitor_task(skill: str, *, run_id: str, feature_slug: str | None,
                        failed_step: str, blocker_reason: str, failing_role: str,
                        bl_id: str | None, agent_branch: str, main_ref: str,
                        report_rel: str, report_json_rel: str) -> str:
    """Per-dispatch task prompt for the Janitor. Mirrors _build_acceptance_task:
    SKILLS doctrine + a focused failure-context block + explicit deliverables."""
    slug = feature_slug or "(no-feature)"
    return (
        f"{skill}\n\n---\n\n"
        f"# Janitor dispatch — environment repair\n\n"
        f"A non-code orchestration step just FAILED. You are spawned to "
        f"investigate and repair the harness/environment so the run can "
        f"proceed. You are running in the REAL target repo checkout (not an "
        f"isolated worktree), so your repairs act on the live run state.\n\n"
        f"## Failure context (verbatim harness signal)\n"
        f"- run_id: `{run_id}`\n"
        f"- feature_slug: `{slug}`\n"
        f"- failed step: `{failed_step}`\n"
        f"- failing role: `{failing_role}`\n"
        f"- BL: `{bl_id or '(sprint-level)'}`\n"
        f"- blocker: {blocker_reason}\n\n"
        f"## Invariants you MUST preserve\n"
        f"- configured agent branch (fork point + merge sink): `{agent_branch}`\n"
        f"- pristine upstream (NEVER mutate except to preserve its pristine "
        f"state): `{main_ref}`\n"
        f"- NEVER edit target feature code or tests; NEVER mask a code defect.\n\n"
        f"## Deliverables (BOTH required)\n"
        f"1. Investigation+repair report → `{report_rel}`\n"
        f"2. Machine-readable verdict JSON → `{report_json_rel}` (exact schema "
        f"in your SKILLS 'Deliverables'). Set `retry:true` ONLY if you VERIFIED "
        f"the blocking precondition now passes; `classification:\"structural\"` "
        f"(+ `proposed_framework_fix`) if this is a framework defect that will "
        f"recur.\n"
    )


async def _janitor_flow(
    repo_dir: Path,
    repo_name: str,
    run_id: str,
    feature_slug: str | None,
    *,
    failed_step: str,
    blocker_reason: str,
    failing_role: str,
    bl_id: str | None = None,
    timeout: int = 1800,
) -> AsyncIterator[dict]:
    """Spawn the Janitor to repair a non-code failure in the real repo checkout.

    Yields the agent's stream events, optional structural-anomaly + done events,
    and a terminal ``_orchestrator_outcome`` with
    ``{role:"janitor", status, retry, classification, verdict}``.

    Advisory by contract: a Janitor crash or unreadable verdict NEVER aborts the
    run — it degrades to ``status="escalated", retry=False`` so the caller falls
    through to the existing Option-A escalation. R16."""
    cfg = repo_config_svc.load(repo_dir)
    slug = feature_slug or "_no_feature"
    step_safe = failed_step.replace("/", "_").replace(" ", "_")
    janitor_dir = repo_dir / "_brownfield" / "features" / slug / "janitor"
    report_rel = f"_brownfield/features/{slug}/janitor/{step_safe}-{run_id}.md"
    report_json_rel = f"_brownfield/features/{slug}/janitor/{step_safe}-{run_id}.json"
    try:
        janitor_dir.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass

    yield _evt("janitor.start", run_id=run_id, bl_id=bl_id, failed_step=failed_step,
               failing_role=failing_role, blocker=blocker_reason[:500],
               report=report_rel)

    # Advisory contract (R16): NOTHING below may propagate — a Janitor failure
    # (crash, bad config, unloadable skill) must never abort the run. Everything
    # from skill-load through stream is wrapped; on any error we degrade to an
    # escalated/no-retry verdict so the caller falls through to its normal
    # Option-A escalation.
    trace = None
    verdict: dict = {}
    try:
        skill = prompts_brownfield_svc._load_skill("janitor")
        task = _build_janitor_task(
            skill, run_id=run_id, feature_slug=feature_slug, failed_step=failed_step,
            blocker_reason=blocker_reason, failing_role=failing_role, bl_id=bl_id,
            agent_branch=getattr(cfg, "agent_branch", "agentic-skills-work"),
            main_ref=getattr(cfg, "main_ref", "main"),
            report_rel=report_rel, report_json_rel=report_json_rel)
        trace = TraceWriter(repo=repo_name, role="janitor", bl_id=bl_id or run_id, task_id=run_id)
        async for event in stream_agent_task(
            task, repo_dir, timeout_seconds=timeout, idle_timeout=900,
            allowed_tools="Bash,Read,Write,Edit", trace=trace,
        ):
            event.setdefault("orchestrator_step", "janitor")
            yield event
    except Exception as exc:  # noqa: BLE001 — advisory: a Janitor crash never aborts the run
        yield _evt("janitor.error", run_id=run_id, bl_id=bl_id, error=str(exc)[:500])
    finally:
        if trace is not None:
            try:
                trace.close()
            except Exception:  # noqa: BLE001
                pass

    # Read the deterministic sidecar verdict (disk-based, like acceptance's
    # report.json — never trust stdout parsing).
    report_json_abs = repo_dir / report_json_rel
    if report_json_abs.exists():
        try:
            verdict = json.loads(report_json_abs.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            yield _evt("janitor.verdict.error", run_id=run_id, bl_id=bl_id,
                       error=str(exc)[:300], path=report_json_rel)
            verdict = {}

    status = verdict.get("status") if isinstance(verdict, dict) else None
    classification = verdict.get("classification") if isinstance(verdict, dict) else None
    retry = bool(verdict.get("retry")) if isinstance(verdict, dict) else False
    if status not in ("repaired", "escalated"):
        # No usable verdict → conservative escalation, no retry.
        status, retry = "escalated", False
    if status != "repaired":
        retry = False  # never retry on an escalation

    # §5 self-hardening (I-7): a structural anomaly is a FRAMEWORK defect that
    # will recur — surface it so the doctrine-meta-agent fixes the cause once,
    # not the Janitor band-aiding it run after run.
    if classification == "structural":
        yield _evt("janitor.structural_anomaly", run_id=run_id, bl_id=bl_id,
                   failed_step=failed_step,
                   signature=(verdict.get("root_cause") or blocker_reason)[:300],
                   proposed_framework_fix=verdict.get("proposed_framework_fix"),
                   report=report_rel)

    yield _evt("janitor.done", run_id=run_id, bl_id=bl_id, failed_step=failed_step,
               status=status, classification=classification, retry=retry,
               root_cause=(verdict.get("root_cause") if isinstance(verdict, dict) else None),
               actions=(verdict.get("actions") if isinstance(verdict, dict) else None))
    yield {"_orchestrator_outcome": True, "role": "janitor", "run_id": run_id,
           "bl_id": bl_id, "failed_step": failed_step, "status": status,
           "classification": classification, "retry": retry, "verdict": verdict}


async def _run_janitor(repo_dir: Path, repo_name: str, run_id: str,
                       feature_slug: str | None, *, failed_step: str,
                       blocker_reason: str, failing_role: str,
                       bl_id: str | None, timeout: int) -> AsyncIterator[dict]:
    """Thin driver around _janitor_flow used by run_brief: re-yields the stream
    events and captures the terminal outcome on a private attribute the caller
    reads after iteration. Keeps the run-loop call sites small."""
    outcome: dict | None = None
    async for e in _janitor_flow(repo_dir, repo_name, run_id, feature_slug,
                                 failed_step=failed_step, blocker_reason=blocker_reason,
                                 failing_role=failing_role, bl_id=bl_id, timeout=timeout):
        if "_orchestrator_outcome" in e:
            outcome = e
            continue
        yield e
    _run_janitor.last_outcome = outcome  # type: ignore[attr-defined]


# ─── ABL-0002 Stage 1: the Architect — in-sprint judgment at code-gate exhaustion ──
# A new crew role (NOT the Janitor — operator 2026-06-11). The Janitor repairs the
# ENVIRONMENT on non-code failures; the Architect makes the engineering JUDGMENT the
# confined engineer cannot at a CODE-gate exhaustion: re-frame the problem, defer the
# BL with rationale (continue the sprint), or honestly escalate — instead of halting.
# Mirrors _janitor_flow exactly (spawn → deterministic JSON sidecar verdict → act).
# split/respec verdicts are recorded but treated as escalate in Stage 1 (Stage 2 adds
# backlog mutation). Operator-gated (run_architect, default OFF); no-abort (default
# verdict on a missing/garbage sidecar is escalate).

_ARCHITECT_VERDICTS = frozenset(
    {"retry_reframed", "split", "defer", "respec", "escalate"})


def _architect_should_adjudicate(dossier: dict, run_architect: bool) -> bool:
    """Adjudicate a CODE-gate exhaustion only. Merge/env failures are the Janitor's
    lane (blocker == "merge_error" or a non-code gate kind never reaches here as a
    code defect). Fires once per BL at the escalation seam."""
    if not run_architect or not isinstance(dossier, dict):
        return False
    return dossier.get("blocker") != "merge_error"


def _build_architect_adjudicate_task(
    skill: str, *, run_id: str, feature_slug: str | None, bl_id: str,
    dossier: dict, agent_branch_failed: str | None,
    report_rel: str, report_json_rel: str,
) -> str:
    slug = feature_slug or "_no_feature"
    backlog_rel = f"_brownfield/features/{slug}/BACKLOG.md"
    diff_hint = (
        f"- The engineer's FAILED attempt is on branch `{agent_branch_failed}` — "
        f"inspect it with `git diff {agent_branch_failed}` / `git show {agent_branch_failed}` "
        f"to see exactly what it tried."
        if agent_branch_failed else
        "- The engineer's worktree was reaped; reason from the dossier + the codebase."
    )
    return (
        f"{skill}\n\n---\n\n"
        f"# Architect dispatch — MODE: adjudicate ({bl_id}, run {run_id})\n\n"
        f"An engineer exhausted its gate-fix retries on **{bl_id}** and the sprint is "
        f"about to halt. Take the step-back decision it structurally cannot. Ground "
        f"everything in the real code (Read/Grep/git); falsify before you affirm.\n\n"
        f"## The failure dossier (verbatim)\n```json\n{json.dumps(dossier, indent=2)[:4000]}\n```\n\n"
        f"## Your inputs\n"
        f"- The BL spec: read the `{bl_id}` section of `{backlog_rel}`.\n"
        f"{diff_hint}\n"
        f"- The failing tests + signature are in the dossier; OPEN the failing test AND "
        f"the source it exercises before deciding.\n\n"
        f"## Decide ONE verdict (least-disruptive that is honestly correct):\n"
        f"- `retry_reframed` — the engineer mis-framed it; you can point to WHAT it missed. "
        f"Return a precise corrected `directive` (root cause file:line + the exact change + "
        f"the analog to mirror). It gets ONE fresh bounded re-run.\n"
        f"- `defer` — genuinely blocked on something out of this sprint's scope (a product "
        f"decision, a pre-existing defect, a dependency on a later BL). Return `defer_reason` "
        f"(what's blocked + what's needed). The sprint CONTINUES with the other BLs.\n"
        f"- `escalate` — a true wall a senior engineer would also hit. Honest terminal.\n"
        f"- `split` / `respec` — (record your recommendation; Stage-1 treats these as escalate).\n\n"
        f"## Deliverables (BOTH — the orchestrator reads the JSON, never stdout)\n"
        f"1. A grounded report at `{report_rel}` (what you reviewed, grounding with file:line, "
        f"the decision + why, alternatives considered).\n"
        f"2. The EXACT JSON verdict at `{report_json_rel}`:\n"
        f"```json\n"
        f'{{"mode":"adjudicate","bl_id":"{bl_id}",'
        f'"verdict":"retry_reframed|split|defer|respec|escalate",'
        f'"directive":"<reframed fix directive>"|null,'
        f'"defer_reason":"<what is blocked + what is needed>"|null,'
        f'"split_recommendation":"<ordered sub-BLs>"|null,'
        f'"respec_recommendation":"<corrected spec>"|null,'
        f'"root_cause":"<one line, cited file:line>","summary":"<brief>"}}\n```\n'
        f"Then emit that same JSON as your final assistant message. No-abort: if you "
        f"cannot stand behind a resolution, `verdict=\"escalate\"` with a cited root_cause."
    )


async def _architect_flow(
    repo_dir: Path, repo_name: str, run_id: str, feature_slug: str | None, *,
    bl_id: str, dossier: dict, timeout: int,
) -> AsyncIterator[dict]:
    """Spawn the Architect in adjudicate mode over a code-gate-exhaustion dossier.
    Reads a deterministic JSON sidecar verdict. Advisory: a crash never aborts the
    run (the caller falls back to the normal escalation)."""
    cfg = repo_config_svc.load(repo_dir)
    slug = feature_slug or "_no_feature"
    arch_dir = repo_dir / "_brownfield" / "features" / slug / "architect"
    report_rel = f"_brownfield/features/{slug}/architect/adjudicate-{bl_id}-{run_id}.md"
    report_json_rel = f"_brownfield/features/{slug}/architect/adjudicate-{bl_id}-{run_id}.json"
    try:
        arch_dir.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass

    yield _evt("architect.start", run_id=run_id, bl_id=bl_id, mode="adjudicate",
               report=report_rel)

    trace = None
    verdict: dict = {}
    try:
        skill = prompts_brownfield_svc._load_skill("architect")
        task = _build_architect_adjudicate_task(
            skill, run_id=run_id, feature_slug=feature_slug, bl_id=bl_id,
            dossier=dossier, agent_branch_failed=dossier.get("agent_branch_failed"),
            report_rel=report_rel, report_json_rel=report_json_rel)
        trace = TraceWriter(repo=repo_name, role="architect", bl_id=bl_id, task_id=run_id)
        async for event in stream_agent_task(
            task, repo_dir, timeout_seconds=timeout, idle_timeout=900,
            allowed_tools="Bash,Read,Grep,Glob,Write", trace=trace,
        ):
            event.setdefault("orchestrator_step", "architect")
            yield event
    except Exception as exc:  # noqa: BLE001 — advisory: an Architect crash never aborts
        yield _evt("architect.error", run_id=run_id, bl_id=bl_id, error=str(exc)[:500])
    finally:
        if trace is not None:
            try:
                trace.close()
            except Exception:  # noqa: BLE001
                pass

    report_json_abs = repo_dir / report_json_rel
    if report_json_abs.exists():
        try:
            verdict = json.loads(report_json_abs.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            yield _evt("architect.verdict.error", run_id=run_id, bl_id=bl_id,
                       error=str(exc)[:300], path=report_json_rel)
            verdict = {}

    v = verdict.get("verdict") if isinstance(verdict, dict) else None
    if v not in _ARCHITECT_VERDICTS:
        v = "escalate"  # conservative default on a missing/garbage sidecar
    # Stage 1 has no backlog-mutation authority yet: split/respec are honoured as a
    # recommendation on the dossier but resolved as an escalation.
    effective = v if v in ("retry_reframed", "defer", "escalate") else "escalate"

    yield _evt("architect.done", run_id=run_id, bl_id=bl_id, mode="adjudicate",
               verdict=v, effective_verdict=effective,
               root_cause=(verdict.get("root_cause") if isinstance(verdict, dict) else None))
    yield {"_orchestrator_outcome": True, "role": "architect", "run_id": run_id,
           "bl_id": bl_id, "verdict": effective, "raw_verdict": v,
           "directive": (verdict.get("directive") if isinstance(verdict, dict) else None),
           "defer_reason": (verdict.get("defer_reason") if isinstance(verdict, dict) else None),
           "root_cause": (verdict.get("root_cause") if isinstance(verdict, dict) else None),
           "report": report_rel, "verdict_doc": verdict}


async def _run_architect(repo_dir: Path, repo_name: str, run_id: str,
                         feature_slug: str | None, *, bl_id: str, dossier: dict,
                         timeout: int) -> AsyncIterator[dict]:
    """Thin driver around _architect_flow (mirrors _run_janitor): re-yields stream
    events, stashes the terminal verdict on a private attribute."""
    outcome: dict | None = None
    async for e in _architect_flow(repo_dir, repo_name, run_id, feature_slug,
                                   bl_id=bl_id, dossier=dossier, timeout=timeout):
        if "_orchestrator_outcome" in e:
            outcome = e
            continue
        yield e
    _run_architect.last_outcome = outcome  # type: ignore[attr-defined]


# ─── onboarding flow (the Janitor/Ops-Steward in ONBOARDING MODE) ─────────────
# Prepares a brand-new target repo for autonomous brownfield work BEFORE the
# first sprint: fulfils ENVIRONMENT prerequisites a `git clone` doesn't bring
# (deps, runtime/toolchain, services/DB, gitignored config, missing migrations),
# wires the gate config + harness hygiene + integration branch, and verifies the
# target builds/boots and the test command EXECUTES. It PROVISIONS THE
# ENVIRONMENT; it never edits the target's committed source to fix defects (those
# are flagged, not rectified). Operator-invoked (no auto-trigger yet); the
# orchestrator independently verifies the postconditions rather than trusting the
# agent's self-report.


def _build_onboarding_task(skill: str, *, run_id: str, repo_name: str,
                           main_ref: str, report_rel: str, report_json_rel: str,
                           brief: str | None) -> str:
    """Per-dispatch task prompt for the Onboarder. Mirrors _build_janitor_task."""
    if brief and brief.strip():
        brief_block = ("## What the crew will build next (CONTEXT ONLY — do NOT "
                       f"build it; only prepare the environment)\n{brief.strip()}\n\n")
    else:
        brief_block = ("## No specific brief yet — prepare the repo for general "
                       "brownfield work.\n\n")
    return (
        f"{skill}\n\n---\n\n"
        f"# Onboarding dispatch — prepare a brand-new target repo\n\n"
        f"You are spawned in ONBOARDING MODE in the REAL checkout of a target "
        f"repo the crew has never worked on. Fulfil its ENVIRONMENT prerequisites "
        f"so the crew can begin: install/restore dependencies, provision services "
        f"it needs (e.g. a database container), materialise gitignored config from "
        f"a committed template, generate required-but-absent artifacts "
        f"(migrations/schema), derive the gate config, add harness `.gitignore` "
        f"hygiene, write `.agentic-skills.json`, fork the integration branch, and "
        f"verify it builds, boots (if it has a runtime), and that `test_cmd` "
        f"EXECUTES. You PROVISION THE ENVIRONMENT; you NEVER edit the target's "
        f"committed source or tests to fix a pre-existing defect — a red baseline "
        f"caused by a SOURCE defect is FLAGGED in your verdict, not rectified.\n\n"
        f"## Run context\n"
        f"- run_id: `{run_id}`\n"
        f"- repo: `{repo_name}`\n"
        f"- detect the real default branch; keep it pristine. Suggested main_ref: "
        f"`{main_ref}`\n\n"
        f"{brief_block}"
        f"## Deliverables (BOTH required)\n"
        f"1. Onboarding report → `{report_rel}`\n"
        f"2. Machine-readable verdict JSON → `{report_json_rel}` (exact schema in "
        f"your SKILLS 'Deliverables'). Set `status:\"onboarded\"` + `retry:true` "
        f"ONLY when every environment postcondition is verified; otherwise "
        f"`status:\"escalated\"` with the precise missing prerequisite.\n"
    )


def _verify_onboarding_postconditions(repo_dir: Path) -> dict:
    """Independent (orchestrator-side) check of the onboarding contract — the
    trust gate. Do NOT rely on the agent's self-reported verdict alone. Cheap,
    deterministic structural checks. Returns {ok, checks:{...}, missing:[...]}.

    Note: running `test_cmd` to prove it executes is deferred to the first gate
    invocation; here we assert the structural prerequisites the gate depends on.
    """
    checks: dict = {}
    missing: list[str] = []

    cfg_path = repo_dir / repo_config_svc.CONFIG_FILENAME
    cfg_ok = False
    try:
        if cfg_path.exists():
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            cfg_ok = bool(data.get("test_cmd"))
    except Exception:  # noqa: BLE001
        cfg_ok = False
    checks["agentic_skills_json"] = cfg_ok
    if not cfg_ok:
        missing.append(".agentic-skills.json missing/invalid or has no test_cmd")

    cfg = repo_config_svc.load(repo_dir)
    agent_branch = getattr(cfg, "agent_branch", "integration")
    branch_ok = repo_config_svc._git_branch_exists(repo_dir, agent_branch)
    checks["integration_branch"] = branch_ok
    if not branch_ok:
        missing.append(f"agent branch '{agent_branch}' does not exist")

    gi = repo_dir / ".gitignore"
    gi_ok = False
    try:
        text = gi.read_text(encoding="utf-8") if gi.exists() else ""
        gi_ok = ("graphify-out" in text) and ("_brownfield" in text)
    except Exception:  # noqa: BLE001
        gi_ok = False
    checks["gitignore_hygiene"] = gi_ok
    if not gi_ok:
        missing.append("harness .gitignore rules (graphify-out / _brownfield) absent")

    return {"ok": all(checks.values()), "checks": checks, "missing": missing}


async def _onboarding_flow(
    repo_dir: Path,
    repo_name: str,
    run_id: str,
    *,
    brief: str | None = None,
    timeout: int = 3600,
) -> AsyncIterator[dict]:
    """Spawn the Onboarder (Janitor in onboarding mode) to fulfil a new repo's
    environment prerequisites. Yields the agent stream, then an independent
    postcondition verification, then a terminal ``_orchestrator_outcome`` with
    ``{role:"onboarder", status, agent_status, verify, verdict}``.

    The final ``status`` is ``onboarded`` only when BOTH the agent reported
    ``onboarded`` AND the orchestrator's own structural verification passes —
    catching an over-claimed verdict (no-overclaim doctrine in code)."""
    cfg = repo_config_svc.load(repo_dir)
    onb_dir = repo_dir / "_brownfield" / "_onboarding"
    report_rel = f"_brownfield/_onboarding/ONBOARDING_REPORT-{run_id}.md"
    report_json_rel = f"_brownfield/_onboarding/ONBOARDING-{run_id}.json"
    try:
        onb_dir.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass

    yield _evt("onboarding.start", run_id=run_id, repo=repo_name, report=report_rel)

    trace = None
    verdict: dict = {}
    try:
        skill = prompts_brownfield_svc._load_skill("onboarder")
        task = _build_onboarding_task(
            skill, run_id=run_id, repo_name=repo_name,
            main_ref=getattr(cfg, "main_ref", "main"),
            report_rel=report_rel, report_json_rel=report_json_rel, brief=brief)
        trace = TraceWriter(repo=repo_name, role="onboarder", bl_id=run_id, task_id=run_id)
        async for event in stream_agent_task(
            task, repo_dir, timeout_seconds=timeout, idle_timeout=900,
            allowed_tools="Bash,Read,Write,Edit", trace=trace,
        ):
            event.setdefault("orchestrator_step", "onboarding")
            yield event
    except Exception as exc:  # noqa: BLE001 — onboarding failure escalates, never crashes the caller
        yield _evt("onboarding.error", run_id=run_id, error=str(exc)[:500])
    finally:
        if trace is not None:
            try:
                trace.close()
            except Exception:  # noqa: BLE001
                pass

    report_json_abs = repo_dir / report_json_rel
    if report_json_abs.exists():
        try:
            verdict = json.loads(report_json_abs.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            yield _evt("onboarding.verdict.error", run_id=run_id,
                       error=str(exc)[:300], path=report_json_rel)
            verdict = {}

    agent_status = verdict.get("status") if isinstance(verdict, dict) else None

    # Independent verification — the trust gate (don't believe a self-report).
    verify = _verify_onboarding_postconditions(repo_dir)
    yield _evt("onboarding.verify", run_id=run_id, ok=verify["ok"],
               checks=verify["checks"], missing=verify["missing"])

    onboarded = (agent_status == "onboarded") and verify["ok"]
    status = "onboarded" if onboarded else "escalated"
    yield _evt("onboarding.done" if onboarded else "onboarding.escalated",
               run_id=run_id, status=status, agent_status=agent_status,
               verify_ok=verify["ok"], missing=verify["missing"],
               gaps=(verdict.get("gaps") if isinstance(verdict, dict) else None),
               report=report_rel)
    yield {"_orchestrator_outcome": True, "role": "onboarder", "run_id": run_id,
           "status": status, "agent_status": agent_status, "verify": verify,
           "verdict": verdict}


async def run_onboarding(
    repo_dir: Path, repo_name: str, run_id: str, *,
    brief: str | None = None, timeout: int = 3600,
) -> AsyncIterator[dict]:
    """Public entry point used by the ``/onboard`` endpoint and the
    ``scripts/onboard_target.py`` launcher. Streams the onboarding events; the
    terminal ``_orchestrator_outcome`` carries the final status."""
    async for e in _onboarding_flow(repo_dir, repo_name, run_id,
                                    brief=brief, timeout=timeout):
        yield e


# ─── acceptance flow (ABL-0014 — Batch B: agent spawn + R10.1 retry) ──────


# No-abort persistence doctrine (operator, 2026-06-06 — BINDING): an agent that
# detects an issue must investigate → fix → re-test and keep working until it is
# resolved. The per-role doctrine/gate fix loops are therefore deep, not the old
# shallow cap of 2. This ceiling is a SAFETY backstop (bounds infinite spend on a
# genuinely-stuck BL), NOT a routine give-up point: on exhaustion the run does not
# silently `abort`, it `escalates` to the operator with a full dossier (Option A).
# The expected exit of every loop is RESOLUTION (green), not the ceiling.
MAX_FIX_ATTEMPTS = 6

ACCEPTANCE_MAX_RETRIES = 2  # R10.1 — matches per-role doctrine retry budget
# PROPOSAL_LIVE_ACCEPTANCE_LOOP: max boot→exercise→fix→re-boot rounds before the
# convergence loop escalates with a dossier. Generous backstop (no-abort doctrine),
# not a routine give-up — the loop also exits early when a round makes no progress.
ACCEPTANCE_LOOP_MAX_ROUNDS = 5


def _acceptance_loop_next(round_done: dict | None, accept_round: int,
                          max_rounds: int) -> str:
    """Decide the live-acceptance convergence-loop action after one round.

    Returns one of:
    - "accept"   — integrity_ok: every criterion live-verified, zero open failures.
    - "reround"  — not clean but ≥1 fix was dispatched this round AND rounds remain →
                   re-boot + re-exercise to confirm the fix live.
    - "escalate" — not clean and either nothing actionable was dispatched (a senior
                   engineer would also be blocked) or rounds are exhausted. No-abort:
                   surfaces a dossier, never a silent clean / routine give-up.
    """
    if round_done and round_done.get("integrity_ok"):
        return "accept"
    dispatched = int((round_done or {}).get("dispatched_count", 0) or 0)
    if dispatched > 0 and accept_round < max_rounds:
        return "reround"
    return "escalate"


def _accept_worktree_task_id(run_id: str, accept_round: int) -> str:
    """Round-unique detached-worktree task id for the live-acceptance loop.

    Round 1 keeps the historical ``accept-<run_id>`` name; rounds >=2 append
    ``-r<round>`` so a rerounds ``git worktree add -b`` does not collide with the
    prior rounds still-existing ``agent/accept-<run_id>`` branch (the worktree_failed
    acceptance-reround escalation in run-20260614T143621Z-0b7c91).
    """
    base = f"accept-{run_id}"
    return base if accept_round <= 1 else f"{base}-r{accept_round}"


async def _gate_stack_present(run_id: str) -> bool:
    """§E.1 Q7 pre-flight: is a regression-gate docker stack still up for
    this run? Returns True if any container named ``gate-<run_id>*`` exists.

    Used by ``_acceptance_flow`` to skip-with-warning rather than fight a
    port collision mid-playwright. A non-empty result is itself a latent
    I-3 closure_check violation — callers should surface it as
    ``acceptance.skipped reason=gate_stack_still_up``.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "ps", "--filter", f"name=gate-{run_id}",
            "--format", "{{.Names}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
    except (FileNotFoundError, asyncio.TimeoutError, OSError):
        # Docker not installed / hung — treat as "not present" rather than
        # blocking. The acceptance agent itself will fail loudly if docker
        # is genuinely broken.
        return False
    return bool(out and out.decode("utf-8", "replace").strip())


async def _compute_backend_bls(
    repo_dir: Path,
    target_ref: str,
    agent_branch: str,
    api_route_globs: list[str],
) -> tuple[list[str], dict[str, list[str]]]:
    """ABL-0014 Item 1 Batch B: identify merged BLs that touched backend
    route files.

    Walks the commits on ``agent_branch`` since divergence from
    ``target_ref`` and, for each commit whose subject begins with a
    ``BL-NNNN`` prefix, checks whether its diff touches any path matching
    one of ``api_route_globs``. Returns ``(backend_bls, evidence)``:

    - ``backend_bls`` is the deduped, sort-stable BL ID list (e.g.
      ``["BL-0006", "BL-0007"]``).
    - ``evidence`` is ``{bl_id: [touched_path, ...]}`` capped at 5 paths
      per BL, used by the acceptance prompt to show the agent WHY each BL
      is on the list.

    Best-effort: returns ``([], {})`` on any git failure. The validator
    treats an empty list as "skip API-acceptance validation," matching
    the pure-frontend-sprint contract.

    Coverage rule matches the validator: a BL whose only backend touch is
    a test file (``backend/tests/...``) does NOT need an api_journey — the
    intent is to exercise SHIPPED behavior, not re-run QA tests through
    a different harness.
    """
    import fnmatch
    import re
    bl_re = re.compile(r"^(BL-\d{4})\b", re.MULTILINE)

    # 1. Range of commits on agent_branch since divergence from target_ref.
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "log", "--reverse", "--format=%H%x09%s",
            f"{target_ref}..{agent_branch}",
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, _err = await asyncio.wait_for(proc.communicate(), timeout=30)
    except (FileNotFoundError, asyncio.TimeoutError, OSError):
        return [], {}
    if proc.returncode != 0 or not out:
        return [], {}

    # 2. For each commit, extract BL-NNNN from subject, then diff its files.
    bls_order: list[str] = []
    seen: set[str] = set()
    evidence: dict[str, list[str]] = {}

    for line in out.decode("utf-8", "replace").splitlines():
        if "\t" not in line:
            continue
        sha, subj = line.split("\t", 1)
        m = bl_re.search(subj)
        if not m:
            continue
        bl_id = m.group(1)

        try:
            diff_proc = await asyncio.create_subprocess_exec(
                "git", "show", "--no-renames", "--name-only", "--format=",
                sha,
                cwd=str(repo_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            diff_out, _ = await asyncio.wait_for(diff_proc.communicate(), timeout=20)
        except (FileNotFoundError, asyncio.TimeoutError, OSError):
            continue
        if diff_proc.returncode != 0:
            continue

        touched_routes: list[str] = []
        for path in diff_out.decode("utf-8", "replace").splitlines():
            path = path.strip()
            if not path:
                continue
            # Skip test files — exercising shipped behavior is the intent.
            if "/tests/" in path or path.startswith("tests/"):
                continue
            for glob in api_route_globs:
                if fnmatch.fnmatch(path.lower(), glob.lower()):
                    touched_routes.append(path)
                    break
        if not touched_routes:
            continue

        if bl_id not in seen:
            seen.add(bl_id)
            bls_order.append(bl_id)
            evidence[bl_id] = []
        # Cap evidence to 5 paths per BL — keeps the prompt readable.
        for p in touched_routes:
            if p not in evidence[bl_id] and len(evidence[bl_id]) < 5:
                evidence[bl_id].append(p)

    return bls_order, evidence


async def _compute_ui_coverage(
    repo_dir: Path,
    target_ref: str,
    agent_branch: str,
    ui_globs: list[str],
    merged_bl_ids: list[str],
) -> dict:
    """ABL-0014 Item 2 (Batch C, 2026-06-01): UI-coverage breakdown.

    For each merged BL, scan commits on ``agent_branch`` whose subject
    starts with ``BL-NNNN`` and check whether the diff touches any path
    matching ``ui_globs`` (tests excluded). A BL is "UI-covered" if any
    of its commits touched at least one UI file.

    Returns::

        {
          "merged_total": int,         # = len(merged_bl_ids)
          "ui_bls":       [str, ...],  # sorted by first-merge order
          "backend_only": [str, ...],  # merged_bl_ids - ui_bls
          "ratio":        float,       # ui_bls / merged_total (0.0–1.0)
          "evidence":     {bl: [paths]},
        }

    Best-effort: returns zero-ratio with the supplied ids on any git
    failure. The caller decides what to do with the ratio (Item 2's
    operator-tunable ``min_ui_coverage_ratio`` threshold drives the
    partial-vs-full subtype).
    """
    import fnmatch
    import re

    if not merged_bl_ids:
        return {
            "merged_total": 0, "ui_bls": [], "backend_only": [],
            "ratio": 0.0, "evidence": {},
        }
    bl_re = re.compile(r"^(BL-\d{4})\b", re.MULTILINE)
    merged_set = set(merged_bl_ids)

    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "log", "--reverse", "--format=%H%x09%s",
            f"{target_ref}..{agent_branch}",
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, _err = await asyncio.wait_for(proc.communicate(), timeout=30)
    except (FileNotFoundError, asyncio.TimeoutError, OSError):
        return {
            "merged_total": len(merged_bl_ids),
            "ui_bls": [], "backend_only": list(merged_bl_ids),
            "ratio": 0.0, "evidence": {},
        }
    if proc.returncode != 0:
        return {
            "merged_total": len(merged_bl_ids),
            "ui_bls": [], "backend_only": list(merged_bl_ids),
            "ratio": 0.0, "evidence": {},
        }

    ui_bls_order: list[str] = []
    seen_ui: set[str] = set()
    evidence: dict[str, list[str]] = {}

    for line in out.decode("utf-8", "replace").splitlines():
        if "\t" not in line:
            continue
        sha, subj = line.split("\t", 1)
        m = bl_re.search(subj)
        if not m:
            continue
        bl_id = m.group(1)
        if bl_id not in merged_set:
            continue  # commit references a BL that didn't reach merged_*

        try:
            diff_proc = await asyncio.create_subprocess_exec(
                "git", "show", "--no-renames", "--name-only", "--format=",
                sha,
                cwd=str(repo_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            diff_out, _ = await asyncio.wait_for(diff_proc.communicate(), timeout=20)
        except (FileNotFoundError, asyncio.TimeoutError, OSError):
            continue
        if diff_proc.returncode != 0:
            continue

        touched_ui: list[str] = []
        for path in diff_out.decode("utf-8", "replace").splitlines():
            path = path.strip()
            if not path:
                continue
            if "/tests/" in path or path.startswith("tests/"):
                continue
            for glob in ui_globs:
                if fnmatch.fnmatch(path.lower(), glob.lower()):
                    touched_ui.append(path)
                    break
        if not touched_ui:
            continue
        if bl_id not in seen_ui:
            seen_ui.add(bl_id)
            ui_bls_order.append(bl_id)
            evidence[bl_id] = []
        for p in touched_ui:
            if p not in evidence[bl_id] and len(evidence[bl_id]) < 5:
                evidence[bl_id].append(p)

    backend_only = [bl for bl in merged_bl_ids if bl not in seen_ui]
    merged_total = len(merged_bl_ids)
    ratio = (len(ui_bls_order) / merged_total) if merged_total else 0.0
    return {
        "merged_total": merged_total,
        "ui_bls": ui_bls_order,
        "backend_only": backend_only,
        "ratio": ratio,
        "evidence": evidence,
    }


def _build_priors_block(repo_dir: Path, feature_slug: str) -> str:
    """ABL-0014 §I.3 Batch E — classifier accuracy priors injection.

    Read the per-feature findings ledger and summarize operator
    verdicts as a falsification prior. Only classifications with at
    least one non-pending verdict appear in the block; an empty or
    all-pending ledger yields the empty string (silent — agent gets
    no extra noise).

    Per spec (§I.3): a high refuted count for a classification means
    the agent over-classified in past runs; the prompt should raise
    its falsification bar before reporting that classification again.
    """
    try:
        ledger = findings_ledger_svc.FindingsLedger(repo_dir, feature_slug)
        rows: list[tuple[str, dict]] = []
        for cls in (
            "product_bug", "test_bug", "data_bug", "infra_bug", "uncertain",
        ):
            priors = ledger.get_priors_for_classification(cls)
            verdicted = (
                priors.get("confirmed", 0)
                + priors.get("refuted", 0)
                + priors.get("deferred", 0)
            )
            if verdicted > 0:
                rows.append((cls, priors))
    except Exception:
        # Best-effort: never break the agent spawn over a ledger read.
        return ""
    if not rows:
        return ""
    lines = [
        "",
        "---",
        "",
        "# Prior verdict history for this feature",
        "",
        (
            "Operator has triaged findings in this feature's acceptance "
            "ledger. By classification (confirmed · refuted · deferred):"
        ),
        "",
    ]
    for cls, p in rows:
        lines.append(
            f"- **{cls}**: {p.get('confirmed', 0)} · "
            f"{p.get('refuted', 0)} · {p.get('deferred', 0)}"
        )
    lines.extend([
        "",
        (
            "A high `refuted` count means you have over-classified that "
            "type in prior runs. Raise your falsification bar before "
            "reporting that classification — cite specific evidence that "
            "distinguishes the current failure from the historical "
            "refuted patterns. Treat these as priors, not bans: a real "
            "bug is still a real bug."
        ),
        "",
    ])
    return "\n".join(lines)


def _alloc_free_port() -> int:
    """Reserve an ephemeral free TCP port (PROPOSAL_NATIVE_BOOT_ACCEPTANCE, locked
    decision: free-port injection kills the stale-build port-collision class)."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _resolve_app_boot_port(app_boot: dict, port: int, fe_port: int | None = None) -> dict:
    """Return a copy of the app_boot contract with ``${PORT}`` (backend) and
    ``${FE_PORT}`` (frontend) substituted in cmd / ready_url / pre_cmd / env, and
    the chosen ports recorded under ``_port`` / ``frontend._port``.

    app_boot v2 (PROPOSAL_LIVE_ACCEPTANCE_LOOP): when an ``app_boot.frontend``
    sub-block is present, it is resolved too so acceptance can boot the real UI
    alongside the backend and Playwright-drive it.
    """
    def _sub(s: str) -> str:
        s = s.replace("${PORT}", str(port))
        if fe_port is not None:
            s = s.replace("${FE_PORT}", str(fe_port))
        return s
    out = dict(app_boot)
    out["cmd"] = [_sub(x) for x in app_boot.get("cmd", [])]
    if app_boot.get("ready_url"):
        out["ready_url"] = _sub(app_boot["ready_url"])
    if app_boot.get("pre_cmd"):
        out["pre_cmd"] = [[_sub(tok) for tok in step] for step in app_boot["pre_cmd"]]
    if isinstance(app_boot.get("env"), dict):
        out["env"] = {k: _sub(v) for k, v in app_boot["env"].items()}
    out["_port"] = port
    fe = app_boot.get("frontend")
    if isinstance(fe, dict) and fe.get("cmd"):
        fe_out = dict(fe)
        fe_out["cmd"] = [_sub(x) for x in fe.get("cmd", [])]
        if fe.get("ready_url"):
            fe_out["ready_url"] = _sub(fe["ready_url"])
        if fe.get("pre_cmd"):
            fe_out["pre_cmd"] = [[_sub(tok) for tok in step] for step in fe["pre_cmd"]]
        if isinstance(fe.get("env"), dict):
            fe_out["env"] = {k: _sub(v) for k, v in fe["env"].items()}
        if fe_port is not None:
            fe_out["_port"] = fe_port
        out["frontend"] = fe_out
    return out


def _materialize_app_boot(app_boot: dict, wt_path: Path) -> list[dict]:
    """Copy app_boot.materialize templates into the acceptance worktree.

    SECURITY (locked decision A, PROPOSAL_NATIVE_BOOT_ACCEPTANCE §7): each
    ``from`` MUST be a committed ``*.example.*`` template and resolve inside the
    worktree; ``to`` MUST resolve inside the worktree. The source is committed so
    it is already present in the worktree — this is a single-tree copy that fills
    in the gitignored runtime config the agent otherwise can't get. Returns
    per-entry results for telemetry; never raises (advisory).
    """
    import shutil as _sh
    results: list[dict] = []
    wt_root = wt_path.resolve()
    for m in app_boot.get("materialize", []):
        frm, to = m.get("from", ""), m.get("to", "")
        res = {"from": frm, "to": to, "ok": False, "reason": ""}
        try:
            if ".example." not in Path(frm).name:
                res["reason"] = "rejected: source is not a *.example.* template"
                results.append(res)
                continue
            src = (wt_path / frm).resolve()
            dst = (wt_path / to).resolve()
            if not str(src).startswith(str(wt_root) + "/"):
                res["reason"] = "rejected: source escapes worktree"
                results.append(res)
                continue
            if not str(dst).startswith(str(wt_root) + "/"):
                res["reason"] = "rejected: dest escapes worktree"
                results.append(res)
                continue
            if not src.is_file():
                res["reason"] = f"source template not found: {frm}"
                results.append(res)
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            _sh.copyfile(src, dst)
            res["ok"] = True
            res["reason"] = "materialized"
        except Exception as exc:  # noqa: BLE001 — advisory: never abort
            res["reason"] = f"error: {type(exc).__name__}: {exc}"
        results.append(res)
    return results


def _free_app_boot_ports(app_boot: dict | None) -> list[int]:
    """Harness-owned: kill any process listening on the app_boot backend/frontend
    ports BEFORE (re)booting in an acceptance round, and reap them after.

    Root cause this guards (PROPOSAL_LIVE_ACCEPTANCE_LOOP, 2026-06-13): the boot
    is agent-driven and backgrounded on a FIXED port (the frontend hardcodes the
    backend URL). A prior round's/run's app process can linger on that port, so a
    later round polls the STALE binary, tests pre-fix code, and the convergence
    loop escalates on an already-fixed defect (the F1 audience false-negative).
    Freeing the ports each round forces the agent's fresh boot to bind its own
    freshly-built process. Best-effort; never raises. Returns the ports freed."""
    if not isinstance(app_boot, dict):
        return []
    import subprocess
    ports: list[int] = []
    if isinstance(app_boot.get("_port"), int):
        ports.append(app_boot["_port"])
    fe = app_boot.get("frontend")
    if isinstance(fe, dict) and isinstance(fe.get("_port"), int):
        ports.append(fe["_port"])
    for port in ports:
        try:
            subprocess.run(
                ["bash", "-c",
                 f"fuser -k {port}/tcp 2>/dev/null; "
                 f"lsof -ti tcp:{port} 2>/dev/null | xargs -r kill -9 2>/dev/null; "
                 f"true"],
                capture_output=True, timeout=20)
        except Exception:  # noqa: BLE001 — best-effort, never block the sprint
            pass
    return ports


def _build_acceptance_task(
    skill: str,
    *,
    run_id: str,
    feature_slug: str,
    brief_rel: str,
    backlog_rel: str,
    acceptance_rel: str,
    compose_project: str,
    attempt: int,
    prior_missing: list[str] | None = None,
    backend_bls: list[str] | None = None,
    backend_bl_evidence: dict[str, list[str]] | None = None,
    repo_dir: Path | None = None,
    inject_acceptance_priors: bool = False,
    app_boot: dict | None = None,
) -> str:
    """Construct the per-attempt task prompt for the acceptance agent.

    On attempt > 1 (R10.1 retry), include the validator's missing-artifact
    list as a focused fix prompt — mirrors ``doctrine_validator.build_fix_prompt``.
    """
    retry_block = ""
    if attempt > 1 and prior_missing:
        items = "\n".join(f"- MISSING: `{p}`" for p in prior_missing)
        retry_block = (
            f"\n\n---\n\n# Retry context (attempt {attempt} of "
            f"{1 + ACCEPTANCE_MAX_RETRIES})\n\n"
            f"Your previous run did not satisfy the validator. Fix these "
            f"specifically, in the SAME worktree:\n\n{items}\n"
        )

    # ABL-0014 Item 1 Batch B: backend BL coverage block.
    api_block = ""
    if backend_bls:
        lines = [
            "",
            "---",
            "",
            "# API Acceptance — REQUIRED for this sprint",
            "",
            (
                f"This sprint merged {len(backend_bls)} BL(s) that touched "
                "backend route files. Per the **API Acceptance** section of "
                "your SKILLS.md, every one of these BLs MUST be covered by "
                "≥1 entry in `api_journeys.yaml` with a matching "
                "`backend_bl:` field. The validator will fail the run "
                "(triggering R10.1 retry) if any of these BLs has no "
                "covering api_journey."
            ),
            "",
            "Backend BLs to cover (and the route files that earned each its slot):",
            "",
        ]
        for bl in backend_bls:
            paths = (backend_bl_evidence or {}).get(bl) or []
            cited = ", ".join(f"`{p}`" for p in paths) or "(no file evidence available)"
            lines.append(f"- **{bl}** — touched: {cited}")
        lines.extend([
            "",
            (
                "For each backend BL, write at least one api_journey that "
                "exercises its routes as a portal-authenticated seeded "
                "client; classify any failure with the same taxonomy as "
                "UI journeys (`product_bug | test_bug | data_bug | "
                "infra_bug | uncertain`); log each request/response to "
                "`fixtures/api_logs/<journey_id>.jsonl`; and add the "
                "outcome to `report.json` under an `api_journeys: [...]` "
                "array."
            ),
            "",
        ])
        api_block = "\n".join(lines)
    elif backend_bls is not None:
        # Caller explicitly computed zero — pure-frontend sprint. Tell
        # the agent to emit the empty marker for honesty.
        api_block = (
            "\n\n---\n\n# API Acceptance — not required this sprint\n\n"
            "No merged BLs touched backend route files. Emit "
            "`api_journeys.yaml` with `api_journeys: []` to make the empty "
            "intent explicit; no API requests are required.\n"
        )

    # ABL-0014 §I.3 Batch E: classifier priors block (default OFF until
    # 3-smoke calibration per §I.1). Silent when ledger is empty.
    priors_block = ""
    if inject_acceptance_priors and repo_dir is not None:
        priors_block = _build_priors_block(repo_dir, feature_slug)

    # PROPOSAL_NATIVE_BOOT_ACCEPTANCE: native-boot contract when the target has
    # no compose stack. The harness has already reserved the port + materialized
    # the gitignored config; the AGENT drives the boot against this explicit
    # contract (decision: agent-driven), with a Level-3 feature-route check.
    if app_boot:
        port = app_boot.get("_port")
        env = app_boot.get("env") or {}
        env_str = " ".join(f"{k}={v}" for k, v in env.items())
        cmd_str = " ".join(app_boot.get("cmd", []))
        ready_url = app_boot.get("ready_url") or "(no ready_url configured — pick one)"
        ready_to = app_boot.get("ready_timeout_s", 150)
        pre_lines = ""
        if app_boot.get("pre_cmd"):
            steps = "\n".join("    " + " ".join(s) for s in app_boot["pre_cmd"])
            pre_lines = (
                f"  First run these setup step(s) (e.g. DB migrations) from the "
                f"worktree root:\n{steps}\n"
            )
        fixed_note = ""
        if isinstance(app_boot, dict) and app_boot.get("port"):
            fixed_note = (
                f"  This target pins the backend to port {port} (the frontend "
                f"hardcodes it). If {port} is already in use by a stale process, "
                f"free it first (e.g. `fuser -k {port}/tcp` or kill the listener) "
                f"before booting.\n"
            )
        boot_block = (
            f"- BOOT THE APP NATIVELY — this target has NO docker-compose stack. "
            f"The harness has reserved **port {port}** and materialized the "
            f"gitignored runtime config into your worktree. Drive the boot "
            f"yourself from the worktree root:\n"
            f"{fixed_note}"
            f"{pre_lines}"
            f"  Then start the app (background it) and wait for it to serve:\n"
            f"    {env_str + ' ' if env_str else ''}{cmd_str}\n"
            f"  Poll `{ready_url}` until it returns 2xx (up to {ready_to}s).\n"
            f"- LEVEL-3 READINESS (REQUIRED before any journey): confirm the app "
            f"serves THIS sprint's feature — request at least one NEW-feature "
            f"route and verify it is NOT 404. A stale baseline build can answer "
            f"200 on old routes while 404ing the new ones; if that happens you "
            f"booted the wrong build/port — fix it before proceeding. Drive all "
            f"API journeys over HTTP against `http://localhost:{port}`.\n"
        )
        # app_boot v2 (PROPOSAL_LIVE_ACCEPTANCE_LOOP): full-app boot — also boot
        # the real frontend and Playwright-drive EVERY UI acceptance criterion
        # against it (the customer-acceptance standard). The harness reserved the
        # FE port + materialized any frontend config; the agent drives the boot.
        fe = app_boot.get("frontend") if isinstance(app_boot, dict) else None
        if isinstance(fe, dict) and fe.get("cmd"):
            fe_port = fe.get("_port")
            fe_dir = fe.get("dir", ".")
            fe_cmd = " ".join(fe.get("cmd", []))
            fe_env = fe.get("env") or {}
            fe_env_str = " ".join(f"{k}={v}" for k, v in fe_env.items())
            fe_ready = fe.get("ready_url") or f"http://localhost:{fe_port}/"
            fe_ready_to = fe.get("ready_timeout_s", 180)
            fe_pre = ""
            if fe.get("pre_cmd"):
                steps = "\n".join("      " + " ".join(s) for s in fe["pre_cmd"])
                fe_pre = (
                    f"  First run the frontend setup step(s) from `{fe_dir}/`:\n{steps}\n"
                )
            boot_block += (
                f"- BOOT THE REAL FRONTEND TOO (full-app acceptance — MANDATORY). The "
                f"harness reserved **frontend port {fe_port}**. From `{fe_dir}/`:\n"
                f"{fe_pre}"
                f"  Start the UI (background it):\n"
                f"    {fe_env_str + ' ' if fe_env_str else ''}{fe_cmd}\n"
                f"  Poll `{fe_ready}` until it serves (up to {fe_ready_to}s). The UI "
                f"talks to the backend you booted on port {port}.\n"
                f"- EXERCISE EVERY UI ACCEPTANCE CRITERION through this running UI with "
                f"**Playwright** at `http://localhost:{fe_port}` — navigate the real "
                f"pages, click the real controls, fill the real forms, like the paying "
                f"customer who just received the app. This is NOT optional and is NOT "
                f"replaced by an API call or a build check.\n"
                f"- VERIFY PERSISTENCE where a criterion changes state: after a save, "
                f"**reload the page (or re-fetch) and assert the data persisted**; after "
                f"an edit, confirm it stuck; after a delete, confirm it's gone; for a "
                f"reject-path criterion, confirm the live UI actually rejects it. A "
                f"toast/optimistic update alone is NOT acceptance — re-read the state.\n"
                f"- EVIDENCE PER CRITERION: every `AC-<BL>-<n>` MUST map to one journey "
                f"that ran against the live app and produced a screenshot (UI) or a "
                f"recorded request/response (API) under your output dir, plus the "
                f"persistence re-check. Record it in `report.json` `ac_coverage: "
                f"[{{ac_id, status, journey, evidence}}]` — `evidence` MUST cite a real "
                f"artifact path that exists. A criterion with no real evidence is "
                f"treated as UNVERIFIED (the run cannot read clean).\n"
            )
    else:
        boot_block = (
            f"- When you boot any docker compose stack for the seed/run, "
            f"export `COMPOSE_PROJECT_NAME={compose_project}` so "
            f"`closure_check` can enumerate any leaks tied to this run.\n"
        )

    return (
        f"{skill}\n\n"
        f"---\n\n"
        f"# Run context\n\n"
        f"- run_id: `{run_id}`\n"
        f"- feature_slug: `{feature_slug}`\n"
        f"- brief: `{brief_rel}`\n"
        f"- backlog: `{backlog_rel}`\n"
        f"- output dir (write everything here, nothing elsewhere): "
        f"`{acceptance_rel}`\n"
        f"- attempt: {attempt} of {1 + ACCEPTANCE_MAX_RETRIES}\n\n"
        f"# Hard requirements (§E.1 of ABL-0014 plan)\n\n"
        f"- MAXIMUM 8 journeys. If more candidates exist, pick the cross-"
        f"actor ones and list the rest as `journeys_deferred` in the "
        f"report. The validator rejects > 8.\n"
        f"- MAXIMUM 15 steps per journey. The validator rejects > 15.\n"
        f"{boot_block}"
        f"- One honest pass: do NOT retry failed journeys yourself. "
        f"Classify each failure into one of "
        f"`product_bug | test_bug | data_bug | infra_bug | uncertain` "
        f"and move on.\n"
        f"- The pre-existing test suite (`frontend/tests/*.spec.ts`, "
        f"`backend/tests/`) is READ-ONLY. Your tests live under "
        f"`{acceptance_rel}/tests/_acceptance/` and nowhere else.\n\n"
        f"Follow the Required Completion Steps in your SKILLS.md, "
        f"emitting a final JSON summary with `journeys_planned`, "
        f"`journeys_passed`, `journeys_failed`, `journeys_unshippable`, "
        f"`api_journeys_planned`, `api_journeys_passed`, "
        f"`api_journeys_failed`, "
        f"`report_path`, `screenshots_dir`.{retry_block}{api_block}{priors_block}\n"
    )


def _archive_acceptance_dir(acceptance_dir: Path, run_id: str) -> Path | None:
    """Copy the agent's `acceptance/` tree into
    `webapp/backend/traces_archive/<run_id>/acceptance/` so the operator can
    review reports + screenshots after the worktree is reaped. Returns the
    archive path, or None on any failure (best-effort)."""
    if not acceptance_dir.exists():
        return None
    archive_root = (
        prompts_brownfield_svc.AGENTIC_ROOT
        / "webapp" / "backend" / "traces_archive" / run_id
    )
    dest = archive_root / "acceptance"
    try:
        archive_root.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(acceptance_dir, dest)
        return dest
    except (OSError, shutil.Error):
        return None


def _persist_acceptance_in_target(
    acceptance_dir_wt: Path,
    feature_dir: Path,
    repo_dir: Path,
    run_id: str,
    feature_slug: str | None,
) -> dict:
    """Persist the acceptance evidence PERMANENTLY in-target under
    ``_brownfield/features/<slug>/acceptance/`` and commit it on the agent_branch
    (operator directive 2026-06-13). Journeys, screenshots, api-logs, and the
    report then travel WITH the feature on the integration branch — not only in
    the harness-side ``traces_archive`` (which is reaped/ephemeral relative to the
    target).

    Orchestrator-owned: the acceptance agent itself never commits (R13). Copies
    the worktree's acceptance tree into the real checkout (merging — so the
    findings ledger already written there is preserved), then ``git add`` +
    ``git commit`` scoped to the acceptance pathspec only (leaves any other
    working-tree state untouched). Best-effort: returns a result dict and never
    raises — a persist failure must not abort the sprint."""
    import subprocess
    dst = feature_dir / "acceptance"
    res = {"ok": False, "committed": False, "path": str(dst), "reason": ""}
    try:
        if not acceptance_dir_wt.exists():
            res["reason"] = "no acceptance dir in worktree"
            return res
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copytree(acceptance_dir_wt, dst, dirs_exist_ok=True)
        res["ok"] = True
        try:
            rel = str(dst.relative_to(repo_dir))
        except ValueError:
            rel = str(dst)
        subprocess.run(["git", "-C", str(repo_dir), "add", "--", rel],
                       check=False, capture_output=True)
        staged = subprocess.run(
            ["git", "-C", str(repo_dir), "diff", "--cached", "--quiet", "--", rel],
            capture_output=True)
        if staged.returncode != 0:  # non-zero ⇒ there ARE staged changes
            msg = f"acceptance({feature_slug or 'feature'}): persist results (run {run_id})"
            cm = subprocess.run(
                ["git", "-C", str(repo_dir), "commit", "-m", msg, "--", rel],
                capture_output=True, text=True)
            res["committed"] = cm.returncode == 0
            res["reason"] = "committed" if cm.returncode == 0 else f"commit failed: {cm.stderr[-200:]}"
        else:
            res["reason"] = "no staged changes (already persisted / all gitignored)"
        return res
    except Exception as exc:  # noqa: BLE001 — best-effort, never abort the sprint
        res["reason"] = f"error: {type(exc).__name__}: {exc}"
        return res


# ─── ABL-0015 auto-dispatch follow-up engineer ─────────────────────────────
# §9 Decision 2: v1 dispatches at most one follow-up per sprint. Bump (or
# make operator-configurable) only after calibration. The framework's
# highest-risk action stays small until proven.
# Chain (operator directive 2026-06-12): EVERY detected product failure must be
# dispatched — a cap of 1 would silently defer the rest, which is a defect escape.
# Raised to a generous bound that covers any realistic sprint's failure count while
# remaining a runaway backstop. Overflow beyond the cap is surfaced loudly
# (acceptance.followup.skipped reason=cost_cap) and caught by the terminal integrity
# gate, never silently dropped.
FOLLOWUP_COST_CAP = 25

# A60: confidence-gated auto-confirm. The acceptance agent is a full copy of the
# architect — when it root-causes a product_bug, falsifies the competing
# (data/test/infra) hypotheses, and localizes the fix at high confidence, that
# verified root cause IS the trust signal. The crew must then RESOLVE it, not
# leave it flagged for a human gate-keeper. The dispatched fix still clears the
# same doctrine + gate + merge bar as any BL, so a wrong fix can't merge — the
# gate is the safety net, not manual confirmation. An operator can still veto by
# POSTing verdict="rejected" (only verdict is None auto-confirms).
FOLLOWUP_AUTOCONFIRM_CONFIDENCE = 0.90


def _finding_dispatch_eligible(finding) -> bool:
    """A60: is this finding eligible for follow-up dispatch?

    Eligible iff it is an un-dispatched ``product_bug`` that is EITHER
    operator-confirmed OR self-confirmed by a high-confidence, alternatives-
    falsified agent root cause (``verdict is None`` and
    ``confidence >= FOLLOWUP_AUTOCONFIRM_CONFIDENCE``). A finding the operator
    explicitly rejected (``verdict`` set to anything else) is never dispatched.
    R15 idempotency: any non-null ``dispatch_state`` excludes it.
    """
    if finding.classification != "product_bug" or finding.dispatch_state is not None:
        return False
    if finding.verdict == "confirmed":
        return True
    return (finding.verdict is None
            and finding.confidence is not None
            and finding.confidence >= FOLLOWUP_AUTOCONFIRM_CONFIDENCE)


def _select_followup_candidates(findings, *, cost_cap=FOLLOWUP_COST_CAP):
    """Pure selector for auto-dispatch. Returns (to_dispatch, capped).

    Eligibility (A60): an un-dispatched ``product_bug`` that is operator-CONFIRMED
    or self-confirmed by high agent confidence (see ``_finding_dispatch_eligible``).
    R15 idempotency: a finding with any non-null ``dispatch_state`` is excluded,
    so a re-run never re-spawns on a finding already dispatched/merged.
    """
    eligible = [f for f in findings if _finding_dispatch_eligible(f)]
    to_dispatch = eligible[:cost_cap]
    capped = len(eligible) - len(to_dispatch)
    return to_dispatch, capped


def _followup_hypothesis(finding) -> str:
    """Best-effort: pull the classifier's file-location hypothesis for this
    finding's journey from its source report.json. The hypothesis is not
    persisted on the ledger (only the summary is, for stable hashing), so
    we re-read it here to hand the engineer a starting site. Returns "" on
    any error — the engineer grounds its own retrieval regardless."""
    try:
        report = json.loads(Path(finding.report_path).read_text(encoding="utf-8"))
    except Exception:
        return ""
    for key in ("ui_journeys", "api_journeys", "journeys"):
        for j in report.get(key, []) or []:
            if not isinstance(j, dict):
                continue
            if str(j.get("id") or j.get("journey_id") or "") != finding.journey_id:
                continue
            caveat = j.get("caveat") if isinstance(j.get("caveat"), dict) else {}
            failure = j.get("failure") if isinstance(j.get("failure"), dict) else {}
            for src in (j, caveat, failure):
                h = src.get("hypothesis")
                if isinstance(h, str) and h.strip():
                    return h.strip()
    return ""


def _build_followup_section(finding, *, hypothesis: str = "") -> str:
    """Build the bl_section for a follow-up engineer (fed to build_engineer
    in place of a BACKLOG entry). Compensates for the absent PO per-BL
    context by making the finding the authoritative scope."""
    hyp_block = (
        f"\n### Classifier hypothesis (likely site — verify before trusting)\n{hypothesis}\n"
        if hypothesis else
        "\n### Classifier hypothesis\n(none recorded — ground the site yourself via retrieval)\n"
    )
    # A61 (Lever A): surface the acceptance agent's VERIFIED root-cause dossier —
    # not just the thin status summary — and make it the authoritative scope. The
    # root_cause / fix_locus / source_refs name EVERY surface the defect touches
    # (e.g. both the streak badge AND the "Best Streaks" echart). Mandating a
    # deterministic regression test for EACH named surface turns the engineer's
    # own no-abort gate loop into the re-verify-and-iterate mechanism: the fix
    # cannot merge until every named surface is green. This closes the
    # "fixed one surface, missed the other" gap deterministically, without
    # relying on a (non-deterministic) acceptance re-run to re-discover it.
    def _block(title: str, val) -> str:
        return f"\n### {title}\n{val}\n" if val else ""
    dossier_block = (
        _block("Verified root cause (causal chain)", getattr(finding, "root_cause", None))
        + _block("Fix locus (surfaces/files to repair — fix EVERY one)", getattr(finding, "fix_locus", None))
        + _block("Source references", ", ".join(finding.source_refs) if getattr(finding, "source_refs", None) else None)
        + _block("Alternatives already falsified (do not re-chase these)", getattr(finding, "alternatives_falsified", None))
    )
    return f"""## Remediation task — auto-dispatched from acceptance ({finding.finding_id})

This is a FOLLOW-UP fix for a cross-BL integration defect the acceptance
agent found on journey {finding.journey_id} ({finding.journey_kind}). It
was NOT decomposed by the PO, so the usual
`_brownfield/<bl_id>/codebase_context.md` will be ABSENT — treat the
defect dossier below as your authoritative scope, and ground each named
site with your own retrieval before editing.

### Defect summary
{finding.evidence_summary}
{dossier_block}{hyp_block}
### Source of record
Acceptance report: {finding.report_path}

### Your job (BINDING — full-locus resolution)
Resolve the defect COMPLETELY. The fix locus above may name MORE THAN ONE
surface (e.g. several call sites, an API path AND a UI render path). You must:
1. Fix EVERY surface named in the root cause / fix locus — not just the most
   obvious one. A partial fix that leaves a named sibling surface broken is a
   FAILURE, not a resolution.
2. For EACH distinct surface you fix, add a deterministic regression test (in
   the feature's own test file, NOT in the application's pre-existing test
   files) that fails on the OLD behavior and passes on your fix. These tests
   are how the gate proves the WHOLE defect is closed — the same regression
   gate that guards every BL guards this one, and it will not go green (so this
   will not merge) until every surface's test passes. Keep iterating
   investigate→fix→re-test until all are green; do not stop at the first.
3. Keep the change additive and regression-safe. Write your `eng_patterns.md`
   artifact as required.
"""


def _should_self_confirm(finding, merged: bool) -> bool:
    """A62: should a just-merged follow-up fix self-record verdict=confirmed?

    Closes the self-resolution -> lessons seam. A finding reaches dispatch only
    if it is operator-CONFIRMED (``verdict == "confirmed"``) or self-confirmed by
    the A60 high-confidence path (``verdict is None`` + confidence >= 0.90). When
    the dispatched fix MERGES through the full doctrine+gate+merge bar, a
    still-unverdicted finding has earned a durable ``confirmed`` verdict so the
    ABL-0016 lessons read-path (filter: {confirmed, deferred}) surfaces it on
    future features — the crew remembers what it autonomously fixed.

    The merge bar is the trust gate: a fix that cleared every BL guard is a
    strictly stronger signal than the classification confidence dispatch already
    trusts. We never touch a finding whose verdict the operator already set
    (the ``verdict is None`` guard) — operator adjudication always wins. The
    write is advisory (feeds an advisory store); it is NOT a new R-rule (I-2
    unaffected)."""
    return bool(merged) and finding.verdict is None


async def _dispatch_one_followup(
    repo_dir: Path,
    repo_name: str,
    run_id: str,
    feature_slug: str,
    finding,
    idx: int,
    retrieval_kwargs_builder,
    ledger,
    *,
    timeout: int,
) -> AsyncIterator[dict]:
    """Dispatch a single follow-up engineer for one confirmed finding.

    The shared per-finding body used by BOTH the inline sprint loop
    (``_dispatch_followup_engineers``) and the operator's on-demand
    "Dispatch fix" endpoint (ABL-0021). R15-stamps ``dispatched`` BEFORE the
    spawn, runs the unchanged ``_engineer_flow`` (section_override only),
    captures the verified terminal events, stamps the terminal state, and
    emits ``acceptance.followup.{start,done}``."""
    bl_id = f"BL-ACCEPT-{run_id}-{idx}"
    # R15: stamp dispatched BEFORE the spawn — the idempotency anchor.
    await asyncio.to_thread(
        ledger.set_dispatch_state, finding.finding_id, "dispatched",
        bl_id=bl_id, run_id=run_id,
    )
    yield _evt("acceptance.followup.start", run_id=run_id,
               finding_id=finding.finding_id, bl_id=bl_id,
               classification=finding.classification, verdict=finding.verdict)
    section = _build_followup_section(
        finding, hypothesis=_followup_hypothesis(finding),
    )
    merged = False
    merged_sha = None
    eng_outcome = None
    async for ev in _engineer_flow(
        repo_dir, repo_name, bl_id, timeout, retrieval_kwargs_builder,
        run_id=run_id, feature_slug=feature_slug, section_override=section,
        task_id=f"followup-{run_id}-{idx}",
    ):
        if ev.get("phase") == "merge_to_target":
            merged_sha = ev.get("merged_sha")
        if ev.get("_orchestrator_outcome"):
            merged = bool(ev.get("merged"))
            eng_outcome = ev
        yield ev

    # A66: the follow-up engineer is a FULL engineer — it must self-resolve a
    # repairable merge failure (e.g. a dirty target checkout) via the Janitor +
    # remerge, EXACTLY as the per-BL engineer path does (A58/A59). That chain
    # lived only in run_brief's per-BL loop; the follow-up runs `_engineer_flow`
    # directly through here, so it bypassed the Janitor entirely and a correct,
    # green-tested fix was silently abandoned as `not_merged`
    # (run-20260609T133620Z-fb16cc: badge-clipping fix passed its gate but
    # merge_to_target failed on a dirty tree, no Janitor fired). Mirror the
    # per-BL block: on a merge_error, repair the environment and re-attempt.
    if not merged and eng_outcome is not None:
        _dossier = eng_outcome.get("dossier") or {}
        if _engineer_janitor_trigger(_dossier, True) and _dossier.get("blocker") == "merge_error":
            _cfg = repo_config_svc.load(repo_dir)
            try:
                async for je in _run_janitor(
                    repo_dir, repo_name, run_id, feature_slug,
                    failed_step="acceptance_followup.merge_error",
                    blocker_reason=str(_dossier.get("merge_error") or "merge_to_target failed"),
                    failing_role="engineer", bl_id=bl_id, timeout=timeout,
                ):
                    yield je
                _dossier["janitor"] = getattr(_run_janitor, "last_outcome", None) or {}
            except Exception as exc:  # noqa: BLE001 — Janitor is advisory; never block
                yield _evt("janitor.error", bl_id=bl_id, run_id=run_id, error=str(exc)[:300])
            if _should_remerge_after_janitor(_dossier):
                remerge = await fast_forward_target(
                    repo_dir, _dossier["merge_branch"], target_ref=_cfg.agent_branch)
                yield _evt("merge_retry_post_janitor", bl_id=bl_id,
                           role="acceptance_followup",
                           ok=remerge.get("ok"), merged_sha=remerge.get("merged_sha"),
                           kind=remerge.get("kind"), error=remerge.get("error"),
                           branch=_dossier.get("merge_branch"))
                if remerge.get("ok"):
                    merged = True
                    merged_sha = remerge.get("merged_sha") or merged_sha
                    yield _evt("janitor.resolved", bl_id=bl_id,
                               role="acceptance_followup",
                               reason=(f"Janitor repaired the environment and the "
                                       f"follow-up merge landed "
                                       f"({(remerge.get('merged_sha') or '')[:8]}); "
                                       f"{bl_id} fully resolved in-loop — no escalation"))
    state = "merged" if merged else "not_merged"
    await asyncio.to_thread(
        ledger.set_dispatch_state, finding.finding_id, state,
        merged_sha=merged_sha,
    )
    # A62: cumulative-loop closure. A self-confirmed finding whose fix merged
    # through the full doctrine+gate+merge bar becomes a durable advisory
    # lesson — record verdict=confirmed so ABL-0016's read-path surfaces it on
    # future features (closing the self-resolution -> lessons seam). The note
    # marks provenance as crew-self-confirmed (NOT operator-triaged) so it stays
    # honest + operator-auditable; operator-set verdicts are never overwritten.
    # Advisory telemetry: a failure here must NEVER perturb the sprint (mirrors
    # lessons.record_injection / the priors guards).
    if _should_self_confirm(finding, merged):
        try:
            updated = await asyncio.to_thread(
                ledger.set_verdict, finding.finding_id, "confirmed",
                f"self-confirmed by crew: dispatched fix merged through the full "
                f"doctrine+gate bar ({(merged_sha or '')[:8]}); not operator-triaged. "
                f"[A62 auto-resolution cumulative-loop closure]",
            )
            yield _evt("acceptance.followup.self_confirmed", run_id=run_id,
                       finding_id=finding.finding_id, bl_id=bl_id,
                       merged_sha=merged_sha)
            # ABL-0016 Stage 1.5 write-through: index the just-confirmed lesson
            # into the per-target vector store so search_lessons can match it by
            # problem statement on future features. Best-effort, off-thread
            # (embeds via Ollama); a failure NEVER perturbs the sprint.
            try:
                indexed = await asyncio.to_thread(
                    lessons_index_svc.upsert_lesson, repo_dir,
                    lessons_svc.Lesson.from_finding(updated),
                )
                if indexed:
                    yield _evt("acceptance.followup.lesson_indexed", run_id=run_id,
                               finding_id=finding.finding_id, bl_id=bl_id)
            except Exception:
                pass  # advisory telemetry only
        except Exception as exc:
            yield _evt("acceptance.followup.self_confirm_error", run_id=run_id,
                       finding_id=finding.finding_id, error=str(exc))
    yield _evt("acceptance.followup.done", run_id=run_id,
               finding_id=finding.finding_id, bl_id=bl_id,
               outcome=state, merged_sha=merged_sha)


async def _dispatch_followup_engineers(
    repo_dir: Path,
    repo_name: str,
    run_id: str,
    feature_slug: str,
    retrieval_kwargs_builder,
    *,
    timeout: int,
) -> AsyncIterator[dict]:
    """ABL-0015 Batch C: select confirmed product_bug findings and spawn a
    follow-up engineer per candidate (capped). Reuses ``_engineer_flow``
    unchanged except for the section override — all gate/merge/teardown is
    the same machinery that guards every BL. Emits
    ``acceptance.followup.{skipped,start,done}``."""
    ledger = findings_ledger_svc.FindingsLedger(repo_dir, feature_slug)
    to_dispatch, capped = _select_followup_candidates(ledger.list_all())
    if not to_dispatch:
        yield _evt("acceptance.followup.skipped", run_id=run_id,
                   feature_slug=feature_slug, reason="no_confirmed_candidates")
        return
    for idx, finding in enumerate(to_dispatch):
        async for ev in _dispatch_one_followup(
            repo_dir, repo_name, run_id, feature_slug, finding, idx,
            retrieval_kwargs_builder, ledger, timeout=timeout,
        ):
            yield ev
    if capped:
        yield _evt("acceptance.followup.skipped", run_id=run_id,
                   feature_slug=feature_slug, reason="cost_cap",
                   cost_cap=FOLLOWUP_COST_CAP, deferred=capped)


def select_followup_finding(repo_dir: Path, feature_slug: str, finding_id: str):
    """ABL-0021: resolve + eligibility-check a single finding for on-demand
    dispatch. Returns (finding, ledger, reason). ``reason`` is None when
    eligible, else one of: unknown | not_product_bug | not_confirmed |
    already_dispatched. Pure read; the router maps reason -> HTTP status."""
    ledger = findings_ledger_svc.FindingsLedger(repo_dir, feature_slug)
    finding = next((f for f in ledger.list_all() if f.finding_id == finding_id), None)
    if finding is None:
        return None, ledger, "unknown"
    if finding.classification != "product_bug":
        return finding, ledger, "not_product_bug"
    if finding.dispatch_state is not None:
        return finding, ledger, "already_dispatched"   # R15
    # A60: eligible if operator-confirmed OR self-confirmed by high agent
    # confidence (a copy of the architect root-caused it). "not_confirmed" now
    # means "neither operator-confirmed nor confident enough to auto-confirm".
    if not _finding_dispatch_eligible(finding):
        return finding, ledger, "not_confirmed"
    return finding, ledger, None


def _summarize_acceptance_journeys(report: dict) -> tuple[dict, list[dict]]:
    """Extract a journey pass/fail summary + a list of anomaly records (one per
    failed/unshippable journey) from an acceptance report.json. Defensive: tolerates
    missing keys and either count fields or per-journey arrays. Feeds the explicit
    `acceptance.anomaly` surfacing (operator 2026-06-11): a failed journey must never
    hide under a clean summary."""
    if not isinstance(report, dict):
        return {}, [{"kind": "report_shape", "detail": "report.json was not an object"}]
    summary = {k: report[k] for k in (
        "journeys_planned", "journeys_passed", "journeys_failed", "journeys_unshippable",
        "api_journeys_planned", "api_journeys_passed", "api_journeys_failed",
        "api_journeys_unshippable") if isinstance(report.get(k), int)}
    # Prefer rich per-journey anomalies from any journey array; fall back to the
    # numeric count fields only if no array is present (so we never double-count).
    per_journey: list[dict] = []
    seen: set = set()
    for arr_key in ("journeys", "api_journeys", "ui_journeys"):
        arr = report.get(arr_key)
        if not isinstance(arr, list):
            continue
        for j in arr:
            if not isinstance(j, dict):
                continue
            status = str(j.get("status", "")).lower()
            if status in ("failed", "fail", "unshippable", "error"):
                jid = str(j.get("id") or j.get("name") or "?")
                if (arr_key, jid) in seen:
                    continue
                seen.add((arr_key, jid))
                per_journey.append({
                    "kind": "journey_" + status, "journey": jid,
                    "title": str(j.get("title") or j.get("name") or "")[:120],
                    "evidence": str(j.get("evidence_summary") or j.get("reason") or "")[:200],
                })
    if per_journey:
        return summary, per_journey
    anomalies = [
        {"kind": k, "count": report[k], "detail": f"{report[k]} {k.replace('_', ' ')}"}
        for k in ("journeys_failed", "api_journeys_failed",
                  "journeys_unshippable", "api_journeys_unshippable")
        if isinstance(report.get(k), int) and report[k] > 0]
    return summary, anomalies


def _evidence_exists(evidence_base: Path | None, evidence: object) -> bool:
    """R20 evidence-enforcement (PROPOSAL_LIVE_ACCEPTANCE_LOOP): an ac_coverage
    entry is only credited as verified if it cites a real artifact that EXISTS on
    disk (a screenshot, a recorded request/response log, a playwright spec/result),
    not just a self-reported status. ``evidence`` may be a string path or a list of
    paths; each is resolved relative to the acceptance output dir (and tried under a
    couple of conventional subdirs). Returns True if at least one cited path exists
    as a file. If we cannot resolve a base dir, fall back to truthiness (degraded
    but never crashes)."""
    paths: list[str] = []
    if isinstance(evidence, str) and evidence.strip():
        paths = [evidence.strip()]
    elif isinstance(evidence, list):
        paths = [str(x).strip() for x in evidence if isinstance(x, (str,)) and str(x).strip()]
    if not paths:
        return False
    if evidence_base is None:
        return True  # degraded: no base to resolve against — accept non-empty citation
    base = evidence_base
    for p in paths:
        cand = Path(p)
        tries = [cand] if cand.is_absolute() else [
            base / p, base / "screenshots" / p, base / "fixtures" / p,
            base / "tests" / "_acceptance" / p,
        ]
        for t in tries:
            try:
                if t.is_file():
                    return True
            except OSError:
                continue
    return False


def _unverified_criteria(
    repo_dir: Path,
    feature_slug: str | None,
    report: dict,
    evidence_base: Path | None = None,
) -> list[str]:
    """R20 — every PO acceptance criterion (AC-<BL>-<n>) MUST be verified by a live
    acceptance journey **backed by real evidence on disk**. Returns the AC ids the
    report does NOT credit as verified (missing, failed, or with no real evidence
    artifact in its ``ac_coverage`` entry). Empty list ⇒ every criterion was
    live-verified with evidence. Defensive: any parse problem yields [] (the
    journey/finding paths still surface failures), so this never crashes the flow."""
    try:
        bf = backlog_svc.find_backlog(repo_dir, feature_slug=feature_slug)
        if bf is None:
            return []
        items = backlog_svc.parse(bf.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return []
    all_ids = [c.id for crits in backlog_svc.all_criteria(items).values() for c in crits]
    if not all_ids:
        return []
    verified: set = set()
    cov = report.get("ac_coverage") if isinstance(report, dict) else None
    if isinstance(cov, list):
        for e in cov:
            if not isinstance(e, dict):
                continue
            acid = str(e.get("ac_id") or e.get("id") or "")
            status = str(e.get("status") or "").lower()
            if not (acid and status in ("verified", "pass", "passed", "ok", "covered")):
                continue
            # R20 evidence-enforcement: status alone is not enough — require a real
            # cited artifact that exists, so a criterion can't be self-reported
            # verified without having actually been exercised against the live app.
            if _evidence_exists(evidence_base, e.get("evidence") or e.get("evidence_path")
                                or e.get("screenshot") or e.get("artifact")):
                verified.add(acid)
    return [a for a in all_ids if a not in verified]


async def _acceptance_flow(
    repo_dir: Path,
    repo_name: str,
    run_id: str,
    feature_slug: str | None,
    timeout: int = 3600,
    backend_bls_override: list[str] | None = None,
    inject_acceptance_priors: bool = False,
    retrieval_kwargs_builder=None,  # ABL-0015 Batch B: needed to spawn followup engineer
    run_acceptance_followup: bool = False,  # ABL-0015: auto-dispatch; OFF until calibrated
    accept_round: int = 1,  # live-acceptance convergence round (>=2 on reround); makes the
                            # detached worktree branch round-unique so a reround does not
                            # collide with the prior round's still-existing branch (acceptance
                            # reround worktree_failed bug, run-20260614T143621Z-0b7c91).
    trace=None,  # A13-followup (A64): caller-supplied TraceWriter so the acceptance
                 # flow seals its enforcement phase events (regression_checkpoint +
                 # lifecycle) into the SAME co-located phase_events.jsonl the
                 # ABL-0017 efficacy aggregator reads. None → create our own (the
                 # standalone /run-acceptance path).
) -> AsyncIterator[dict]:
    """ABL-0014 Acceptance Agent.

    Runs once per sprint, AFTER ``sprint_complete`` and BEFORE
    ``doctrine_meta`` / ``closure_check`` (per §E.1 Q3, advisory only —
    never sets terminal_status=aborted from here).

    **Batch B scope:** detached worktree off ``agent_branch``, agent spawn
    via ``stream_agent_task``, R10.1 retry on validator-incomplete,
    archive copy to ``traces_archive/<run_id>/acceptance/``, cleanup in
    ``finally``.

    Events:
      - ``acceptance.skipped`` — ``no_feature_slug | no_brief |
        gate_stack_still_up``
      - ``acceptance.start`` — opens the flow; includes worktree path
      - per-attempt agent stream events (pass-through, tagged
        ``orchestrator_step=acceptance``)
      - ``acceptance.validator.{ok,incomplete,give_up}`` — R10.1 result
      - ``acceptance.archived`` — archive copy destination
      - ``acceptance.done`` — terminal
    """
    if not feature_slug:
        yield _evt("acceptance.skipped", reason="no_feature_slug", run_id=run_id)
        return

    feature_dir = repo_dir / "_brownfield" / "features" / feature_slug
    brief_path = feature_dir / "brief.md"
    if not brief_path.exists():
        yield _evt(
            "acceptance.skipped",
            reason="no_brief",
            run_id=run_id,
            brief_path=str(brief_path),
        )
        return

    if await _gate_stack_present(run_id):
        yield _evt(
            "acceptance.skipped",
            reason="gate_stack_still_up",
            run_id=run_id,
        )
        return

    # Resolve the merged agent_branch we fork the read-only worktree off of.
    cfg = repo_config_svc.load(repo_dir)
    agent_branch = cfg.agent_branch
    # A48 follow-up (2026-06-02): lowercase to satisfy docker compose's
    # project-name validator + the volume_reaper's matching regex. ISO-8601
    # run_ids carry uppercase T/Z which fail
    # `_PROJECT_NAME_RE = ^[a-z0-9][a-z0-9_-]*$` and cause the reaper to
    # no-op every acceptance run (verified on 2026-06-01 client_portal
    # smoke). Mirrors the lowercase fix already in regression_gate.py:50-71.
    compose_project = f"acceptance-{run_id}".lower()
    feature_rel = f"_brownfield/features/{feature_slug}"
    brief_rel = f"{feature_rel}/brief.md"
    backlog_rel = f"{feature_rel}/BACKLOG.md"
    acceptance_rel = f"{feature_rel}/acceptance"

    # Create the detached worktree (§E.1 Q1).
    try:
        wt = await create_worktree(
            repo_dir,
            task_id=_accept_worktree_task_id(run_id, accept_round),
            base_ref=agent_branch,
        )
    except RuntimeError as exc:
        yield _evt(
            "acceptance.skipped",
            reason="worktree_failed",
            run_id=run_id,
            error=str(exc),
        )
        return

    # ABL-0014 Item 1 Batch B: compute the backend BL list for coverage.
    # Caller may override (e.g. /run-acceptance re-runs with a fixed list);
    # otherwise we scan the merged agent_branch for BL commits that touched
    # paths matching the target's api_route_globs.
    backend_bls: list[str] = []
    backend_bl_evidence: dict[str, list[str]] = {}
    if backend_bls_override is not None:
        backend_bls = list(backend_bls_override)
    else:
        backend_bls, backend_bl_evidence = await _compute_backend_bls(
            repo_dir,
            target_ref=cfg.main_ref,
            agent_branch=agent_branch,
            api_route_globs=cfg.effective_api_route_globs(),
        )

    # A13-followup (A64): resolve the trace BEFORE the first phase event so the
    # acceptance flow's enforcement/lifecycle events seal into a co-located
    # phase_events.jsonl. The caller (sprint runner) supplies one shared with the
    # regression_checkpoint seal; standalone /run-acceptance creates its own.
    if trace is None:
        trace = TraceWriter(repo=repo_name, role="acceptance", task_id=run_id)

    def _seal(evt: dict) -> dict:
        """Seal an orchestrator-built acceptance phase event into the trace's
        phase_events.jsonl, then return it for yielding. Defensive: sealing is
        observability, never a sprint blocker (write_phase_event is itself
        try/excepted)."""
        try:
            trace.write_phase_event(evt)
        except Exception:  # noqa: BLE001
            pass
        return evt

    yield _seal(_evt(
        "acceptance.start",
        run_id=run_id,
        feature_slug=feature_slug,
        brief_path=str(brief_path),
        acceptance_dir=str(feature_dir / "acceptance"),
        worktree=str(wt.path),
        agent_branch=agent_branch,
        compose_project=compose_project,
        timeout=timeout,
        backend_bls=backend_bls,
        backend_bls_source=(
            "override" if backend_bls_override is not None else "computed"
        ),
    ))

    skill = prompts_brownfield_svc._load_skill("acceptance")
    acceptance_dir_wt = wt.path / acceptance_rel  # validator reads the worktree copy
    validation: dict = {"ok": False, "missing": [], "empty": [], "summary": "no attempts"}
    last_attempt = 0

    # PROPOSAL_NATIVE_BOOT_ACCEPTANCE: prepare the native-boot contract when the
    # target configures `app_boot` (no compose stack). Harness-owned steps only:
    # reserve a free port (kills the stale-build port-collision class) + materialize
    # the gitignored runtime config from committed *.example.* templates (locked
    # decision A). The agent then drives the boot against this explicit contract.
    resolved_app_boot = None
    _app_boot_cfg = getattr(cfg, "app_boot", None)  # getattr: tolerate test-double cfgs (A67 pattern)
    if _app_boot_cfg:
        # app_boot v2: honor a FIXED backend port when the contract pins one
        # (frontend hardcodes the API URL); else allocate a free port.
        _fixed_port = _app_boot_cfg.get("port")
        _port = _fixed_port if isinstance(_fixed_port, int) and _fixed_port > 0 else _alloc_free_port()
        # app_boot v2: reserve a SECOND free port for the real frontend when a
        # frontend sub-block is configured (full-app boot for live UI acceptance).
        _has_fe = isinstance(_app_boot_cfg.get("frontend"), dict) and \
            _app_boot_cfg["frontend"].get("cmd")
        # Honor a FIXED frontend port when pinned (e.g. :5173 to satisfy the
        # backend's CORS allowlist); else a free port.
        _fe_fixed = (_app_boot_cfg.get("frontend") or {}).get("port") if _has_fe else None
        if _has_fe:
            _fe_port = _fe_fixed if isinstance(_fe_fixed, int) and _fe_fixed > 0 else _alloc_free_port()
            if _fe_port == _port:  # keep them distinct
                _fe_port = _alloc_free_port()
        else:
            _fe_port = None
        resolved_app_boot = _resolve_app_boot_port(_app_boot_cfg, _port, _fe_port)
        # Free the boot ports up-front so the agent's boot binds a fresh,
        # freshly-built process (not a stale listener from a prior round/run).
        _freed = _free_app_boot_ports(resolved_app_boot)
        if _freed:
            yield _evt("acceptance.app_boot.ports_freed", run_id=run_id, ports=_freed)
        mat_results = _materialize_app_boot(resolved_app_boot, wt.path)
        yield _seal(_evt(
            "acceptance.app_boot.prepared",
            run_id=run_id,
            port=_port,
            frontend_port=_fe_port,
            full_app=bool(_has_fe),
            cmd=resolved_app_boot.get("cmd"),
            ready_url=resolved_app_boot.get("ready_url"),
            frontend_cmd=(resolved_app_boot.get("frontend") or {}).get("cmd") if _has_fe else None,
            frontend_ready_url=(resolved_app_boot.get("frontend") or {}).get("ready_url") if _has_fe else None,
            materialized=[m for m in mat_results if m["ok"]],
            rejected=[m for m in mat_results if not m["ok"]],
        ))

    try:
        for attempt in range(1, ACCEPTANCE_MAX_RETRIES + 2):  # 1, 2, 3 = 1 + 2 retries
            last_attempt = attempt
            # Free the boot ports before every attempt's spawn too — the prior
            # attempt may have left a backgrounded app process bound to them.
            if attempt > 1:
                _free_app_boot_ports(resolved_app_boot)
            prior_missing = (
                validation.get("missing", []) if attempt > 1 else None
            )
            task = _build_acceptance_task(
                skill,
                run_id=run_id,
                feature_slug=feature_slug,
                brief_rel=brief_rel,
                backlog_rel=backlog_rel,
                acceptance_rel=acceptance_rel,
                compose_project=compose_project,
                attempt=attempt,
                prior_missing=prior_missing,
                backend_bls=backend_bls,
                backend_bl_evidence=backend_bl_evidence,
                repo_dir=repo_dir,
                inject_acceptance_priors=inject_acceptance_priors,
                app_boot=resolved_app_boot,
            )
            yield _seal(_evt(
                "acceptance.attempt.start",
                run_id=run_id,
                attempt=attempt,
                max_attempts=1 + ACCEPTANCE_MAX_RETRIES,
            ))
            try:
                async for event in stream_agent_task(
                    task,
                    wt.path,
                    timeout_seconds=timeout,
                    idle_timeout=900,
                    allowed_tools="Bash,Read,Write,Edit",
                    trace=trace,
                ):
                    event.setdefault("orchestrator_step", "acceptance")
                    yield event
            except Exception as exc:  # noqa: BLE001 — advisory: never abort sprint
                yield _evt(
                    "acceptance.attempt.error",
                    run_id=run_id,
                    attempt=attempt,
                    error=str(exc),
                )

            validation = acceptance_validator_svc.validate_acceptance(
                acceptance_dir_wt,
                backend_bls=backend_bls or None,
            )
            if validation["ok"]:
                yield _evt(
                    "acceptance.validator.ok",
                    run_id=run_id,
                    attempt=attempt,
                    summary=validation["summary"],
                )
                break

            phase = (
                "acceptance.validator.give_up"
                if attempt >= 1 + ACCEPTANCE_MAX_RETRIES
                else "acceptance.validator.incomplete"
            )
            yield _evt(
                phase,
                run_id=run_id,
                attempt=attempt,
                missing=validation["missing"],
                empty=validation["empty"],
                summary=validation["summary"],
            )
            if phase == "acceptance.validator.give_up":
                break
    finally:
        trace.close()
        # Reap the app processes the agent backgrounded on the fixed boot ports,
        # so they can't linger and serve STALE code to a later round/run
        # (the F1 audience false-negative root cause). Best-effort.
        try:
            _reaped = _free_app_boot_ports(resolved_app_boot)
            if _reaped:
                yield _evt("acceptance.app_boot.ports_reaped", run_id=run_id, ports=_reaped)
        except Exception:  # noqa: BLE001
            pass
        # Archive whatever the agent produced (even on give_up, the report
        # is the most valuable evidence — keep it).
        archive_dest = _archive_acceptance_dir(acceptance_dir_wt, run_id)
        if archive_dest is not None:
            yield _evt(
                "acceptance.archived",
                run_id=run_id,
                archive=str(archive_dest),
            )
        # Operator directive 2026-06-13: the acceptance evidence (journeys,
        # screenshots, api-logs, report) must persist PERMANENTLY in-target under
        # _brownfield/features/<slug>/acceptance/ — travelling with the feature on
        # the agent_branch — not only harness-side. Orchestrator copies + commits
        # (the agent never commits). Best-effort; never aborts the sprint.
        try:
            persisted = _persist_acceptance_in_target(
                acceptance_dir_wt, feature_dir, repo_dir, run_id, feature_slug)
            yield _evt("acceptance.persisted_in_target", run_id=run_id,
                       feature_slug=feature_slug, **persisted)
        except Exception as exc:  # noqa: BLE001
            yield _evt("acceptance.persist_error", run_id=run_id, error=str(exc))
        # ABL-0014 §I.3 Batch B: persist acceptance findings to the
        # per-feature ledger. Prefer the archived copy (immutable,
        # survives worktree cleanup); fall back to the worktree copy
        # if archive failed but the worktree is still on disk. Never
        # raises — ledger failures are advisory and must not abort
        # the sprint, so a corrupt report.json yields an .error event
        # but the flow continues to `remove_worktree` and `done`.
        findings_persisted = 0
        # Operator directive 2026-06-11: an ANOMALOUS acceptance result (any failed /
        # unshippable journey, a missing/corrupt report, or a non-OK validator) must
        # ALWAYS be surfaced EXPLICITLY — never buried under a "clean" summary while a
        # journey silently failed (the review-submit 401 case). These trackers feed a
        # dedicated `acceptance.anomaly` event + an `anomalous` flag on `acceptance.done`.
        acceptance_anomalies: list[dict] = []
        journey_summary: dict = {}
        unverified_acs: list[str] = []
        report_src: Path | None = None
        if archive_dest is not None and (archive_dest / "report.json").exists():
            report_src = archive_dest / "report.json"
        elif (acceptance_dir_wt / "report.json").exists():
            report_src = acceptance_dir_wt / "report.json"
        if report_src is None:
            acceptance_anomalies.append({
                "kind": "report_missing",
                "detail": "no acceptance report.json was produced — the run could NOT "
                          "be verified end-to-end (treat as anomalous, not clean)"})
        if report_src is not None:
            try:
                report_dict = json.loads(report_src.read_text(encoding="utf-8"))
                journey_summary, _journey_anoms = _summarize_acceptance_journeys(report_dict)
                acceptance_anomalies.extend(_journey_anoms)
                # R20 — per-criterion live verification: any PO acceptance criterion
                # not verified by a live journey is an anomaly (→ non-clean), so a
                # criterion can never be silently skipped at the integration check.
                unverified_acs = _unverified_criteria(
                    repo_dir, feature_slug, report_dict,
                    evidence_base=report_src.parent)
                for _acid in unverified_acs:
                    acceptance_anomalies.append({
                        "kind": "criterion_unverified",
                        "ac_id": _acid,
                        "detail": f"acceptance criterion {_acid} was not verified by a "
                                  f"live journey (missing or failed in report.ac_coverage)"})
                ledger = findings_ledger_svc.FindingsLedger(repo_dir, feature_slug)
                persisted = await asyncio.to_thread(
                    ledger.append_from_report,
                    report_dict,
                    run_id=run_id,
                    report_path=str(report_src),
                )
                findings_persisted = len(persisted)
                yield _evt(
                    "acceptance.ledger.appended",
                    run_id=run_id,
                    feature_slug=feature_slug,
                    findings_persisted=findings_persisted,
                    ledger_path=str(ledger.path),
                )
            except Exception as exc:  # noqa: BLE001 — advisory: never abort sprint
                acceptance_anomalies.append({
                    "kind": "report_unparseable",
                    "detail": f"acceptance report.json could not be read/parsed "
                              f"({type(exc).__name__}: {exc}) — run NOT verified"})
                yield _evt(
                    "acceptance.ledger.error",
                    run_id=run_id,
                    feature_slug=feature_slug,
                    error=str(exc),
                    report_path=str(report_src),
                )
        # Reap the worktree (I-1). Branch is left in place per the convention
        # in remove_worktree; closure_check.scan_orphan_agent_branches is the
        # canonical reaper for those (currently deferred).
        try:
            await remove_worktree(repo_dir, wt, force=True)
        except Exception as exc:  # noqa: BLE001
            yield _evt(
                "acceptance.worktree_cleanup_error",
                run_id=run_id,
                error=str(exc),
            )
        # A48 fix #2 (2026-06-01): reap anonymous volumes from the
        # acceptance compose project. Acceptance stacks are heavier
        # than gate stacks (frontend + backend + db + mailcatcher +
        # playwright), so leftover volumes here are a real cost.
        try:
            reap = await volume_reaper_svc.reap(compose_project)
            yield _evt(
                "acceptance.volume_reaper",
                run_id=run_id,
                **reap.to_event(),
            )
        except Exception:
            pass

    # ABL-0015 Batch C + R17 (operator directive 2026-06-12): auto-dispatch the
    # no-abort fix loop on confirmed product_bug findings. Runs AFTER the finally
    # (acceptance worktree + volumes already reaped) and BEFORE acceptance.done — so
    # the follow-up worktree is created AND reaped (by _engineer_flow's own finally)
    # before run_brief's closure_check.scan_all fires. Requires the retrieval builder
    # (Batch B). Advisory: a dispatch failure must not abort the sprint.
    #
    # R17 — acceptance is the BINDING real-test owner. A failed real journey is the
    # strongest possible signal: the assembled product broke end-to-end. So dispatch
    # fires whenever there is an eligible observed-failure finding, INDEPENDENT of the
    # calibration-gated ``run_acceptance_followup`` flag — an observed real failure is
    # never left un-actioned (no-abort). All acceptance findings are, by construction,
    # observed failures (the ledger extracts a Finding only from a failed/caveat journey
    # that carries a classification). Every safety rail is preserved:
    # ``_select_followup_candidates`` still requires product_bug + confidence>=0.90
    # (or operator-confirmed) + cost_cap + R15 idempotency, and the dispatched fix must
    # itself clear the full doctrine+gate+merge bar (a broken fix never merges) — so the
    # zero-false-merge guarantee holds. ``run_acceptance_followup`` still force-enables
    # the path even when nothing is eligible yet (calibration-campaign smoke).
    eligible_now: list = []
    if feature_slug:
        try:
            eligible_now, _capped_now = _select_followup_candidates(
                findings_ledger_svc.FindingsLedger(repo_dir, feature_slug).list_all()
            )
        except Exception:  # noqa: BLE001 — selection is advisory; never abort
            eligible_now = []
    should_dispatch = bool(eligible_now) or run_acceptance_followup
    if should_dispatch and retrieval_kwargs_builder is not None and feature_slug:
        if eligible_now and not run_acceptance_followup:
            yield _evt(
                "acceptance.followup.auto_triggered",
                run_id=run_id,
                feature_slug=feature_slug,
                eligible=len(eligible_now),
                reason="R17: observed real-journey-failure product_bug finding(s) "
                       "auto-dispatched independent of the calibration flag",
            )
        try:
            async for evt in _dispatch_followup_engineers(
                repo_dir, repo_name, run_id, feature_slug,
                retrieval_kwargs_builder, timeout=timeout,
            ):
                yield evt
        except Exception as exc:  # noqa: BLE001 — advisory: never abort sprint
            yield _evt("acceptance.followup.error", run_id=run_id, error=str(exc))

    # A non-OK validator (the acceptance agent itself didn't converge) is anomalous.
    if not validation.get("ok"):
        acceptance_anomalies.append({
            "kind": "validator_not_ok",
            "detail": "the acceptance validator did not reach an OK verdict "
                      f"({validation.get('summary') or 'incomplete/give_up'})"})

    # Component 4 — terminal integrity gate (operator directive 2026-06-12: 0%
    # detected-defect escape). Re-read the ledger AFTER dispatch: any eligible
    # failure-finding still un-dispatched (cap overflow, no retrieval builder, or
    # not eligible) is an OPEN failure that was NOT addressed. Combined with any
    # unverified criterion, this is the binding "nothing escapes silently" check —
    # surfaced on every acceptance.done so the sprint's honest top-line reflects it.
    open_failures: list = []
    if feature_slug:
        try:
            open_failures, _ = _select_followup_candidates(
                findings_ledger_svc.FindingsLedger(repo_dir, feature_slug).list_all())
        except Exception:  # noqa: BLE001
            open_failures = []
    open_failure_ids = [getattr(f, "finding_id", "?") for f in open_failures]
    # Convergence-loop progress signal (PROPOSAL_LIVE_ACCEPTANCE_LOOP): how many
    # eligible failure-findings moved out of the eligible set this round (i.e. got
    # a follow-up engineer dispatched). >0 ⇒ the loop made progress and a re-boot+
    # re-exercise round is warranted to confirm the fix live; 0 with integrity not
    # ok ⇒ nothing actionable ⇒ the outer loop escalates rather than spin.
    dispatched_count = max(0, len(eligible_now) - len(open_failures))

    # Operator directive 2026-06-11: ALWAYS surface an anomalous acceptance EXPLICITLY,
    # loudly, as its own event — so a failed/unshippable journey (or a missing report)
    # can never hide under "8/8 merged, regression green". This is honest aggregation
    # (I-5): the top-line success of the per-BL gates does NOT imply acceptance passed.
    acceptance_clean = not acceptance_anomalies
    # integrity_ok is the conservative, no-overclaim verdict: the run is clean AND no
    # detected failure is left un-addressed (un-dispatched) AND every criterion was
    # live-verified. A dispatched-but-not-yet-re-verified fix keeps integrity_ok False
    # until a follow-up acceptance confirms it — we never declare integrity restored on
    # a fix we have not observed working.
    integrity_ok = acceptance_clean and not open_failures and not unverified_acs
    if not acceptance_clean or open_failures:
        yield _evt(
            "acceptance.anomaly",
            run_id=run_id,
            feature_slug=feature_slug,
            anomaly_count=len(acceptance_anomalies),
            anomalies=acceptance_anomalies[:30],
            unverified_criteria=unverified_acs[:50],
            open_failures=open_failure_ids[:50],
            journeys=journey_summary,
            integrity_ok=integrity_ok,
            reason="acceptance produced anomalous results (failed/unshippable journeys, "
                   "unverified acceptance criteria, an un-addressed failure, a missing/"
                   "corrupt report, or a non-OK validator) — escalated explicitly",
        )

    yield _seal(_evt(
        "acceptance.done",
        run_id=run_id,
        feature_slug=feature_slug,
        validator_ok=validation["ok"],
        attempts=last_attempt,
        acceptance_dir=str(feature_dir / "acceptance"),
        backend_bls=backend_bls,
        findings_persisted=findings_persisted,
        acceptance_clean=acceptance_clean,            # explicit clean/anomalous verdict
        integrity_ok=integrity_ok,                    # binding 0%-escape terminal verdict
        unverified_criteria=unverified_acs[:50],      # criteria not live-verified
        open_failures=open_failure_ids[:50],          # detected failures not yet dispatched
        dispatched_count=dispatched_count,            # fixes dispatched this round (loop progress)
        anomaly_count=len(acceptance_anomalies),
        anomalies=acceptance_anomalies[:30],
        journeys=journey_summary,
        batch="B",
    ))


# ─── doctrine-meta flow (B-3 / I-7 self-hardening) ─────────────────────────


async def _doctrine_meta_flow(
    repo_name: str,
    run_id: str,
    timeout: int,
) -> AsyncIterator[dict]:
    """Spawn the doctrine-meta-agent against the just-completed sprint's
    archived traces. The agent reads traces_archive/<run_id>/ and writes
    proposal files to .planning/doctrine_proposals/. It does NOT modify code.

    This flow:
      1. Locates the trace archive and the proposals dir.
      2. Snapshots existing proposal files (so we can detect new ones).
      3. Builds the prompt (doctrine SKILLS.md + run_id + paths + invariants
         doc reference).
      4. Streams the agent in the agentic-skills repo root (no MCP retrieval —
         the meta-agent reads files directly via Read/Bash, no graphify needed).
      5. Validates each new proposal file: must contain `## Evidence` and at
         least one `trace_path` reference. Rejected proposals get flagged but
         remain on disk for operator inspection.
      6. Emits orchestrator.doctrine_meta.proposals with counts + paths.

    Honors I-7: this flow NEVER changes doctrine itself; the agent NEVER
    auto-merges proposals. Operator approval is the only path to landed
    doctrine change.
    """
    agentic_root = prompts_brownfield_svc.AGENTIC_ROOT
    archive_dir = agentic_root / "webapp" / "backend" / "traces_archive" / run_id
    proposals_dir = agentic_root / ".planning" / "doctrine_proposals"

    if not archive_dir.exists():
        yield _evt("doctrine_meta.skipped", reason="no_archive", archive_dir=str(archive_dir))
        return

    trace_subdirs = sorted(p.name for p in archive_dir.iterdir() if p.is_dir())
    if not trace_subdirs:
        yield _evt("doctrine_meta.skipped", reason="empty_archive", archive_dir=str(archive_dir))
        return

    proposals_dir.mkdir(parents=True, exist_ok=True)
    pre_existing = {p.name for p in proposals_dir.glob("*.md") if p.name not in ("README.md",)}

    invariants_doc = agentic_root / "ARCHITECTURE_INVARIANTS.md"
    ledger_doc = agentic_root / "DESIGN_SHORTCOMINGS.md"

    # ABL-0017 Stage 2: compute the cross-run doctrine-efficacy report (this run
    # + recent archived runs) and hand it to the meta-agent so a `retire`
    # proposal is grounded in fire-rate evidence, not a single clean sprint.
    # Best-effort: a failure here must not block the meta analysis.
    efficacy_block = ""
    try:
        archive_parent = archive_dir.parent
        recent = sorted(
            (p.name for p in archive_parent.iterdir()
             if p.is_dir() and p.name.startswith("run-")
             and doctrine_efficacy_svc.load_run_state(p.name)),
            reverse=True,
        )[:10]
        if run_id not in recent:
            recent = [run_id] + recent
        report = doctrine_efficacy_svc.efficacy_report(recent)
        report_path = archive_dir / "doctrine_efficacy.json"
        try:
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        except OSError:
            pass
        yield _evt("doctrine_meta.efficacy", run_id=run_id,
                   run_count=report["run_count"],
                   never_fired=report["never_fired_review_candidates"],
                   unobserved=report["unobserved_rules"])
        efficacy_block = (
            f"\n## Doctrine-efficacy report (cross-run, ABL-0017)\n\n"
            f"A machine-readable report over {report['run_count']} archived run(s) "
            f"is at `{report_path}`. Confidence: {report['confidence']}\n"
            f"- **never_fired_review_candidates**: {report['never_fired_review_candidates']} "
            f"— enforced AND observed running across these runs yet NEVER caught a "
            f"violation. These are the ONLY rules eligible for a `retire` proposal — "
            f"and only if the report + traces show the rule's targeted failure class "
            f"also did not occur by other means. A guardrail that never trips may "
            f"simply mean a clean crew, so `retire` is the highest-risk direction: "
            f"propose it conservatively, grounded in this report, operator-gated.\n"
            f"- **unobserved_rules**: {report['unobserved_rules']} — their enforcement "
            f"phase never appeared in the analyzed traces. These are NOT assessable "
            f"(observability gap or no trigger arose); NEVER propose `retire` for them.\n"
        )
    except Exception as exc:  # noqa: BLE001
        yield _evt("doctrine_meta.efficacy_error", run_id=run_id, error=str(exc))

    doctrine = prompts_brownfield_svc._load_skill("doctrine_meta")
    task = (
        f"{doctrine}\n\n"
        f"---\n\n"
        f"# Run context\n\n"
        f"- run_id: `{run_id}`\n"
        f"- trace archive: `{archive_dir}` ({len(trace_subdirs)} trace dirs)\n"
        f"- canonical invariants: `{invariants_doc}`\n"
        f"- existing ledger: `{ledger_doc}`\n"
        f"- proposals output dir: `{proposals_dir}`\n"
        + efficacy_block
        + "\n"
        f"Trace dirs under the archive (each holds events.jsonl, retrieval.jsonl, meta.json):\n"
        + "\n".join(f"- {n}" for n in trace_subdirs)
        + "\n\n"
        f"Follow the Required Completion Steps in your SKILLS.md. "
        f"Write proposal files only under `{proposals_dir}` — never elsewhere. "
        f"Cite every claim with a trace path + line number that can be re-opened. "
        f"If you find nothing proposal-worthy, write zero files and emit a final JSON summary with `proposals_count: 0`.\n"
    )

    trace = TraceWriter(repo=repo_name, role="doctrine_meta", task_id=run_id)
    yield _evt("doctrine_meta.start", run_id=run_id, traces_count=len(trace_subdirs),
               trace_dir=str(trace.dir))
    try:
        async for event in stream_agent_task(
            task,
            agentic_root,
            timeout_seconds=timeout,
            idle_timeout=600,
            allowed_tools="Bash,Read,Write,Edit",
            trace=trace,
        ):
            event.setdefault("orchestrator_step", "doctrine_meta")
            yield event
    finally:
        trace.close()

    # Detect new proposal files + validate.
    after = {p.name for p in proposals_dir.glob("*.md") if p.name not in ("README.md",)}
    new_files = sorted(after - pre_existing)
    proposals: list[dict] = []
    for name in new_files:
        path = proposals_dir / name
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            continue
        has_evidence = "## Evidence" in body
        cites_trace = "traces_archive/" in body
        proposals.append({
            "filename": name,
            "path": str(path),
            "bytes": path.stat().st_size,
            "has_evidence_section": has_evidence,
            "cites_trace": cites_trace,
            "valid": has_evidence and cites_trace,
        })

    yield _evt(
        "doctrine_meta.proposals",
        run_id=run_id,
        proposals_count=len(proposals),
        valid_count=sum(1 for p in proposals if p["valid"]),
        proposals=proposals,
    )


# ─── main orchestrator ─────────────────────────────────────────────────────


def _dep_order(items: list) -> list:
    """Topological order over BL deps. Falls back to source order on cycles."""
    by_id = {it.id: it for it in items}
    order: list = []
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(bl_id: str):
        if bl_id in visited or bl_id not in by_id:
            return
        if bl_id in visiting:
            return  # cycle — skip
        visiting.add(bl_id)
        deps_raw = by_id[bl_id].meta.get("dependencies") or ""
        for dep in [d.strip() for d in str(deps_raw).replace(",", " ").split() if d.strip().startswith("BL-")]:
            visit(dep)
        visiting.discard(bl_id)
        visited.add(bl_id)
        order.append(by_id[bl_id])

    for it in items:
        visit(it.id)
    return order


def _dep_waves(items: list) -> list[list]:
    """Group BLs into topological execution **waves** (wave-execution Phase 2).

    ``wave[0]`` are BLs with no in-graph dependency; each later wave depends only
    on earlier ones. BLs WITHIN a wave are independent (per the R21 DAG) and are
    therefore safe to run concurrently — Phase 2 runs them at **concurrency=1**
    (the degenerate case, identical per-BL semantics to the sequential loop); a
    later phase raises the concurrency and moves the reindex to the wave barrier.

    Falls back to a single wave in dependency/source order if the graph has a
    cycle (the R21 PO gate already rejects cycles, so this is defense-in-depth).
    Reuses the same ``backlog.topological_waves`` primitive the validator uses, so
    the schedule the operator sees at the PO gate is exactly the one that runs.
    """
    try:
        id_waves = backlog_svc.topological_waves(items)
    except Exception:  # noqa: BLE001 — cycle / malformed: degrade to one wave
        return [_dep_order(items)]
    by_id = {it.id: it for it in items}
    return [[by_id[b] for b in wave if b in by_id] for wave in id_waves]


async def _merge_streams(factories, concurrency):
    """Fan-in N event-stream factories into one stream, <=`concurrency` at once.

    PROPOSAL_WAVE_CONCURRENCY.md step 2 - the intra-wave parallelism primitive.
    `factories`: zero-arg callables each returning an async iterator of events (one
    per BL in a wave). Yields `(idx, event)` as events arrive; `idx` is the factory
    position (-> bl_id) so the merged stream stays legible. A semaphore gates so at
    most `concurrency` factories drain simultaneously. Per-stream event order is
    preserved; cross-stream interleaving is timing-dependent and MUST NOT feed any
    control decision (read each stream's structured result after it ends -
    interleaving-independent determinism). No-abort: a factory that raises is
    isolated into one `{"_stream_error": ..., "_idx": idx}` event and never cancels
    its siblings.
    """
    q: asyncio.Queue = asyncio.Queue()
    sem = asyncio.Semaphore(max(1, concurrency))
    _SENTINEL = object()

    async def _drain(factory, idx):
        async with sem:
            try:
                async for ev in factory():
                    await q.put((idx, ev))
            except Exception as exc:  # noqa: BLE001 - isolate one BL's failure
                await q.put((idx, {"_stream_error": repr(exc), "_idx": idx}))
            finally:
                await q.put((idx, _SENTINEL))

    tasks = [asyncio.create_task(_drain(f, i)) for i, f in enumerate(factories)]
    live = len(tasks)
    try:
        while live:
            idx, ev = await q.get()
            if ev is _SENTINEL:
                live -= 1
                continue
            yield idx, ev
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def _run_wave_concurrent(bl_specs, assembler, concurrency):
    """Run a wave's BLs concurrently, then assemble their work-branches in fixed
    BL-id order (PROPOSAL_WAVE_CONCURRENCY.md Strategy A, step 3b - the concurrent
    wave orchestration the wave loop drives when wave_concurrency > 1).

    `bl_specs`: list of (bl_id, factory) in BL-id (assembly) order. Each `factory`
      is a zero-arg callable returning an async iterator of the BL events; the BL
      signals completion by yielding ONE event
      {"_wave_bl_done": {"bl_id", "work_branch"?, "outcome", ...}} - the structured
      result, read AFTER its stream ends (NOT the cosmetic interleaving). A BL is
      eligible for assembly only when outcome == "ready" and a work_branch is given.
    `assembler`: async fn(bl_id, work_branch) -> merge dict (merge_branch_into_target).
    `concurrency`: max BLs draining at once (the fan-in cap).

    Yields ("event", bl_id, ev) for live per-BL events as they arrive, then
    ("assembly", bl_id, merge) per assembled BL, then ("wave_done", None, summary).
    DETERMINISTIC: assembly runs in `bl_specs` order regardless of which BL finished
    first; a BL that did not reach outcome=="ready", errored, or whose assembly
    conflicts is left unassembled and surfaced (no-abort: the caller routes it on).
    """
    factories = [f for (_b, f) in bl_specs]
    idx_to_bid = {i: b for i, (b, _f) in enumerate(bl_specs)}
    results: dict = {}
    async for idx, ev in _merge_streams(factories, concurrency):
        if isinstance(ev, dict) and "_wave_bl_done" in ev:
            r = ev["_wave_bl_done"]
            results[r.get("bl_id", idx_to_bid.get(idx))] = r
        elif isinstance(ev, dict) and "_stream_error" in ev:
            b = idx_to_bid.get(ev.get("_idx", idx))
            results[b] = {"bl_id": b, "outcome": "stream_error", "error": ev.get("_stream_error")}
        else:
            yield ("event", idx_to_bid.get(idx), ev)
    assembled = []
    for bid, _f in bl_specs:
        r = results.get(bid)
        work_branch = (r or {}).get("work_branch")
        if not r or r.get("outcome") != "ready" or not work_branch:
            assembled.append({"bl_id": bid, "assembled": False,
                              "reason": (r or {}).get("outcome", "no_result")})
            continue
        merge = await assembler(bid, work_branch)
        assembled.append({"bl_id": bid, "assembled": bool(merge.get("ok")),
                          "kind": merge.get("kind"),
                          "conflict_files": merge.get("conflict_files")})
        yield ("assembly", bid, merge)
    yield ("wave_done", None, {"results": results, "assembled": assembled})


def _reconcile_unassembled_outcome(
    bl_outcomes_compact: list[dict], bid: str, kind: str | None,
) -> bool:
    """I-5 truthful aggregation (wave-concurrency Strategy A). In the concurrent
    path a BL's per-BL outcome (merged_full / merged_no_qa / merged_no_score) is
    labelled from WORK_BRANCH readiness and recorded BEFORE the BL-id-ordered
    assembly barrier runs. If that barrier then reports a conflict/error the BL
    never reached the trunk, so the recorded label is a lie. Rewrite the matching
    bl_outcomes entry to ``escalated_assembly_<kind>`` so the persisted roll-up
    matches escalated_bls. Returns True if an entry was corrected."""
    label = f"escalated_assembly_{kind or 'fail'}"
    for bo in bl_outcomes_compact:
        if bo.get("bl_id") == bid:
            bo["outcome"] = label
            return True
    return False


def _concurrent_assembly_decision(qa_doc_ok: bool, qa_merged: bool,
                                  score_doc_ok: bool) -> "tuple[str, bool]":
    """(outcome_label, assembly_eligible) for a wave-concurrent BL whose ENGINEER
    already passed its own green gate (deferred_ready) — its work_branch carries
    green-gated code (+ QA's reinforcement if QA added any).

    Assembly eligibility tracks the SAME bar that ships code in the serial body:
    engineer-green + QA satisfied doctrine. It deliberately does NOT require
    ``qa_merged`` (QA having added a reinforcement commit). A BL whose QA added
    nothing (new_commits==0 — e.g. the engineer already wrote the BL's tests, the
    common case for a frontend BL) still SHIPS its engineer-green code, exactly as
    the serial body leaves the engineer merge on the trunk. Requiring qa_merged
    stranded such BLs on their work_branch while still recording a ``merged_no_qa``
    label — counted in merged_total yet never on the trunk (the wave-concurrency
    honesty bug surfaced by the 2026-06-16 frontend-concurrency diagnostic).

    Honesty invariant: a ``merged_*`` label is returned IFF the BL is
    assembly-eligible (will reach the trunk). A BL that cannot assemble gets an
    ``*_escalated`` label and MUST be surfaced in ``escalated_bls`` by the caller.
    """
    if not qa_doc_ok:
        # QA could not satisfy doctrine after exhaustive attempts — a real failure.
        return ("qa_escalated", False)
    if not qa_merged:
        return ("merged_no_qa", True)
    if not score_doc_ok:
        return ("merged_no_score", True)
    return ("merged_full", True)


def _ensure_on_agent_branch(repo_dir: Path) -> dict:
    """Structural fix (2026-06-06, Ops/Steward proposal §9): put the target
    checkout on the configured ``agent_branch`` at run start.

    Rationale: the PO copy-back commit and ``fast_forward_target`` both act on
    ``repo_dir``'s *currently checked-out* branch. If the checkout is left on
    ``main_ref``, PO output commits onto main (violating its pristine status)
    and the orchestrator's own live ``events.jsonl`` dirties the merge
    precondition (``merge_to_target: main checkout has modified tracked
    files``). Checking out ``agent_branch`` here makes the fast-forward target
    equal the checked-out branch and keeps ``main_ref`` pristine. Creates the
    agent branch from ``main_ref`` if it does not yet exist. Never raises — on
    failure it emits an event the (future) Ops agent / operator can act on.
    """
    # Fully defensive: this runs inside run_brief's try/except, so any raise
    # would turn into a terminal `aborted`. A branch-prep helper must NEVER
    # abort the sprint — on any failure it emits ok=False and lets the run
    # proceed (the merge-guard / future Ops agent is the backstop).
    try:
        import subprocess  # local: module-level import is not guaranteed here

        cfg = repo_config_svc.load(repo_dir)
        ab = cfg.agent_branch

        def _g(*args):
            return subprocess.run(
                ["git", "-C", str(repo_dir), *args], capture_output=True, text=True
            )

        cur = _g("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if cur == ab:
            return _evt("run.branch_ready", agent_branch=ab, action="already_on", ok=True)
        if _g("rev-parse", "--verify", f"refs/heads/{ab}").returncode != 0:
            _g("branch", ab, cfg.main_ref)
        r = _g("checkout", ab)
        ok = r.returncode == 0
        return _evt(
            "run.branch_ready", agent_branch=ab,
            action="checked_out", from_branch=cur, ok=ok,
            detail=("" if ok else r.stderr.strip()[:200]),
        )
    except Exception as e:  # noqa: BLE001 — never abort the run from here
        return _evt("run.branch_ready", action="error", ok=False, detail=str(e)[:200])


async def run_brief(
    repo_dir: Path,
    repo_name: str,
    brief: str,
    project_name: str,
    retrieval_kwargs_builder,
    timeout_per_role: int = 2400,
    max_bls: int | None = None,
    skip_po: bool = False,
    stop_on_failure: bool = True,
    stop_on_qa_doctrine_failure: bool = False,
    run_id: str | None = None,
    brief_hash: str | None = None,
    start_bl: str | None = None,
    run_doctrine_meta: bool = True,
    feature_slug: str | None = None,
    run_acceptance: bool = True,  # ABL-0014 default flipped 2026-05-31 after 3 clean smokes
    acceptance_timeout: int = 3600,
    min_ui_coverage_ratio: float = 0.0,  # ABL-0014 Item 2 (Batch C); 0.0 = informational-only
    inject_acceptance_priors: bool = False,  # ABL-0014 §I.3 Batch E; OFF until 3-smoke calibration
    run_acceptance_followup: bool = False,  # ABL-0015 auto-dispatch; OFF until calibrated
    inject_lessons: bool = False,  # ABL-0016 cumulative learning; OFF until calibrated
    inject_global_lessons: bool = False,  # ABL-0018 Stage 3 cross-target push; OFF until calibrated
    run_janitor: bool = True,  # Janitor/Ops role (operator 2026-06-07): spawn the
                               # environment-repair agent on non-code failures.
                               # Flag = named rollback (set False to disable wiring).
    run_architect: bool = False,  # ABL-0002 Stage 1 (operator 2026-06-11): spawn the
                                  # Architect to ADJUDICATE a code-gate exhaustion
                                  # (retry_reframed / defer / escalate) instead of
                                  # halting. Default OFF until live-proven.
    warm_retrieval: bool = True,  # A56 (operator 2026-06-07): warm the LOCAL
                                  # retrieval backend before the PO so the first
                                  # agent isn't grounding-blind. Flag = rollback.
    contract_first: bool = True,  # Contract-First DEFAULT ON (operator 2026-06-16); gated to .NET (operator 2026-06-15):
                                   # PO authors an OpenAPI 3.1 contract; the
                                   # Engineer-as-materializer turns it into compilable
                                   # C# stubs gated by R22 (structural validation +
                                   # per-operation conformance + dotnet build) BEFORE
                                   # any slice runs. Additive; DEFAULT OFF = rollback.
    wave_concurrency: int = 1,  # PROPOSAL_WAVE_CONCURRENCY.md Strategy A: max BLs
                                # concurrent within a wave. DEFAULT 1 = serial
                                # scaffolding (live-proven); >1 inert until fan-in.
    wave_execution: bool = False,  # wave-execution Phase 2 (operator 2026-06-14):
                                   # schedule BLs by the R21 dependency DAG into
                                   # topological WAVES and emit wave.start/done
                                   # boundaries. Phase 2 runs each wave at
                                   # concurrency=1 (identical per-BL semantics);
                                   # OFF = today's flat sequential order. Flag =
                                   # rollback. Parallelism + reindex-at-barrier
                                   # are later phases that build on this schedule.
    reindex_incremental: bool = True,  # reindex incremental short-circuit (operator
                                       # 2026-06-15): index_initial establishes a merkle
                                       # snapshot (op=index_baseline) and each
                                       # reindex_after_* barrier embeds ONLY changed files
                                       # (op=reindex) vs a full re-embed. DEFAULT ON
                                       # (live-proven df8c69: 4.4s vs 900s, no silent
                                       # drop); set False for the full-index rollback.
) -> AsyncIterator[dict]:
    """Full brief-to-merged-feature pipeline. Yields SSE-shaped event dicts.

    `retrieval_kwargs_builder(wt, role, bl_id, trace)` produces the kwargs
    used by `stream_agent_task` to attach the retrieval MCP server. It is
    passed in (not built here) so the caller can centralize preflight failure
    handling.
    """
    summary = {
        "po": None,
        "bls": [],  # [{bl_id, engineer:{merged,no_op}, qa:{merged}, scorer:{doctrine_ok}}]
    }
    # A7: compact per-BL state for the disk checkpoint. Mirrors `summary["bls"]`
    # at a smaller, schema-stable shape so resume can read it without coupling
    # to the full per-role outcome structure.
    bl_outcomes_compact: list[dict] = []
    # ABL-0002 Stage 0: surfaced roll-ups so escalated/deferred BLs are reported in
    # the sprint_complete summary instead of vanishing from coverage math.
    escalated_bls: list[dict] = []
    deferred_bls: list[dict] = []
    # A7: terminal status for the disk state move. Defaults to "aborted" so any
    # return / exception path lands in done/ tagged as aborted; the single
    # sprint_complete path flips this just before the terminal yield.
    terminal_status = "aborted"

    # ABL-0020: snapshot which doctrine rules were in force for this run, so
    # ABL-0017 Stage-2 efficacy can join rule-state against bl_outcomes.
    # Static for the run; computed once, written on every checkpoint.
    _doctrine_manifest = doctrine_spec_svc.manifest()
    _doctrine_manifest["harness_sha"] = traces_svc.harness_sha()

    def _checkpoint(current_bl: str | None) -> None:
        try:
            run_state_svc.write_checkpoint(
                run_id=run_id,
                repo=repo_name,
                brief_hash=brief_hash,
                started_at=run_started_at,
                current_bl=current_bl,
                bl_outcomes=bl_outcomes_compact,
                status="active",
                doctrine_manifest=_doctrine_manifest,
            )
        except OSError:
            pass  # checkpoints are advisory; never block the sprint on disk I/O

    # B15+A7: tag this run for trace archival on exit AND for disk-persisted
    # state checkpoints. If the router (B2/B9) already minted a run_id, honor
    # it so the disk state file matches the lock metadata.
    run_started_at = datetime.now(timezone.utc)
    if run_id is None:
        run_id = f"run-{run_started_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
    # A7 needs brief_hash to find orphaned state on resume — keep "unknown"
    # only as a back-compat sentinel for callers that didn't pass one.
    if brief_hash is None:
        brief_hash = "unknown"

    yield _evt("start", brief_chars=len(brief), project_name=project_name, run_id=run_id)

    # Contract-First is DEFAULT ON but its materializer emits C# stubs and its R22 gate
    # runs `dotnet build`, so it only applies to .NET/C# targets. On any other stack
    # force it OFF (clean) so a non-dotnet brownfield run is byte-identical to pre-flip
    # behaviour rather than escalating at the dotnet-build gate.
    if contract_first and not _is_dotnet_target(repo_dir):
        contract_first = False
        yield _evt("contract_first.gated_off",
                   reason="target is not a .NET/C# repo (no .sln/.csproj); contract-first "
                          "materializer + R22 dotnet-build gate are C#-specific")

    try:
        # Structural fix (2026-06-06): operate on the configured agent branch,
        # never whatever happens to be checked out — keeps main_ref pristine and
        # makes the FF merge target == the checked-out branch.
        yield _ensure_on_agent_branch(repo_dir)

        # ── Step 2-3: initial indexing ─────────────────────────────────────────
        async for e in _run_indexers(repo_dir, "index_initial", reindex_incremental=reindex_incremental):
            yield e

        # ── Step 3.5: retrieval readiness gate (A56) ───────────────────────────
        # Warm the LOCAL retrieval backend (Ollama bge-m3 load + Milvus open +
        # graphify cache) BEFORE the first agent spawns, so the PO isn't handed a
        # cold "still connecting" server and forced to ground blind. Advisory:
        # warn-and-proceed on timeout (the post-PO grounding check is the safety
        # net). External-free: retrieval_warmup forwards only local provider env.
        if warm_retrieval:
            yield _evt("retrieval_warmup.start", target=str(repo_dir))
            warm = await retrieval_warmup_svc.warm_retrieval(repo_dir)
            yield _evt(
                "retrieval_warmup.done" if warm.get("ok") else "retrieval_warmup.timeout",
                ok=warm.get("ok"), attempts=warm.get("attempts"),
                elapsed_s=warm.get("elapsed_s"), reason=warm.get("reason"),
            )

        # ── Step 4: PO ─────────────────────────────────────────────────────────
        po_ok = True
        if not skip_po:
            yield _evt("po.start")
            po_trace_dir: str | None = None
            async for e in _po_flow(repo_dir, repo_name, brief, project_name,
                                    timeout_per_role, retrieval_kwargs_builder,
                                    run_id=run_id, brief_hash=brief_hash,
                                    feature_slug=feature_slug, inject_lessons=inject_lessons,
                                    inject_global_lessons=inject_global_lessons,
                                    contract_first=contract_first):
                if "_orchestrator_outcome" in e:
                    summary["po"] = e
                    po_ok = e.get("doctrine_ok", False)
                    continue
                # A56 part 2: capture the PO's trace dir so we can check whether
                # it actually grounded (its retrieval.jsonl) once it finishes.
                if e.get("phase") == "orchestrator.po.worktree_ready" or e.get("trace_dir"):
                    po_trace_dir = e.get("trace_dir") or po_trace_dir
                yield e
            # A56 part 2: surface a grounding-blind PO LOUDLY instead of letting
            # `doctrine_check: complete` hide it. With Step 3.5 warming the
            # backend first, 0 grounded calls now means a genuine retrieval
            # problem, not a cold-start race — make it observable (advisory; the
            # PO still produced a backlog via direct reads, so the run continues).
            po_grounding = _count_po_grounding(po_trace_dir)
            if po_grounding == 0:
                yield _evt("po.grounding_unavailable", trace_dir=po_trace_dir,
                           reason=("PO produced 0 grounded retrieval calls — backlog "
                                   "grounded on direct file reads, not the indexed "
                                   "graph/semantic layer (A56). Warm-up ran="
                                   f"{warm_retrieval})."))
            yield _evt("po.done", ok=po_ok, grounded_calls=po_grounding)
            if not po_ok and stop_on_failure:
                yield _evt("aborted", reason="PO doctrine failed")
                return

        # ── Step 4 cont: parse backlog ─────────────────────────────────────────
        bf = backlog_svc.find_backlog(repo_dir, feature_slug=feature_slug)
        if bf is None:
            yield _evt("aborted", reason="no BACKLOG.md found after PO phase")
            return
        items = backlog_svc.parse_file(bf)
        # Wave-execution Phase 2: when enabled, schedule by the R21 dependency DAG
        # into topological waves (flattened to preserve the existing single-loop
        # body) and remember each BL's wave index for wave.start/done boundary
        # events. concurrency=1 within a wave for now → byte-identical per-BL
        # behaviour; OFF = today's flat dependency order, no wave events at all.
        if wave_execution:
            _waves = _dep_waves(items)
            ordered = [it for w in _waves for it in w]
        else:
            _waves = None
            ordered = _dep_order(items)
        if max_bls is not None:
            ordered = ordered[:max_bls]
            if _waves is not None:
                _kept = {it.id for it in ordered}
                _waves = [w2 for w2 in
                          ([it for it in w if it.id in _kept] for w in _waves) if w2]
        _wave_of = ({it.id: wi for wi, w in enumerate(_waves) for it in w}
                    if _waves is not None else {})
        _dag_width = backlog_svc.dag_width(items)  # Phase B fan-out metric
        yield _evt("backlog_parsed", count=len(ordered), dag_width=_dag_width,
                   bls=[{"id": it.id, "title": it.title,
                         "deps": str(it.meta.get("dependencies") or "")} for it in ordered],
                   waves=([[it.id for it in w] for w in _waves] if _waves is not None else None))
        if contract_first and _dag_width <= 1 and len(items) > 1:
            # Contract-First Phase B: a serial DAG under contract_first means the PO
            # decomposed by layers, not contract-bound vertical slices — the parallel
            # crew is starved. Advisory (non-blocking) so a genuinely-serial feature
            # is never false-failed; the metric makes the regression observable.
            yield _evt("contract_first.fanout_advisory", dag_width=_dag_width,
                       n_bls=len(items),
                       note=("contract_first decomposition is serial (DAG width<=1); "
                             "expected a width>=2 fan-out for a parallelizable feature"))
        _checkpoint(current_bl=None)  # A7: first checkpoint after PO+parse

        # Contract-First Phase 1 (R22, operator 2026-06-15): materialize the PO's
        # OpenAPI contract into compilable C# stubs BEFORE any slice runs. Additive +
        # flag-gated — with contract_first=False this whole block is skipped and the
        # path is byte-identical to today.
        if contract_first:
            async for _ce in _contract_flow(repo_dir, repo_name, run_id=run_id,
                                             feature_slug=feature_slug,
                                             timeout=timeout_per_role,
                                             retrieval_kwargs_builder=retrieval_kwargs_builder):
                yield _ce

        # Simple gating model (2026-06-06): the agent-branch HEAD at sprint start
        # (after PO import, before BL-0001) is the baseline for the ONE full-suite
        # regression checkpoint run at the acceptance phase — it catches any
        # collateral regression the assembled feature introduced to PRE-EXISTING
        # functionality (per-BL gates only run each BL's own tests). Best-effort.
        try:
            run_base_sha = await rev_parse(repo_dir, repo_config_svc.load(repo_dir).agent_branch)
        except Exception:  # noqa: BLE001
            run_base_sha = None

        # ── Step 5: per-BL loop ────────────────────────────────────────────────
        # A4: when `start_bl` is set, skip BLs in dep order until we reach it.
        # Convenience for backfilling a specific BL after a mid-sprint abort
        # (e.g. Sprint 3 BL-0002 had no scorer because the orchestrator died
        # mid-reindex). Operator passes start_bl="BL-0002" + skip_po=true to
        # resume the scorer for that BL onward.
        _reached_start_bl = start_bl is None
        _prev_wave = None

        async def _one_bl_concurrent(it):
            """wave-concurrency Strategy A intra-wave BL body. Runs engineer
            (defer_merge) → QA → scorer on an ISOLATED branch lineage; emits the
            same live events + bl.start/bl.done the serial body emits, but does NOT
            integrate into agent_branch (the wave barrier does that in BL-id order)
            and NEVER yields _wave_abort (a failing BL is surfaced, not aborted).
            Always yields exactly ONE {"_wave_bl_done": {...}} as its final event.
            """
            bl_id = it.id
            per_bl = {"bl_id": bl_id, "title": it.title}
            yield _evt("bl.start", bl_id=bl_id, title=it.title)
            # wave_base: the agent_branch SHA at BL start (the common fork point for
            # every BL in this wave). The QA diff base for the BL's own tests.
            try:
                wave_base = await rev_parse(repo_dir, repo_config_svc.load(repo_dir).agent_branch)
            except Exception:  # noqa: BLE001
                wave_base = None

            # ── Engineer (defer_merge: leaves work on its work_branch) ──
            yield _evt("engineer.start", bl_id=bl_id)
            eng_outcome = None
            try:
                async for e in _engineer_flow(repo_dir, repo_name, bl_id,
                                               timeout_per_role, retrieval_kwargs_builder,
                                               run_id=run_id, feature_slug=feature_slug,
                                               inject_lessons=inject_lessons,
                                               inject_global_lessons=inject_global_lessons,
                                               defer_merge=True, contract_first=contract_first):
                    if "_orchestrator_outcome" in e:
                        eng_outcome = e
                        continue
                    yield e
            except Exception as exc:  # noqa: BLE001 — wedge-proof (mirror serial body)
                yield _evt("engineer.error", bl_id=bl_id,
                           error=f"{type(exc).__name__}: {exc}"[:500])
                eng_outcome = {"role": "engineer", "bl_id": bl_id,
                               "merged": False, "no_op": False, "engineer_error": True}
            per_bl["engineer"] = eng_outcome or {"merged": False}
            yield _evt("engineer.done", **(eng_outcome or {"bl_id": bl_id}))

            eng_no_op = bool(eng_outcome and eng_outcome.get("no_op"))
            eng_ready = bool(eng_outcome and eng_outcome.get("deferred_ready"))
            work_branch = (eng_outcome or {}).get("work_branch")

            # Engineer no_op: nothing to assemble; surface as no_op (not eligible).
            if eng_no_op:
                per_bl["qa"] = {"merged": False}
                summary["bls"].append(per_bl)
                bl_outcomes_compact.append({"bl_id": bl_id, "outcome": "no_op"})
                yield _evt("bl.done", bl_id=bl_id, outcome="no_op")
                yield {"_wave_bl_done": {"bl_id": bl_id, "outcome": "no_op"}}
                return

            # Engineer did NOT reach a green gate (escalated / harness error) — the
            # engineer never integrated, so no rollback is needed. Surface honestly
            # and DO NOT abort siblings (no _wave_abort in concurrent mode).
            if not eng_ready or not work_branch:
                _dossier = (eng_outcome or {}).get("dossier") or {
                    "role": "engineer", "bl_id": bl_id,
                    "harness_error": (eng_outcome or {}).get("engineer_error", False),
                }
                per_bl["qa"] = {"merged": False}
                summary["bls"].append(per_bl)
                bl_outcomes_compact.append({"bl_id": bl_id, "outcome": "engineer_escalated"})
                escalated_bls.append({"bl_id": bl_id, "role": "engineer",
                                      "reason": (f"engineer could not reach a green gate for {bl_id} "
                                                 f"after exhaustive investigate→fix→re-test attempts")})
                yield _evt("bl.escalated", bl_id=bl_id, role="engineer",
                           reason=(f"engineer could not reach a green gate for {bl_id} "
                                   f"(wave-concurrent — surfaced, siblings continue)"),
                           dossier=_dossier)
                yield _evt("bl.done", bl_id=bl_id, outcome="engineer_escalated")
                yield {"_wave_bl_done": {"bl_id": bl_id, "outcome": "engineer_escalated"}}
                return

            # ── QA (forks from + merges back into the engineer's work_branch) ──
            yield _evt("qa.start", bl_id=bl_id)
            qa_outcome = None
            async for e in _qa_or_scorer_flow(repo_dir, repo_name, bl_id, "qa",
                                               timeout_per_role, retrieval_kwargs_builder,
                                               run_id=run_id, feature_slug=feature_slug,
                                               inject_lessons=inject_lessons,
                                               inject_global_lessons=inject_global_lessons,
                                               bl_base_ref=wave_base,
                                               base_branch_override=work_branch,
                                               merge_target_override=work_branch):
                if "_orchestrator_outcome" in e:
                    qa_outcome = e
                    continue
                yield e
            per_bl["qa"] = qa_outcome or {"merged": False}
            yield _evt("qa.done", **(qa_outcome or {"bl_id": bl_id}))

            qa_doc_ok = bool(qa_outcome and qa_outcome.get("doctrine_ok"))
            qa_merged = bool(qa_outcome and qa_outcome.get("merged"))

            # ── Scorer (read-only; forks from work_branch to read the BL's work) ──
            yield _evt("scorer.start", bl_id=bl_id)
            score_outcome = None
            async for e in _qa_or_scorer_flow(repo_dir, repo_name, bl_id, "scorer",
                                               timeout_per_role, retrieval_kwargs_builder,
                                               run_id=run_id, feature_slug=feature_slug,
                                               inject_lessons=inject_lessons,
                                               inject_global_lessons=inject_global_lessons,
                                               base_branch_override=work_branch,
                                               merge_target_override=work_branch):  # wave-concurrency: scorer persists its scorecard to the BL work_branch (NOT agent_branch); the BL-id-ordered assembly barrier carries it to the trunk — restores full defer-merge (was leaking BL work onto the trunk mid-wave, making BL-0001 assemble as noop)
                if "_orchestrator_outcome" in e:
                    score_outcome = e
                    continue
                yield e
            per_bl["scorer"] = score_outcome or {}
            yield _evt("scorer.done", **(score_outcome or {"bl_id": bl_id}))
            score_doc_ok = bool(score_outcome and score_outcome.get("doctrine_ok"))

            # wave-concurrency honesty + assembly eligibility (single source of
            # truth: _concurrent_assembly_decision). The engineer already passed
            # its green gate (deferred_ready); the work_branch carries that
            # green-gated code. A BL ships (assembles) on engineer-green + QA
            # doctrine — NOT on qa_merged — matching the serial body. A BL that
            # CANNOT assemble never carries a merged_* label (it escalates), so
            # merged_total / coverage never count code that isn't on the trunk.
            outcome, _eligible = _concurrent_assembly_decision(
                qa_doc_ok, qa_merged, score_doc_ok)
            summary["bls"].append(per_bl)
            bl_outcomes_compact.append({"bl_id": bl_id, "outcome": outcome})
            if _eligible:
                yield _evt("bl.done", bl_id=bl_id, outcome=outcome)
                yield {"_wave_bl_done": {"bl_id": bl_id, "work_branch": work_branch,
                                         "outcome": "ready"}}
            else:
                # No-abort: QA could not satisfy doctrine — surface honestly
                # (escalated, NOT a merged_* label, excluded from merged_total),
                # do not assemble; siblings continue (mirrors engineer_escalated).
                escalated_bls.append({"bl_id": bl_id, "role": "qa",
                                      "reason": (f"QA could not satisfy doctrine for {bl_id} "
                                                 f"after exhaustive investigate→fix→re-test "
                                                 f"attempts (wave-concurrent — surfaced, "
                                                 f"siblings continue)")})
                yield _evt("bl.escalated", bl_id=bl_id, role="qa",
                           reason=f"QA could not satisfy doctrine for {bl_id}",
                           dossier=(qa_outcome or {}).get("dossier") or {})
                yield _evt("bl.done", bl_id=bl_id, outcome=outcome)
                yield {"_wave_bl_done": {"bl_id": bl_id, "outcome": outcome}}
            return

        async def _one_bl(it, concurrent: bool = False):
            bl_id = it.id
            if concurrent:
                # wave-concurrency Strategy A: isolated per-BL lineage. The engineer
                # runs with defer_merge=True (work stays on its work_branch, which
                # survives worktree removal); QA/scorer fork from that work_branch and
                # QA FF-merges its tests back into it. This body NEVER touches
                # agent_branch and NEVER yields _wave_abort — a failing BL is surfaced
                # via the _wave_bl_done outcome and must not abort its siblings. The
                # wave barrier (driven by _run_wave_concurrent) assembles ready
                # work_branches into agent_branch deterministically in BL-id order.
                async for ev in _one_bl_concurrent(it):
                    yield ev
                return
            per_bl = {"bl_id": bl_id, "title": it.title}
            yield _evt("bl.start", bl_id=bl_id, title=it.title)
            _checkpoint(current_bl=bl_id)  # A7: mark which BL is in flight
            # Auto-merge atomicity (2026-06-06): capture the agent-branch HEAD
            # before this BL's engineer can fast-forward-merge into it. If the BL
            # later aborts AFTER the engineer merged but BEFORE QA merged, we
            # reset back to this SHA so an aborted BL leaves the trunk exactly as
            # it was — the engineer's work cannot outlive the BL's failure.
            _cfg_bl = repo_config_svc.load(repo_dir)
            # Best-effort: if the SHA can't be read, rollback is simply skipped —
            # a rev-parse hiccup must never abort the run.
            try:
                pre_bl_sha = await rev_parse(repo_dir, _cfg_bl.agent_branch)
            except Exception:  # noqa: BLE001
                pre_bl_sha = None

            # Engineer
            yield _evt("engineer.start", bl_id=bl_id)
            eng_outcome = None
            try:
                async for e in _engineer_flow(repo_dir, repo_name, bl_id,
                                               timeout_per_role, retrieval_kwargs_builder,
                                               run_id=run_id, feature_slug=feature_slug,
                                               inject_lessons=inject_lessons,
                                               inject_global_lessons=inject_global_lessons, contract_first=contract_first):
                    if "_orchestrator_outcome" in e:
                        eng_outcome = e
                        continue
                    yield e
            except Exception as exc:  # noqa: BLE001
                # #3 wedge-proof (A45-coupled, 2026-06-04 BL-0006): _engineer_flow
                # raised before yielding its outcome sentinel — e.g. an idle-kill
                # propagating mid-await, a gate subprocess crash, or an unexpected
                # error. Treat it as engineer_unmerged so the standard not-merged
                # path below fires bl.done(engineer_unmerged) and honors
                # stop_on_failure deterministically, instead of letting the
                # exception escape the BL loop with no terminal event (the
                # 0-procs-no-terminal wedge that only End-Sprint could clear).
                # This does NOT touch the R10/R10.1/R10.2 retry loops inside
                # _engineer_flow; CancelledError/GeneratorExit are BaseException
                # → not caught → clean shutdown still propagates.
                yield _evt("engineer.error", bl_id=bl_id,
                           error=f"{type(exc).__name__}: {exc}"[:500])
                eng_outcome = {"role": "engineer", "bl_id": bl_id,
                               "merged": False, "no_op": False, "engineer_error": True}
            per_bl["engineer"] = eng_outcome or {"merged": False}
            yield _evt("engineer.done", **(eng_outcome or {"bl_id": bl_id}))
            # R11 no_op: engineer detected work already in codebase. But QA may
            # still be missing (resume-after-crash). Only short-circuit if the QA
            # report is also already on the branch — otherwise fall through and
            # run QA against the existing engineer work.
            #
            # B12: file-existence alone is NOT enough. A QA crash mid-write or
            # a stale file from a prior aborted run would silently skip real
            # QA. Additionally require a `qa(<bl>...)` commit on the agent
            # branch touching the file.
            qa_report = repo_dir / ".agile-v" / "qa" / f"{bl_id}.md"
            cfg = repo_config_svc.load(repo_dir)
            qa_committed = _qa_commit_landed(repo_dir, bl_id, cfg.agent_branch)
            if eng_outcome and eng_outcome.get("no_op"):
                if qa_report.exists() and qa_committed:
                    summary["bls"].append(per_bl)
                    bl_outcomes_compact.append({"bl_id": bl_id, "outcome": "no_op"})
                    _checkpoint(current_bl=None)  # A7
                    yield _evt("bl.done", bl_id=bl_id, outcome="no_op")
                    return
                # Engineer no_op but QA report missing OR uncommitted —
                # partial-resume path. Reason string distinguishes the cases.
                if qa_report.exists() and not qa_committed:
                    reason = (
                        f"engineer no_op; .agile-v/qa/{bl_id}.md exists but no "
                        f"qa(...) commit on {cfg.agent_branch} touches it — "
                        f"running QA on current branch (B12 cross-check)"
                    )
                else:
                    reason = (
                        f"engineer no_op but .agile-v/qa/{bl_id}.md missing — "
                        f"running QA on current branch"
                    )
                yield _evt("partial_resume", bl_id=bl_id, reason=reason)
                # Skip reindex (engineer added nothing new) + skip merged check.
                # Fall through directly to QA below.
            elif not (eng_outcome and eng_outcome.get("merged")):
                # No-abort doctrine (Option A): the engineer exhausted its deep
                # investigate→fix→re-test loop without a green gate. This is an
                # ESCALATION to the operator with a full dossier, NOT a routine
                # abort. (The engineer never merged, so the trunk is already
                # pristine — no rollback needed here.)
                _dossier = (eng_outcome or {}).get("dossier") or {
                    "role": "engineer", "bl_id": bl_id,
                    "harness_error": (eng_outcome or {}).get("engineer_error", False),
                }
                # Janitor (R16): if the engineer was blocked by a NON-CODE failure
                # (infra_fail, merge error) — NOT a code defect (failed/no_tests/
                # regressed/inconclusive, which the engineer's own no-abort loop
                # owns) — spawn the environment-repair agent. It repairs the live
                # run state (full §6 authority; R13-backstopped) and routes any
                # structural anomaly to the doctrine-meta loop. The repair + its
                # diagnosis attach to the escalation dossier. (Auto re-run of the
                # BL after repair is a separate, larger increment — the per-BL
                # body must first become a retryable unit; see handoff.)
                # A58: fire on a non-code GATE kind (error/infra_fail) OR on a
                # merge-step failure that escalated after a GREEN gate (blocker
                # == "merge_error"). The latter previously slipped through because
                # the guard inspected only `last_gate_kind`, which is "green" when
                # the gate passed but merge_to_target failed (e.g. dirty target
                # checkout) — the engineer-path analogue of the QA merge-failed
                # branch, which already spawns the Janitor unconditionally.
                _merge_blocked = _dossier.get("blocker") == "merge_error"
                _recovered = False
                if _engineer_janitor_trigger(_dossier, run_janitor):
                    _failed_kind = (_dossier.get("merge_kind") if _merge_blocked
                                    else _dossier.get("last_gate_kind"))
                    _blocker_reason = (
                        str(_dossier.get("merge_error") or "merge_to_target failed") if _merge_blocked
                        else str(_dossier.get("last_gate_reason")
                                 or _dossier.get("last_gate_kind") or "non-code failure"))
                    try:
                        async for je in _run_janitor(
                            repo_dir, repo_name, run_id, feature_slug,
                            failed_step=f"engineer.{'merge_error' if _merge_blocked else _failed_kind}",
                            blocker_reason=_blocker_reason,
                            failing_role="engineer", bl_id=bl_id, timeout=timeout_per_role):
                            yield je
                        _dossier["janitor"] = getattr(_run_janitor, "last_outcome", None) or {}
                    except Exception as exc:  # noqa: BLE001 — Janitor is advisory; never block the escalation
                        yield _evt("janitor.error", bl_id=bl_id, run_id=run_id, error=str(exc)[:300])
                    # A59: the Janitor must FULLY resolve a merge failure, not
                    # repair-and-escalate. If it repaired the environment, RE-ATTEMPT
                    # the merge it was blocked on (the agent branch survived worktree
                    # removal). Success → the BL is integrated and proceeds through the
                    # normal QA/scorer continuation, exactly as a clean merge would.
                    # This is the "agent resolves its own issue to completion" standard:
                    # a dirty checkout is something a copy of me would just fix and
                    # re-merge, so the system must let the Janitor do the same.
                    if _should_remerge_after_janitor(_dossier):
                        remerge = await fast_forward_target(
                            repo_dir, _dossier["merge_branch"], target_ref=cfg.agent_branch)
                        yield _evt("merge_retry_post_janitor", bl_id=bl_id, role="engineer",
                                   ok=remerge.get("ok"), merged_sha=remerge.get("merged_sha"),
                                   kind=remerge.get("kind"), error=remerge.get("error"),
                                   branch=_dossier.get("merge_branch"))
                        if remerge.get("ok"):
                            _recovered = True
                            if eng_outcome is not None:
                                eng_outcome["merged"] = True
                            yield _evt("janitor.resolved", bl_id=bl_id, role="engineer",
                                       reason=(f"Janitor repaired the environment and the merge "
                                               f"landed ({(remerge.get('merged_sha') or '')[:8]}); "
                                               f"{bl_id} fully resolved in-loop — no escalation"))
                # === ABL-0002 Stage 1: Architect adjudication at code-gate exhaustion ===
                # The Janitor handles env/merge; if it didn't recover this (a CODE
                # failure), the Architect makes the step-back decision the confined
                # engineer cannot — reframe & re-run, defer-and-continue, or escalate
                # honestly — instead of halting the sprint. Operator-gated (run_architect).
                if not _recovered and _architect_should_adjudicate(_dossier, run_architect):
                    _adj = {}
                    try:
                        async for ae in _run_architect(repo_dir, repo_name, run_id,
                                                       feature_slug, bl_id=bl_id,
                                                       dossier=_dossier, timeout=timeout_per_role):
                            yield ae
                        _adj = getattr(_run_architect, "last_outcome", None) or {}
                    except Exception as exc:  # noqa: BLE001 — advisory; never block escalation
                        yield _evt("architect.error", bl_id=bl_id, run_id=run_id, error=str(exc)[:300])
                    _dossier["architect"] = _adj
                    _av = _adj.get("verdict")
                    if _av == "retry_reframed" and _adj.get("directive"):
                        try:
                            _sect = _resolve_engineer_section(repo_dir, bl_id, feature_slug, None)
                        except Exception:  # noqa: BLE001
                            _sect = ""
                        _reframed = (f"{_sect}\n\n## ARCHITECT DIRECTIVE (adjudication — "
                                     f"root-cause corrected)\n{_adj.get('directive')}\n")
                        yield _evt("architect.retry_reframed", bl_id=bl_id,
                                   root_cause=_adj.get("root_cause"))
                        _re_out = None
                        async for e in _engineer_flow(repo_dir, repo_name, bl_id,
                                                      timeout_per_role, retrieval_kwargs_builder,
                                                      run_id=run_id, feature_slug=feature_slug,
                                                      section_override=_reframed,
                                                      inject_lessons=inject_lessons,
                                                      inject_global_lessons=inject_global_lessons, contract_first=contract_first):
                            if "_orchestrator_outcome" in e:
                                _re_out = e
                                continue
                            yield e
                        if _re_out and _re_out.get("merged"):
                            _recovered = True
                            eng_outcome = _re_out
                            yield _evt("architect.resolved", bl_id=bl_id, verdict="retry_reframed",
                                       reason=(f"Architect reframed the root cause and the engineer's "
                                               f"re-run merged {bl_id} — resolved in-loop, no escalation"))
                    elif _av == "defer":
                        _dreason = (_adj.get("defer_reason") or "architect deferred (out of scope)")[:500]
                        summary["bls"].append(per_bl)
                        bl_outcomes_compact.append({"bl_id": bl_id, "outcome": "deferred",
                                                    "reason": _dreason[:300]})
                        deferred_bls.append({"bl_id": bl_id, "reason": _dreason})
                        _checkpoint(current_bl=None)  # A7
                        yield _evt("bl.deferred", bl_id=bl_id, reason=_dreason, dossier=_dossier)
                        yield _evt("bl.done", bl_id=bl_id, outcome="deferred")
                        return
                    # escalate / split / respec → fall through to the escalate block;
                    # the Architect's reasoning is attached to _dossier["architect"].
                if not _recovered:
                    summary["bls"].append(per_bl)
                    bl_outcomes_compact.append({"bl_id": bl_id, "outcome": "engineer_escalated"})
                    _checkpoint(current_bl=None)  # A7
                    # A58: an honest reason. A merge-step failure is NOT "could not
                    # reach a green gate" — the gate was green; the branch could not
                    # be integrated. Name the real blocker so the dossier and the
                    # reason agree (I-5 truthful aggregation).
                    if _dossier.get("blocker") == "merge_error":
                        _esc_reason = (
                            f"engineer's {bl_id} passed its gate ({_dossier.get('last_gate_reason')}) "
                            f"but could not be merged: {_dossier.get('merge_error') or _dossier.get('merge_kind')}"
                            + ("" if _dossier.get("janitor") else " (Janitor did not resolve it)"))
                    else:
                        _esc_reason = (f"engineer could not reach a green gate for {bl_id} "
                                       f"after exhaustive investigate→fix→re-test attempts")
                    escalated_bls.append({"bl_id": bl_id, "role": "engineer",
                                          "reason": _esc_reason})  # ABL-0002 Stage 0 roll-up
                    yield _evt("bl.escalated", bl_id=bl_id, role="engineer",
                               reason=_esc_reason, dossier=_dossier)
                    yield _evt("bl.done", bl_id=bl_id, outcome="engineer_escalated")
                    if stop_on_failure:
                        yield _evt("escalated", bl_id=bl_id, role="engineer",
                                   reason=f"engineer escalated {bl_id} for operator review "
                                          f"(no-abort doctrine, Option A — dossier attached)",
                                   dossier=_dossier)
                        yield {"_wave_abort": "escalated"}
                        return
                    return
                # A59: Janitor-recovered merge — reindex then fall through to the
                # normal QA/scorer continuation (same as a clean merge).
                # Wave Phase 3: in wave mode the post-engineer reindex is deferred
                # to the wave barrier (1/wave); same-wave BLs are independent.
                if not wave_execution:
                    async for e in _run_indexers(repo_dir, f"reindex_after_engineer.{bl_id}", reindex_incremental=reindex_incremental):
                        yield e
            else:
                # Reindex post-engineer (only when engineer actually committed).
                # Wave Phase 3: deferred to the wave barrier in wave mode.
                if not wave_execution:
                    async for e in _run_indexers(repo_dir, f"reindex_after_engineer.{bl_id}", reindex_incremental=reindex_incremental):
                        yield e

            # QA
            yield _evt("qa.start", bl_id=bl_id)
            qa_outcome = None
            async for e in _qa_or_scorer_flow(repo_dir, repo_name, bl_id, "qa",
                                                timeout_per_role, retrieval_kwargs_builder,
                                                run_id=run_id, feature_slug=feature_slug,
                                                inject_lessons=inject_lessons,
                                                inject_global_lessons=inject_global_lessons,
                                                bl_base_ref=pre_bl_sha):
                if "_orchestrator_outcome" in e:
                    qa_outcome = e
                    continue
                yield e
            per_bl["qa"] = qa_outcome or {"merged": False}
            yield _evt("qa.done", **(qa_outcome or {"bl_id": bl_id}))

            # A2: QA gave up on doctrine after 2 retries → surface as a
            # distinct failure event (the prior code silently swallowed this
            # and labeled the BL "merged"). Default behavior is to continue;
            # opt-in via stop_on_qa_doctrine_failure aborts the sprint.
            qa_doc_ok = bool(qa_outcome and qa_outcome.get("doctrine_ok"))
            qa_merged = bool(qa_outcome and qa_outcome.get("merged"))
            if not qa_doc_ok and not qa_merged:
                yield _evt(
                    "qa_doctrine_failed",
                    bl_id=bl_id,
                    summary=(qa_outcome or {}).get("doctrine_summary"),
                )
                if stop_on_qa_doctrine_failure:
                    summary["bls"].append(per_bl)
                    bl_outcomes_compact.append({"bl_id": bl_id, "outcome": "merged_no_qa"})
                    _checkpoint(current_bl=None)  # A7
                    # Auto-merge atomicity (2026-06-06): the engineer already
                    # merged this BL; roll the trunk back so an aborted BL leaves
                    # no QA-unvalidated engineer code behind.
                    if pre_bl_sha:
                        rb = await reset_target_to(repo_dir, _cfg_bl.agent_branch, pre_bl_sha)
                        bl_outcomes_compact[-1]["outcome"] = "rolled_back"
                        yield _evt("bl.rolled_back", bl_id=bl_id, to_sha=pre_bl_sha[:8],
                                   ok=rb.get("ok"), error=rb.get("error"),
                                   reason="QA doctrine failed; engineer merge undone")
                    yield _evt("bl.done", bl_id=bl_id,
                               outcome="rolled_back" if pre_bl_sha else "merged_no_qa")
                    # No-abort doctrine (Option A): escalate with dossier, not abort.
                    yield _evt("escalated", bl_id=bl_id, role="qa",
                               reason=f"QA could not satisfy doctrine for {bl_id} after exhaustive "
                                      f"attempts (stop_on_qa_doctrine_failure) — escalating for operator review",
                               dossier=(qa_outcome or {}).get("dossier") or {})
                    yield {"_wave_abort": "escalated"}
                    return

            # A37: QA merge failed independent of doctrine. Engineer-merge-
            # failure aborts under stop_on_failure by symmetry — QA must too,
            # otherwise the branch ships engineer code without QA's
            # reinforcement tests. Common trigger before A35 fix #2 landed:
            # graphify-out symlink collision on the target checkout when the
            # agent branch's tracked copy can't FF over an untracked
            # working-tree symlink (documents_2 BL-0002 + BL-0007 forensic).
            # Skip reindex_after_qa + scorer when QA didn't merge — there is
            # no QA-added content to reindex against, and scoring an unmerged
            # QA would record metrics that don't reflect the agent_branch.
            if qa_doc_ok and not qa_merged:
                yield _evt(
                    "qa_merge_failed",
                    bl_id=bl_id,
                    summary=(qa_outcome or {}).get("doctrine_summary"),
                )
                # Janitor (R16): QA passed doctrine but its merge did not land —
                # this is the canonical NON-CODE (environment) failure (dirty
                # checkout, branch/ref drift, graphify-out symlink collision —
                # the A35/A37 class). Spawn the environment-repair agent to fix
                # the live run state (full §6 authority; R13-backstopped) and
                # route structural anomalies to doctrine-meta. (Auto re-run of QA
                # after repair is the same deferred increment as the engineer
                # path — see handoff.)
                _qa_dossier = (qa_outcome or {}).get("dossier") or {}
                if run_janitor:
                    try:
                        async for je in _run_janitor(
                            repo_dir, repo_name, run_id, feature_slug,
                            failed_step="qa.merge_to_target",
                            blocker_reason=str((qa_outcome or {}).get("doctrine_summary")
                                               or _qa_dossier.get("last_gate_reason")
                                               or "QA merge did not land"),
                            failing_role="qa", bl_id=bl_id, timeout=timeout_per_role):
                            yield je
                        _qa_dossier["janitor"] = getattr(_run_janitor, "last_outcome", None) or {}
                    except Exception as exc:  # noqa: BLE001 — Janitor is advisory; never block the rollback
                        yield _evt("janitor.error", bl_id=bl_id, run_id=run_id, error=str(exc)[:300])
                summary["bls"].append(per_bl)
                bl_outcomes_compact.append({"bl_id": bl_id, "outcome": "merged_no_qa"})
                _checkpoint(current_bl=None)  # A7
                if stop_on_failure:
                    # Auto-merge atomicity (2026-06-06): the engineer's BL was
                    # already fast-forward-merged into the trunk on its own green
                    # gate; QA then failed to merge and we are aborting. Roll the
                    # trunk back to pre_bl_sha so the aborted BL leaves NO
                    # QA-unvalidated engineer code behind (an `abort` must mean
                    # the trunk is pristine for this BL). The dropped engineer
                    # work stays recoverable on its agent/<task_id> branch.
                    if pre_bl_sha:
                        rb = await reset_target_to(repo_dir, _cfg_bl.agent_branch, pre_bl_sha)
                        bl_outcomes_compact[-1]["outcome"] = "rolled_back"
                        yield _evt("bl.rolled_back", bl_id=bl_id, to_sha=pre_bl_sha[:8],
                                   ok=rb.get("ok"), error=rb.get("error"),
                                   reason="QA did not merge; engineer merge undone")
                    yield _evt("bl.done", bl_id=bl_id,
                               outcome="rolled_back" if pre_bl_sha else "merged_no_qa")
                    # No-abort doctrine (Option A): escalate with dossier, not abort.
                    yield _evt("escalated", bl_id=bl_id, role="qa",
                               reason=f"QA could not reach a green gate for {bl_id} after exhaustive "
                                      f"investigate→fix→re-test attempts — escalating for operator review",
                               dossier=_qa_dossier)
                    yield {"_wave_abort": "escalated"}
                    return
                # stop_on_failure=False: best-effort continue. The engineer's
                # merge stays on the trunk (rollback is scoped to aborts); the
                # merged_no_qa outcome flags that it shipped without QA.
                yield _evt("bl.done", bl_id=bl_id, outcome="merged_no_qa")
                return

            # Reindex post-QA (QA may add characterization tests).
            # Wave Phase 3: deferred to the wave barrier in wave mode.
            if not wave_execution:
                async for e in _run_indexers(repo_dir, f"reindex_after_qa.{bl_id}", reindex_incremental=reindex_incremental):
                    yield e

            # Scorer
            yield _evt("scorer.start", bl_id=bl_id)
            score_outcome = None
            async for e in _qa_or_scorer_flow(repo_dir, repo_name, bl_id, "scorer",
                                                timeout_per_role, retrieval_kwargs_builder,
                                                run_id=run_id, feature_slug=feature_slug,
                                                inject_lessons=inject_lessons,
                                                inject_global_lessons=inject_global_lessons):
                if "_orchestrator_outcome" in e:
                    score_outcome = e
                    continue
                yield e
            per_bl["scorer"] = score_outcome or {}
            yield _evt("scorer.done", **(score_outcome or {"bl_id": bl_id}))

            # A5: outcome reflects the WORST role result, not just the engineer.
            # Possible labels (this branch only — engineer already merged):
            #   merged_full     — engineer ✓ qa ✓ scorer doctrine ✓
            #   merged_no_qa    — engineer ✓ qa failed/didn't merge
            #   merged_no_score — engineer ✓ qa ✓ scorer doctrine ✗
            score_doc_ok = bool(score_outcome and score_outcome.get("doctrine_ok"))
            if not qa_doc_ok or not qa_merged:
                outcome = "merged_no_qa"
            elif not score_doc_ok:
                outcome = "merged_no_score"
            else:
                outcome = "merged_full"
            summary["bls"].append(per_bl)
            bl_outcomes_compact.append({"bl_id": bl_id, "outcome": outcome})
            _checkpoint(current_bl=None)  # A7
            yield _evt("bl.done", bl_id=bl_id, outcome=outcome)

        # wave-concurrency Strategy A (operator 2026-06-14): when the operator
        # opts into BOTH wave scheduling AND concurrency>1, iterate the DAG WAVES
        # and run each multi-BL wave's BLs CONCURRENTLY on isolated branch
        # lineages, then assemble their work-branches into agent_branch in fixed
        # BL-id order at the wave barrier (deterministic, interleaving-independent).
        # A single-BL wave runs the ordinary serial _one_bl path. The flattened
        # serial loop below is UNCHANGED and still drives wave_concurrency<=1 (and
        # wave_execution off) byte-identically.
        _concurrent_wave_mode = (wave_execution and wave_concurrency
                                 and wave_concurrency > 1 and _waves is not None)
        if _concurrent_wave_mode:
            # Honor start_bl: build the set of BLs to actually run (resume support).
            _run_ids = {it.id for it in ordered}
            if start_bl is not None:
                _seen = False
                _run_ids = set()
                for it in ordered:
                    if it.id == start_bl:
                        _seen = True
                    if _seen:
                        _run_ids.add(it.id)
            _aborted = False
            for _wi, _wave in enumerate(_waves):
                _wave_bls = [it for it in _wave if it.id in _run_ids]
                if not _wave_bls:
                    continue
                yield _evt("wave.start", wave=_wi, bls=[i.id for i in _wave_bls])
                if len(_wave_bls) == 1:
                    # Degenerate wave → ordinary serial path (handles _wave_abort).
                    async for ev in _one_bl(_wave_bls[0]):
                        if isinstance(ev, dict) and "_wave_abort" in ev:
                            terminal_status = ev["_wave_abort"]
                            _aborted = True
                            break
                        yield ev
                    if _aborted:
                        return
                else:
                    # Concurrent intra-wave execution + deterministic BL-id-order
                    # barrier assembly. effective_concurrency caps fan-in at the
                    # smaller of wave size, the operator cap, and half the cores.
                    _eff = min(len(_wave_bls), wave_concurrency,
                               max(1, (os.cpu_count() or 2) // 2))
                    _by_id = {it.id: it for it in _wave_bls}
                    _bl_specs = [(it.id, (lambda _it=it: _one_bl(_it, concurrent=True)))
                                 for it in sorted(_wave_bls, key=lambda x: x.id)]

                    async def _assembler(bid, work_branch, _wi=_wi):
                        _acfg = repo_config_svc.load(repo_dir)
                        return await merge_branch_into_target(
                            repo_dir, work_branch, target_ref=_acfg.agent_branch)

                    async for _tag, _bid, _payload in _run_wave_concurrent(
                            _bl_specs, _assembler, _eff):
                        if _tag == "event":
                            yield _payload
                        elif _tag == "assembly":
                            yield _evt("bl.assembled", bl_id=_bid,
                                       ok=_payload.get("ok"), kind=_payload.get("kind"),
                                       merged_sha=_payload.get("merged_sha"),
                                       conflict_files=_payload.get("conflict_files"),
                                       error=_payload.get("error"))
                            if not _payload.get("ok"):
                                # No-abort: a conflict/error at assembly is surfaced
                                # (the BL's work survives on its work_branch) and
                                # rolled into the escalated roll-up; siblings already
                                # assembled stay on the trunk.
                                escalated_bls.append({"bl_id": _bid, "role": "assembly",
                                                      "reason": (f"{_bid} passed its per-BL gate but "
                                                                 f"could not assemble into "
                                                                 f"{repo_config_svc.load(repo_dir).agent_branch}: "
                                                                 f"{_payload.get('kind')} "
                                                                 f"{_payload.get('error') or ''}".strip())})
                                # I-5 truthful aggregation: the per-BL outcome was
                                # labelled from work_branch readiness BEFORE the
                                # assembly barrier ran; a conflict/error here means
                                # the BL did NOT reach the trunk, so reconcile its
                                # bl_outcomes entry (else an unassembled BL is
                                # mislabelled merged_* in the persisted roll-up).
                                _reconcile_unassembled_outcome(
                                    bl_outcomes_compact, _bid, _payload.get("kind"))
                                yield _evt("bl.escalated", bl_id=_bid, role="assembly",
                                           reason=(f"{_bid} could not assemble "
                                                   f"({_payload.get('kind')})"),
                                           conflict_files=_payload.get("conflict_files"))
                        elif _tag == "wave_done":
                            pass
                yield _evt("wave.done", wave=_wi)
                # Barrier reindex so the next dependent wave (and acceptance)
                # grounds on the just-assembled wave's merged code.
                async for e in _run_indexers(repo_dir, f"reindex_after_wave.{_wi}", reindex_incremental=reindex_incremental):
                    yield e
                _checkpoint(current_bl=None)  # A7
            terminal_status = "sprint_complete"
        else:
         for it in ordered:
            bl_id = it.id
            if not _reached_start_bl:
                if bl_id == start_bl:
                    _reached_start_bl = True
                else:
                    yield _evt("bl.skipped", bl_id=bl_id, reason=f"before start_bl={start_bl}")
                    continue
            # Wave-execution Phase 2: emit wave boundaries as the flattened order
            # crosses from one DAG layer to the next (only when the flag is on).
            if wave_execution and _wave_of:
                _wi = _wave_of.get(bl_id)
                if _wi != _prev_wave:
                    if _prev_wave is not None:
                        yield _evt("wave.done", wave=_prev_wave)
                        # Wave Phase 3: ONE reindex at the barrier (replaces the 2
                        # per-BL reindexes) so the next dependent wave grounds on
                        # the just-completed wave's merged code.
                        async for e in _run_indexers(repo_dir, f"reindex_after_wave.{_prev_wave}", reindex_incremental=reindex_incremental):
                            yield e
                    yield _evt("wave.start", wave=_wi,
                               bls=[i.id for i in _waves[_wi]])
                    _prev_wave = _wi
            _aborted = False
            async for ev in _one_bl(it):
                if isinstance(ev, dict) and "_wave_abort" in ev:
                    terminal_status = ev["_wave_abort"]
                    _aborted = True
                    break
                yield ev
            if _aborted:
                return

        # Wave-execution Phase 2: close the final wave once the loop drains.
        if wave_execution and _prev_wave is not None:
            yield _evt("wave.done", wave=_prev_wave)
            # Wave Phase 3: final barrier reindex so acceptance + pattern-profile
            # ground on the fully assembled feature.
            async for e in _run_indexers(repo_dir, f"reindex_after_wave.{_prev_wave}", reindex_incremental=reindex_incremental):
                yield e

        terminal_status = "sprint_complete"  # A7: flip from default "aborted"

        # ABL-0014 Item 2 (Batch C, 2026-06-01): UI-coverage breakdown.
        # Informational by default (min_ui_coverage_ratio=0.0). When the
        # operator sets a positive floor, a partial flag is added to the
        # sprint_complete event for downstream UI/log surfacing.
        coverage = {
            "merged_total": 0, "ui_bls": [], "backend_only": [],
            "ratio": 0.0, "evidence": {},
        }
        try:
            cfg_cov = repo_config_svc.load(repo_dir)
            merged_ids = [
                o["bl_id"] for o in bl_outcomes_compact
                if str(o.get("outcome", "")).startswith("merged")
            ]
            coverage = await _compute_ui_coverage(
                repo_dir,
                target_ref=cfg_cov.main_ref,
                agent_branch=cfg_cov.agent_branch,
                ui_globs=cfg_cov.effective_ui_globs(),
                merged_bl_ids=merged_ids,
            )
        except Exception as exc:  # noqa: BLE001 — informational; never abort
            yield _evt("coverage_check.error", run_id=run_id, error=str(exc))

        subtype = "full"
        if min_ui_coverage_ratio > 0.0 and coverage["merged_total"] > 0:
            if coverage["ratio"] < min_ui_coverage_ratio:
                subtype = "partial"

        yield _evt(
            "coverage_check",
            run_id=run_id,
            merged_total=coverage["merged_total"],
            ui_bls=coverage["ui_bls"],
            backend_only=coverage["backend_only"],
            ratio=round(coverage["ratio"], 4),
            threshold=min_ui_coverage_ratio,
            subtype=subtype,
        )

        yield _evt(
            "sprint_complete",
            summary=summary,
            coverage_subtype=subtype,
            ui_coverage_ratio=round(coverage["ratio"], 4),
            ui_coverage_threshold=min_ui_coverage_ratio,
            # ABL-0002 Stage 0: surface escalated/deferred BLs so dropped work is
            # reported, not silently lost from coverage math. Honest aggregation (I-5).
            escalated_bls=escalated_bls,
            deferred_bls=deferred_bls,
            bl_outcomes=bl_outcomes_compact,
        )

        # ABL-0019 Batch C: refresh the per-target Pattern Profile from the
        # eng_patterns.md files this sprint's engineers wrote, so the durable
        # conventions compound and search_patterns surfaces them on the NEXT
        # feature. Best-effort + off-thread (embeds via Ollama); a failure NEVER
        # perturbs the completed sprint.
        try:
            entries = await asyncio.to_thread(pattern_profile_svc.extract_patterns, repo_dir)
            if entries:
                await asyncio.to_thread(pattern_profile_svc.consolidate, repo_dir, entries=entries)
                n = await asyncio.to_thread(pattern_profile_svc.index_patterns, repo_dir, entries=entries)
                yield _evt("pattern_profile.refreshed", n_patterns=n, n_sources=len(entries))
        except Exception as exc:  # noqa: BLE001 — advisory; never perturb
            yield _evt("pattern_profile.refresh_error", error=str(exc))

        # ABL-0018 Stage 3: cross-target ("community") graduation. Now that this
        # sprint's lessons are sealed, re-run the recurrence pass across ALL
        # registered targets — a failure mode independently confirmed on ≥2
        # targets graduates into the shared global store, so the NEXT sprint on
        # ANY target inherits it (the mission's "carries forward across targets").
        # DORMANT BY DEFAULT (operator 2026-06-11): cross-target transfer must not
        # be used in any run, so the graduation write does not even fire unless
        # STAGE3_CROSS_TARGET=1 re-enables it. Best-effort + off-thread when on.
        if global_lessons_svc.enabled():
            try:
                graduated = await asyncio.to_thread(global_lessons_svc.graduate_all)
                if graduated:
                    yield _evt("global_lessons.graduated", n=len(graduated),
                               targets=sorted({t for g in graduated for t in g.origin_targets}))
            except Exception as exc:  # noqa: BLE001 — advisory; never perturb
                yield _evt("global_lessons.graduation_error", error=str(exc))

        # ABL-0014: acceptance pass — runs AFTER sprint_complete and BEFORE
        # doctrine_meta + closure_check. Advisory only (§E.1 Q3): exceptions
        # are surfaced as acceptance.error and never abort the sprint.
        # Default off until §E.1 Q6 calibration (3 smoke runs) flips it on.
        if contract_first:
            # Contract-First Phase D: bind the assembled slices (stub->real DI +
            # aggregator) and prove the composed solution builds, BEFORE acceptance.
            async for _be in _contract_bind(repo_dir, repo_name, run_id=run_id,
                                            feature_slug=feature_slug,
                                            timeout=timeout_per_role):
                yield _be
        if run_acceptance:
            # ── Live-acceptance convergence loop (PROPOSAL_LIVE_ACCEPTANCE_LOOP) ──
            # The customer-acceptance standard: boot the WHOLE app, exercise every
            # AC live; if acceptance finds defects it dispatches follow-up
            # engineer(s) (R17), and we RE-BOOT + RE-EXERCISE until acceptance
            # accepts every criterion live (integrity_ok) — or, after exhausting
            # rounds / when no actionable fix can be dispatched, escalate honestly
            # (no-abort: never a silent clean, never a routine give-up).
            accepted = False
            last_round_done: dict | None = None
            for accept_round in range(1, ACCEPTANCE_LOOP_MAX_ROUNDS + 1):
                if accept_round > 1:
                    yield _evt("acceptance.loop.reround", run_id=run_id,
                               round=accept_round,
                               max_rounds=ACCEPTANCE_LOOP_MAX_ROUNDS,
                               reason="prior round dispatched fix(es) — re-booting the "
                                      "live app to re-exercise every criterion")
                # Fresh trace per round (round-tagged task_id). A64: one TraceWriter
                # shared by the regression checkpoint AND the acceptance flow so both
                # seal into one co-located phase_events.jsonl.
                acceptance_trace = TraceWriter(
                    repo=repo_name, role="acceptance",
                    task_id=(run_id if accept_round == 1 else f"{run_id}-r{accept_round}"))
                # The ONE full-suite regression checkpoint (re-run each round so a
                # fix's collateral regressions are caught before re-accept).
                if run_base_sha:
                    try:
                        _accfg = repo_config_svc.load(repo_dir)
                        rc = await regression_gate_svc.run_gate(
                            repo_dir, agent_branch=_accfg.agent_branch,
                            target_ref=run_base_sha, run_id=run_id)
                        rc_evt = _evt("regression_checkpoint",
                                      round=accept_round,
                                      ok=rc.get("ok"), kind=rc.get("kind"),
                                      reason=rc.get("reason"),
                                      regressions=(rc.get("regressions") or [])[:50],
                                      failing_tests=(rc.get("failing_tests") or [])[:50])
                        try:
                            acceptance_trace.write_phase_event(rc_evt)
                        except Exception:  # noqa: BLE001
                            pass
                        yield rc_evt
                    except Exception as exc:  # noqa: BLE001
                        yield _evt("regression_checkpoint.error", error=str(exc))
                round_done: dict | None = None
                try:
                    async for evt in _acceptance_flow(
                        repo_dir,
                        repo_name,
                        run_id,
                        feature_slug,
                        timeout=acceptance_timeout,
                        inject_acceptance_priors=inject_acceptance_priors,
                        retrieval_kwargs_builder=retrieval_kwargs_builder,
                        run_acceptance_followup=run_acceptance_followup,
                        accept_round=accept_round,
                        trace=acceptance_trace,
                    ):
                        if isinstance(evt, dict) and evt.get("phase") == "orchestrator.acceptance.done":
                            round_done = evt
                        yield evt
                except Exception as exc:
                    yield _evt("acceptance.error", round=accept_round, error=str(exc))
                    break
                last_round_done = round_done or last_round_done
                decision = _acceptance_loop_next(
                    round_done, accept_round, ACCEPTANCE_LOOP_MAX_ROUNDS)
                dispatched = int((round_done or {}).get("dispatched_count", 0) or 0)
                if decision == "accept":
                    accepted = True
                    yield _evt("acceptance.loop.accepted", run_id=run_id,
                               round=accept_round,
                               reason="every acceptance criterion live-verified against the "
                                      "booted app with evidence; zero open failures")
                    break
                if decision == "reround":
                    yield _evt("acceptance.loop.progress", run_id=run_id,
                               round=accept_round, dispatched=dispatched,
                               reason="fix(es) dispatched+merged — will re-boot and re-verify")
                    continue
                # decision == "escalate": rounds exhausted OR nothing actionable.
                exhausted = accept_round >= ACCEPTANCE_LOOP_MAX_ROUNDS
                yield _evt("acceptance.loop.escalated", run_id=run_id,
                           round=accept_round, integrity_ok=False,
                           rounds_used=accept_round,
                           max_rounds=ACCEPTANCE_LOOP_MAX_ROUNDS,
                           unverified_criteria=(round_done or {}).get("unverified_criteria", []),
                           open_failures=(round_done or {}).get("open_failures", []),
                           dispatched_last_round=dispatched,
                           reason=("exhausted acceptance rounds without a live-clean accept — "
                                   "escalating with dossier (no-abort: not a silent clean)"
                                   if exhausted else
                                   "remaining failures/unverified criteria have no actionable "
                                   "auto-fix (nothing eligible to dispatch) — a senior engineer "
                                   "would also be blocked; escalating with dossier"))
                break

        # B-3 / I-7: spawn the doctrine-meta-agent against this sprint's
        # archived traces. Runs ONLY after sprint_complete (a partial sprint
        # has no completed-pattern to mine). Archive traces NOW so the meta
        # agent can read them; _archive_traces_since is idempotent so the
        # finally-block call below becomes a no-op for already-moved dirs.
        if run_doctrine_meta:
            try:
                _archive_traces_since(repo_name, run_started_at, run_id)
            except Exception:
                pass
            try:
                async for evt in _doctrine_meta_flow(repo_name, run_id, timeout=timeout_per_role):
                    yield evt
            except Exception as exc:
                yield _evt("doctrine_meta.error", error=str(exc))

        # M2-3 / I-3: closure_check fires AFTER sprint_complete (and after
        # doctrine_meta when enabled). Yields one orchestrator.closure_violation
        # event per resource that survived past its intended scope; emits
        # closure_check.summary at the end. Lives INSIDE the try block (not in
        # finally) because yielding from an async generator's finally during
        # aclose() is illegal — PEP 525, see B15 comment below. This means
        # aborted paths currently don't surface violations live; a future
        # startup-scan pattern (M2-3b) can read disk state and report at the
        # next run's start.
        try:
            yield _evt("closure_check.start", run_id=run_id)
            violations = await closure_check_svc.scan_all(repo_dir, run_id)
            for v in violations:
                yield _evt("closure_violation", kind=v.kind, resource=v.resource,
                           detail=v.detail, run_id=run_id)
            yield _evt("closure_check.done",
                       violation_count=len(violations),
                       by_kind={k: sum(1 for v in violations if v.kind == k)
                                for k in {v.kind for v in violations}})
        except Exception as exc:
            yield _evt("closure_check.error", error=str(exc))
    except Exception as exc:  # noqa: BLE001
        # #3 wedge-proof backstop: any exception that escaped the sprint body
        # before sprint_complete MUST still produce a terminal event. The outer
        # try previously had ONLY a finally — and an async generator cannot
        # yield from finally during aclose() (PEP 525) — so an unhandled raise
        # propagated out of run() and the SSE stream ended with NO terminal
        # event: the 0-procs-no-terminal wedge that only the End-Sprint button
        # could clear (BL-0006, search_and_discovery_2, 2026-06-04). Emit
        # `aborted` here so the stream always terminates cleanly. terminal_status
        # stays "aborted" (its default) so the A7 disk-state move tags the run
        # correctly. We deliberately do NOT re-raise — the structured terminal
        # event IS the contract; re-raising would break the very stream we just
        # guaranteed. CancelledError/GeneratorExit are BaseException → not
        # caught → consumer-disconnect / End-Sprint cancellation still propagate.
        yield _evt("aborted",
                   reason=f"unhandled orchestrator error: {type(exc).__name__}: {exc}"[:600],
                   error_type=type(exc).__name__)
    finally:
        # A49 fix #2: drop this run's same-SHA green memory (process-local,
        # run-scoped) so it can't leak across runs.
        try:
            regression_gate_svc.clear_green_shas(run_id)
        except Exception:
            pass
        # A7: move the disk state file into done/ tagged with how the run ended.
        try:
            run_state_svc.mark_terminated(run_id, terminal_status)
        except Exception:
            pass
        # B15: archive any traces this run produced (clean exit OR aborted OR
        # consumer disconnect). Silently best-effort — yielding from an async
        # generator's finally during aclose() is illegal (PEP 525), so we
        # never try; operators inspect traces_archive/<run_id>/ directly.
        try:
            _archive_traces_since(repo_name, run_started_at, run_id)
        except Exception:
            pass


# ───────────────────── Contract-First Phase 1 (R22) ─────────────────────
# PROPOSAL_CONTRACT_FIRST_DECOMPOSITION.md. Decision A: the PO authors a raw
# OpenAPI 3.1 contract (HTTP seam, B1). Decision (c): the Engineer-as-
# materializer turns it into compilable C# stubs. The R22 gate below is the
# load-bearing guarantee (the agent-based path trades a tool's byte-determinism
# for "compiles + conforms"): structural contract validation + per-operation
# conformance + a real `dotnet build`, driving a no-abort fix loop.


async def _dotnet_build(wt_path: "Path", project: str | None = None, timeout: int = 600) -> dict:
    """Run `dotnet build` (targeting the solution/project when known) in the
    worktree. R22's 'stubs compile' proof."""
    cmd = ["dotnet", "build"] + ([project] if project else []) + ["--nologo"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(wt_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError:
        return {"ok": False, "kind": "no_dotnet", "tail": "dotnet not on PATH"}
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return {"ok": False, "kind": "timeout", "tail": f"dotnet build exceeded {timeout}s"}
    text = out.decode("utf-8", "replace") if out else ""
    ok = proc.returncode == 0
    return {"ok": ok, "kind": "build" if ok else "build_failed",
            "returncode": proc.returncode, "tail": "\n".join(text.splitlines()[-30:])}


async def _changed_cs_corpus(wt_path: "Path", base_ref: str) -> str:
    """Concatenate the C# files the materializer added/changed vs base_ref —
    the corpus the R22 conformance check scans (not the whole repo)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "diff", "--name-only", f"{base_ref}...HEAD",
            cwd=str(wt_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await proc.communicate()
    except Exception:
        return ""
    parts: list[str] = []
    for rel in out.decode("utf-8", "replace").splitlines():
        if not rel.endswith(".cs"):
            continue
        p = wt_path / rel
        if p.exists():
            try:
                parts.append(p.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
    return "\n".join(parts)


def _is_dotnet_target(repo_dir: "Path") -> bool:
    """True when the target looks like a .NET/C# repo (a `.sln` or `.csproj` exists at
    the root, an immediate subdir, or one level deeper, e.g. `backend/<Proj>/<Proj>.csproj`).
    Contract-First (default ON) only engages on .NET targets — its materializer emits C#
    stubs and the R22 gate runs `dotnet build`; on any other stack it is forced OFF."""
    try:
        cands = [repo_dir] + [p for p in sorted(repo_dir.iterdir())
                              if p.is_dir() and p.name not in {".git", "node_modules", "bin", "obj"}]
    except OSError:
        return False
    for d in cands[:25]:
        if next(d.glob("*.sln"), None) or next(d.glob("*.csproj"), None):
            return True
        try:
            for sub in sorted(d.iterdir()):
                if sub.is_dir() and next(sub.glob("*.csproj"), None):
                    return True
        except OSError:
            pass
    return False


def _build_target(cfg, wt_path: "Path"):
    """The solution/project `dotnet build` should target. Prefer a .sln/.csproj
    named in the repo's test_cmd; else a shallow search; else None (bare build)."""
    tc = getattr(cfg, "test_cmd", None) or []
    for tok in tc:
        if isinstance(tok, str) and (tok.endswith(".sln") or tok.endswith(".csproj")):
            return tok
    try:
        cands = [wt_path] + [p for p in sorted(wt_path.iterdir())
                             if p.is_dir() and p.name not in {".git", "node_modules", "bin", "obj"}]
    except OSError:
        cands = [wt_path]
    for d in cands[:25]:
        for sln in sorted(d.glob("*.sln")):
            return str(sln.relative_to(wt_path))
    return None


async def _r22_gate(wt_path: "Path", base_ref: str, spec_text: str, timeout: int,
                    project: str | None = None) -> dict:
    """R22 gate: structural contract validation + per-operation conformance of
    the generated stubs + a real `dotnet build`. ok only when all three pass."""
    from app.services import contract as contract_svc
    stub_text = await _changed_cs_corpus(wt_path, base_ref)
    rep = contract_svc.contract_report(spec_text, stub_text)
    build = await _dotnet_build(wt_path, project=project, timeout=timeout)
    return {
        "ok": bool(rep["ok"] and build["ok"]),
        "validation_errors": rep["validation_errors"],
        "unconformant": rep["unconformant"],
        "build_ok": build["ok"],
        "build_kind": build["kind"],
        "build_tail": build.get("tail", ""),
    }


def _r22_fix_prompt(gate: dict) -> str:
    parts = ["The R22 contract-materialization gate FAILED. Root-cause and fix, then commit a NEW commit:"]
    if not gate.get("build_ok"):
        parts.append(
            f"- `dotnet build` FAILED ({gate.get('build_kind')}). Compile-error tail:\n"
            f"{gate.get('build_tail', '')}\nFix EVERY compile error so the solution builds."
        )
    if gate.get("unconformant"):
        parts.append(
            "- These contract operations are NOT represented in your stubs — add a stub "
            "referencing each (by operationId, or its route path): "
            + "; ".join(gate["unconformant"])
        )
    if gate.get("validation_errors"):
        parts.append("- Contract structural errors: " + "; ".join(gate["validation_errors"]))
    parts.append("Additive stubs only — no business logic, no behavior changes, no test changes.")
    return "\n".join(parts)


async def _changed_cs_files(wt_path: "Path", base_ref: str) -> dict:
    """Map {relpath: text} for the C# files added/changed vs base_ref — the feature
    corpus the Phase-D binder composes (keyed variant of _changed_cs_corpus)."""
    files: dict = {}
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "diff", "--name-only", f"{base_ref}...HEAD", cwd=str(wt_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await proc.communicate()
    except Exception:
        return files
    for rel in out.decode("utf-8", "replace").splitlines():
        if not rel.endswith(".cs"):
            continue
        p = wt_path / rel
        if p.exists():
            try:
                files[rel] = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
    return files


async def _contract_bind(repo_dir: "Path", repo_name: str, *, run_id: str | None = None,
                         feature_slug: str | None = None, timeout: int = 900):
    """Contract-First Phase D — barrier BINDING (Option A: per-slice DI module +
    binder composes). After all slices are assembled on agent_branch, compose the
    final DI wiring: prefer each interface's REAL module over its stub, drop the
    superseded stub modules, regenerate the composition aggregator, and prove the
    assembly with a real `dotnet build`. No-abort: any conflict / build failure
    surfaces orchestrator.contract_bind.escalated (siblings stay merged; trunk
    deterministic). Only invoked when contract_first=True (else byte-identical)."""
    from app.services import contract_bind as bind_svc
    import subprocess
    cfg = repo_config_svc.load(repo_dir)
    yield _evt("contract_bind.start")
    wt = None
    try:
        wt = await create_worktree(repo_dir, base_ref=cfg.agent_branch)
        files = await _changed_cs_files(wt.path, cfg.main_ref)
        if not any("@contract-module" in (t or "") for t in files.values()):
            yield _evt("contract_bind.skipped",
                       reason="no @contract-module DI modules in the feature corpus")
            return
        res = bind_svc.compute_binding(files)
        if not res["ok"]:
            yield _evt("contract_bind.escalated", reason="binding plan has conflicts",
                       conflicts=res["conflicts"])
            return
        for rel in res["drop_paths"]:
            try:
                (wt.path / rel).unlink()
            except OSError:
                pass
        (wt.path / res["aggregator_path"]).write_text(res["new_aggregator_text"],
                                                       encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(wt.path), capture_output=True)
        subprocess.run(["git", "commit", "-m",
                        "bind(contract-first): compose real DI modules + drop superseded stubs"],
                       cwd=str(wt.path), capture_output=True)
        build_target = _build_target(cfg, wt.path)
        build = await _dotnet_build(wt.path, project=build_target, timeout=timeout)
        if not build["ok"]:
            yield _evt("contract_bind.escalated",
                       reason="assembled solution failed dotnet build",
                       build_kind=build["kind"], build_tail=build.get("tail", ""),
                       chosen=res["chosen"])
            return
        merge = await fast_forward_target(repo_dir, wt.branch, target_ref=cfg.agent_branch)
        if not merge.get("ok"):
            await asyncio.sleep(2)
            merge = await fast_forward_target(repo_dir, wt.branch, target_ref=cfg.agent_branch)
        if not merge.get("ok"):
            yield _evt("contract_bind.escalated",
                       reason=f"bind merge failed: {merge.get('kind')}", error=merge.get("error"))
            return
        yield _evt("contract_bind.done", ok=True, chosen=res["chosen"],
                   dropped=res["drop_paths"], method_calls=res["method_calls"])
    finally:
        if wt is not None:
            try:
                await remove_worktree(repo_dir, wt)
            except Exception:
                pass


async def _contract_flow(repo_dir: "Path", repo_name: str, *, run_id: str | None = None,
                         feature_slug: str | None = None, timeout: int = 900,
                         retrieval_kwargs_builder=None):
    """Contract-First Phase 1 (R22, decision c). Read the PO-authored OpenAPI 3.1
    contract; spawn the Engineer-as-materializer to write compilable C# stubs;
    run the R22 gate in a no-abort loop until it is green; FF-merge to
    agent_branch. Emits orchestrator.contract.{start,skipped,materialized,done,
    escalated}. Only invoked when contract_first=True (else byte-identical)."""
    from app.services import contract as contract_svc
    cfg = repo_config_svc.load(repo_dir)
    family = cfg.doctrine or prompts_svc.select_family(classify_target(repo_dir))
    art = repo_dir / feature_artifact_dir(repo_dir, feature_slug)
    contract_path = art / "contract" / "openapi.yaml"
    yield _evt("contract.start", contract=str(contract_path))

    if not contract_path.exists():
        # contract_first is opt-in; a PO that authored no contract has nothing to
        # materialize. Non-fatal skip (Phase 1 does not force every feature to
        # carry an HTTP contract).
        yield _evt("contract.skipped", reason="no contract/openapi.yaml authored by PO")
        return

    spec_text = contract_path.read_text(encoding="utf-8")
    pre = contract_svc.contract_report(spec_text)
    if not pre["ok"]:
        yield _evt("contract.escalated", reason="contract failed structural validation",
                   validation_errors=pre["validation_errors"])
        return

    prompt = prompts_svc.build_stub_materializer(family, spec_text, repo_dir, feature_slug=feature_slug)
    wt = None
    trace = None
    try:
        wt = await create_worktree(repo_dir, base_ref=cfg.agent_branch)
        trace = TraceWriter(repo=repo_name, role="engineer", task_id=wt.task_id)
        yield _ptag({"type": "_meta", "phase": "worktree_ready", "task_id": wt.task_id,
                    "branch": wt.branch, "role": "contract", "trace_dir": str(trace.dir)},
                   "contract", trace=trace)
        rk = retrieval_kwargs_builder(wt, "engineer", None, trace)
        build_target = _build_target(cfg, wt.path)
        async for ev in stream_agent_task(prompt, wt.path, timeout_seconds=timeout,
                                          trace=trace, min_pregrounding=3, **rk):
            yield _tag(ev, "contract")

        gate = await _r22_gate(wt.path, cfg.agent_branch, spec_text, timeout, project=build_target)
        yield _ptag({"type": "_meta", "phase": "contract_gate", **gate}, "contract", trace=trace)
        attempt = 0
        while not gate["ok"] and attempt < MAX_FIX_ATTEMPTS:
            attempt += 1
            fix = _r22_fix_prompt(gate)
            async for ev in stream_agent_task(fix, wt.path, timeout_seconds=max(300, timeout // 2),
                                              trace=trace, **rk):
                yield _tag(ev, "contract")
            gate = await _r22_gate(wt.path, cfg.agent_branch, spec_text, timeout, project=build_target)
            yield _ptag({"type": "_meta", "phase": "contract_gate", "attempt": attempt, **gate},
                       "contract", trace=trace)

        if not gate["ok"]:
            yield _evt("contract.escalated", reason="R22 gate not green after fixes",
                       validation_errors=gate["validation_errors"],
                       unconformant=gate["unconformant"], build_ok=gate["build_ok"])
            return

        merge = await fast_forward_target(repo_dir, wt.branch, target_ref=cfg.agent_branch)
        if not merge.get("ok") and merge.get("kind") == "error":
            await asyncio.sleep(2)
            merge = await fast_forward_target(repo_dir, wt.branch, target_ref=cfg.agent_branch)
        if not merge.get("ok"):
            yield _evt("contract.escalated", reason=f"stub merge failed: {merge.get('kind')}",
                       error=merge.get("error"))
            return

        yield _evt("contract.materialized", branch=wt.branch)
        yield _evt("contract.done", ok=True)
    finally:
        if wt is not None:
            await remove_worktree(repo_dir, wt)
