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
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from app.services import backlog as backlog_svc
from app.services import doctrine_validator as doctrine_svc
from app.services import prompts as prompts_svc
from app.services import regression_gate as regression_gate_svc
from app.services import repo_config as repo_config_svc
from app.services.brownfield import classify_target
from app.services.claude_agent import stream_agent_task
from app.services.git_worktree import (
    Worktree,
    create_worktree,
    fast_forward_target,
    get_commit_sha,
    has_new_commits,
    remove_worktree,
)
from app.services.indexing import run_claude_context_index, run_graphify_update
from app.services.traces import TraceWriter


# ─── helpers ───────────────────────────────────────────────────────────────


def _evt(phase: str, **kwargs) -> dict:
    """Construct an orchestrator-tagged SSE event dict."""
    e = {"type": "_meta", "phase": f"orchestrator.{phase}"}
    e.update(kwargs)
    return e


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


async def _run_indexers(repo_dir: Path, label: str) -> AsyncIterator[dict]:
    """Run claude-context + graphify, in parallel. Incremental by provider design."""
    yield _evt(f"{label}.start")
    cc_task = asyncio.create_task(run_claude_context_index(repo_dir))
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
) -> AsyncIterator[dict]:
    cfg = repo_config_svc.load(repo_dir)
    family = cfg.doctrine or prompts_svc.select_family(classify_target(repo_dir))
    prompt = prompts_svc.build_po(family, brief, project_name, repo_dir)
    wt: Worktree | None = None
    trace: TraceWriter | None = None
    try:
        wt = await create_worktree(repo_dir, base_ref=cfg.agent_branch)
        trace = TraceWriter(repo=repo_name, role="po", task_id=wt.task_id)
        yield _tag({"type": "_meta", "phase": "worktree_ready", "task_id": wt.task_id,
                    "branch": wt.branch, "role": "po", "trace_dir": str(trace.dir)}, "po")
        rk = retrieval_kwargs_builder(wt, "po", None, trace)
        async for event in stream_agent_task(prompt, wt.path, timeout_seconds=timeout, trace=trace, **rk):
            yield _tag(event, "po")
        # doctrine
        validation = doctrine_svc.validate_po(wt.path)
        attempt = 0
        while not validation["ok"] and attempt < 2:
            attempt += 1
            yield _tag({"type": "_meta", "phase": "doctrine_check", "kind": "incomplete",
                        "attempt": attempt, **validation}, "po")
            fix = doctrine_svc.build_fix_prompt("po", validation)
            async for event in stream_agent_task(fix, wt.path, timeout_seconds=max(300, timeout // 2),
                                                  trace=trace, **rk):
                yield _tag(event, "po")
            validation = doctrine_svc.validate_po(wt.path)
        yield _tag({"type": "_meta", "phase": "doctrine_check",
                    "kind": "complete" if validation["ok"] else "give_up",
                    "attempts": attempt, "summary": validation["summary"]}, "po")
        # import artifacts back to repo if doctrine passed
        if validation["ok"]:
            from shutil import copy2, copytree
            import shutil, subprocess
            src_bl = wt.path / ".agile-v" / "BACKLOG.md"
            if src_bl.exists():
                dst_bl = repo_dir / ".agile-v" / "BACKLOG.md"
                dst_bl.parent.mkdir(parents=True, exist_ok=True)
                copy2(src_bl, dst_bl)
            from app.services.brownfield import pick_artifact_dir
            art = pick_artifact_dir(wt.path)
            src_bf = wt.path / art
            if src_bf.exists():
                dst_bf = repo_dir / art
                if dst_bf.exists():
                    shutil.rmtree(dst_bf)
                copytree(src_bf, dst_bf)
            subprocess.run(["git", "add", ".agile-v/", art + "/"], cwd=repo_dir, check=False)
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


async def _engineer_flow(
    repo_dir: Path,
    repo_name: str,
    bl_id: str,
    timeout: int,
    retrieval_kwargs_builder,
) -> AsyncIterator[dict]:
    cfg = repo_config_svc.load(repo_dir)
    family = cfg.doctrine or prompts_svc.select_family(classify_target(repo_dir))
    bf = backlog_svc.find_backlog(repo_dir)
    section = backlog_svc.extract_section(bf.read_text(encoding="utf-8"), bl_id)
    prompt = prompts_svc.build_engineer(family, bl_id, section, repo_dir)

    wt: Worktree | None = None
    trace: TraceWriter | None = None
    merged = False
    no_op = False
    try:
        wt = await create_worktree(repo_dir, base_ref=cfg.agent_branch)
        trace = TraceWriter(repo=repo_name, role="engineer", bl_id=bl_id, task_id=wt.task_id)
        yield _tag({"type": "_meta", "phase": "worktree_ready", "task_id": wt.task_id,
                    "branch": wt.branch, "bl_id": bl_id, "role": "engineer",
                    "trace_dir": str(trace.dir)}, "engineer", bl_id)
        rk = retrieval_kwargs_builder(wt, "engineer", bl_id, trace)
        async for event in stream_agent_task(prompt, wt.path, timeout_seconds=timeout,
                                              trace=trace, min_pregrounding=3, **rk):
            yield _tag(event, "engineer", bl_id)

        validation = doctrine_svc.validate_engineer(wt.path, bl_id, base_ref=cfg.agent_branch,
                                                    retrieval_log=trace.retrieval_path)
        if validation.get("no_op"):
            yield _tag({"type": "_meta", "phase": "no_op", "bl_id": bl_id,
                        "summary": validation["summary"]}, "engineer", bl_id)
            no_op = True
            yield {"_orchestrator_outcome": True, "role": "engineer", "bl_id": bl_id,
                   "merged": False, "no_op": True}
            return
        # doctrine retries
        attempt = 0
        while not validation["ok"] and attempt < 2:
            attempt += 1
            yield _tag({"type": "_meta", "phase": "doctrine_check", "kind": "incomplete",
                        "attempt": attempt, **validation}, "engineer", bl_id)
            fix = doctrine_svc.build_fix_prompt("engineer", validation, bl_id=bl_id)
            async for event in stream_agent_task(fix, wt.path, timeout_seconds=max(300, timeout // 2),
                                                  trace=trace, **rk):
                yield _tag(event, "engineer", bl_id)
            validation = doctrine_svc.validate_engineer(wt.path, bl_id, base_ref=cfg.agent_branch,
                                                        retrieval_log=trace.retrieval_path)
        yield _tag({"type": "_meta", "phase": "doctrine_check",
                    "kind": "complete" if validation["ok"] else "give_up",
                    "attempts": attempt, "summary": validation["summary"]}, "engineer", bl_id)

        new_commits = await has_new_commits(wt, base_ref="HEAD~1")
        if validation["ok"] and new_commits > 0:
            gate = await regression_gate_svc.run_gate(repo_dir, agent_branch=wt.branch,
                                                     target_ref=cfg.agent_branch)
            yield _tag({"type": "_meta", "phase": "regression_gate",
                        **{k: gate.get(k) for k in ("ok", "kind", "regressions", "reason", "post_tail")}},
                       "engineer", bl_id)
            gate_attempt = 0
            while not gate.get("ok") and gate.get("kind") == "regressed" and gate_attempt < 2:
                gate_attempt += 1
                fix = doctrine_svc.build_gate_fix_prompt("engineer", gate, bl_id=bl_id,
                                                         attempt=gate_attempt, max_attempts=2)
                async for event in stream_agent_task(fix, wt.path,
                                                      timeout_seconds=max(300, timeout // 2),
                                                      trace=trace, **rk):
                    yield _tag(event, "engineer", bl_id)
                validation = doctrine_svc.validate_engineer(wt.path, bl_id,
                                                            base_ref=cfg.agent_branch,
                                                            retrieval_log=trace.retrieval_path)
                if not validation["ok"]:
                    break
                gate = await regression_gate_svc.run_gate(repo_dir, agent_branch=wt.branch,
                                                         target_ref=cfg.agent_branch)
                yield _tag({"type": "_meta", "phase": "regression_gate",
                            "gate_attempt": gate_attempt,
                            **{k: gate.get(k) for k in ("ok", "kind", "regressions", "reason", "post_tail")}},
                           "engineer", bl_id)
            if validation["ok"] and gate.get("ok"):
                merge = await fast_forward_target(repo_dir, wt.branch, target_ref=cfg.agent_branch)
                # If transient (lock race, etc.), one retry with a short sleep
                # before falling through to awaiting_review.
                if not merge.get("ok") and merge.get("kind") == "error":
                    await asyncio.sleep(2)
                    merge_retry = await fast_forward_target(repo_dir, wt.branch, target_ref=cfg.agent_branch)
                    if merge_retry.get("ok"):
                        merge = merge_retry
                merged = bool(merge.get("ok"))
                yield _tag({"type": "_meta", "phase": "merge_to_target",
                            "ok": merge.get("ok"), "merged_sha": merge.get("merged_sha"),
                            "kind": merge.get("kind"), "error": merge.get("error"),
                            "branch": wt.branch},
                           "engineer", bl_id)
            else:
                yield _tag({"type": "_meta", "phase": "awaiting_review",
                            "reason": gate.get("reason") or "doctrine incomplete"},
                           "engineer", bl_id)
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
) -> AsyncIterator[dict]:
    cfg = repo_config_svc.load(repo_dir)
    family = cfg.doctrine or prompts_svc.select_family(classify_target(repo_dir))
    bf = backlog_svc.find_backlog(repo_dir)
    section = backlog_svc.extract_section(bf.read_text(encoding="utf-8"), bl_id)
    if role == "qa":
        prompt = prompts_svc.build_qa(family, bl_id, section, repo_dir)
    else:
        prompt = prompts_svc.build_score(family, bl_id, section, repo_dir)

    wt: Worktree | None = None
    trace: TraceWriter | None = None
    merged = False
    try:
        wt = await create_worktree(repo_dir, base_ref=cfg.agent_branch)
        trace = TraceWriter(repo=repo_name, role=role, bl_id=bl_id, task_id=wt.task_id)
        yield _tag({"type": "_meta", "phase": "worktree_ready", "task_id": wt.task_id,
                    "branch": wt.branch, "bl_id": bl_id, "role": role,
                    "trace_dir": str(trace.dir)}, role, bl_id)
        rk = retrieval_kwargs_builder(wt, role, bl_id, trace)
        pregrounding = 3 if role == "qa" else 0
        async for event in stream_agent_task(prompt, wt.path, timeout_seconds=timeout,
                                              trace=trace, min_pregrounding=pregrounding, **rk):
            yield _tag(event, role, bl_id)

        if role == "qa":
            validation = doctrine_svc.validate_qa(wt.path, bl_id, base_ref=cfg.agent_branch,
                                                  retrieval_log=trace.retrieval_path)
        else:
            validation = doctrine_svc.validate_scorer(wt.path, bl_id, base_ref=cfg.agent_branch,
                                                     retrieval_log=trace.retrieval_path)
        attempt = 0
        while not validation["ok"] and attempt < 2:
            attempt += 1
            yield _tag({"type": "_meta", "phase": "doctrine_check", "kind": "incomplete",
                        "attempt": attempt, **validation}, role, bl_id)
            fix = doctrine_svc.build_fix_prompt(role, validation, bl_id=bl_id)
            async for event in stream_agent_task(fix, wt.path, timeout_seconds=max(300, timeout // 2),
                                                  trace=trace, **rk):
                yield _tag(event, role, bl_id)
            if role == "qa":
                validation = doctrine_svc.validate_qa(wt.path, bl_id, base_ref=cfg.agent_branch,
                                                      retrieval_log=trace.retrieval_path)
            else:
                validation = doctrine_svc.validate_scorer(wt.path, bl_id, base_ref=cfg.agent_branch,
                                                         retrieval_log=trace.retrieval_path)
        yield _tag({"type": "_meta", "phase": "doctrine_check",
                    "kind": "complete" if validation["ok"] else "give_up",
                    "attempts": attempt, "summary": validation["summary"]}, role, bl_id)

        new_commits = await has_new_commits(wt, base_ref="HEAD~1")
        if role == "qa" and validation["ok"] and new_commits > 0:
            gate = await regression_gate_svc.run_gate(repo_dir, agent_branch=wt.branch,
                                                     target_ref=cfg.agent_branch)
            yield _tag({"type": "_meta", "phase": "regression_gate",
                        **{k: gate.get(k) for k in ("ok", "kind", "regressions", "reason", "post_tail")}},
                       role, bl_id)
            gate_attempt = 0
            while not gate.get("ok") and gate.get("kind") == "regressed" and gate_attempt < 2:
                gate_attempt += 1
                fix = doctrine_svc.build_gate_fix_prompt("qa", gate, bl_id=bl_id,
                                                         attempt=gate_attempt, max_attempts=2)
                async for event in stream_agent_task(fix, wt.path,
                                                      timeout_seconds=max(300, timeout // 2),
                                                      trace=trace, **rk):
                    yield _tag(event, role, bl_id)
                validation = doctrine_svc.validate_qa(wt.path, bl_id, base_ref=cfg.agent_branch,
                                                      retrieval_log=trace.retrieval_path)
                if not validation["ok"]:
                    break
                gate = await regression_gate_svc.run_gate(repo_dir, agent_branch=wt.branch,
                                                         target_ref=cfg.agent_branch)
                yield _tag({"type": "_meta", "phase": "regression_gate",
                            "gate_attempt": gate_attempt,
                            **{k: gate.get(k) for k in ("ok", "kind", "regressions", "reason", "post_tail")}},
                           role, bl_id)
            if validation["ok"] and gate.get("ok"):
                merge = await fast_forward_target(repo_dir, wt.branch, target_ref=cfg.agent_branch)
                if not merge.get("ok") and merge.get("kind") == "error":
                    await asyncio.sleep(2)
                    merge_retry = await fast_forward_target(repo_dir, wt.branch, target_ref=cfg.agent_branch)
                    if merge_retry.get("ok"):
                        merge = merge_retry
                merged = bool(merge.get("ok"))
                yield _tag({"type": "_meta", "phase": "merge_to_target",
                            "ok": merge.get("ok"), "merged_sha": merge.get("merged_sha"),
                            "kind": merge.get("kind"), "error": merge.get("error"),
                            "branch": wt.branch},
                           role, bl_id)
            else:
                yield _tag({"type": "_meta", "phase": "awaiting_review",
                            "reason": gate.get("reason")}, role, bl_id)
        yield {"_orchestrator_outcome": True, "role": role, "bl_id": bl_id,
               "merged": merged, "doctrine_ok": validation["ok"],
               # A2: surface doctrine summary so the per-BL loop can emit
               # qa_doctrine_failed with diagnostic detail.
               "doctrine_summary": validation.get("summary")}
    finally:
        if trace is not None:
            trace.close()
        if wt is not None:
            try:
                await remove_worktree(repo_dir, wt)
            except Exception:
                pass


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

    # B15: tag this run for trace archival on exit (any path: complete or aborted).
    run_started_at = datetime.now(timezone.utc)
    run_id = f"run-{run_started_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"

    yield _evt("start", brief_chars=len(brief), project_name=project_name, run_id=run_id)

    try:
        # ── Step 2-3: initial indexing ─────────────────────────────────────────
        async for e in _run_indexers(repo_dir, "index_initial"):
            yield e

        # ── Step 4: PO ─────────────────────────────────────────────────────────
        po_ok = True
        if not skip_po:
            yield _evt("po.start")
            async for e in _po_flow(repo_dir, repo_name, brief, project_name,
                                    timeout_per_role, retrieval_kwargs_builder):
                if "_orchestrator_outcome" in e:
                    summary["po"] = e
                    po_ok = e.get("doctrine_ok", False)
                    continue
                yield e
            yield _evt("po.done", ok=po_ok)
            if not po_ok and stop_on_failure:
                yield _evt("aborted", reason="PO doctrine failed")
                return

        # ── Step 4 cont: parse backlog ─────────────────────────────────────────
        bf = backlog_svc.find_backlog(repo_dir)
        if bf is None:
            yield _evt("aborted", reason="no BACKLOG.md found after PO phase")
            return
        items = backlog_svc.parse_file(bf)
        ordered = _dep_order(items)
        if max_bls is not None:
            ordered = ordered[:max_bls]
        yield _evt("backlog_parsed", count=len(ordered),
                   bls=[{"id": it.id, "title": it.title,
                         "deps": str(it.meta.get("dependencies") or "")} for it in ordered])

        # ── Step 5: per-BL loop ────────────────────────────────────────────────
        for it in ordered:
            bl_id = it.id
            per_bl = {"bl_id": bl_id, "title": it.title}
            yield _evt("bl.start", bl_id=bl_id, title=it.title)

            # Engineer
            yield _evt("engineer.start", bl_id=bl_id)
            eng_outcome = None
            async for e in _engineer_flow(repo_dir, repo_name, bl_id,
                                           timeout_per_role, retrieval_kwargs_builder):
                if "_orchestrator_outcome" in e:
                    eng_outcome = e
                    continue
                yield e
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
                    yield _evt("bl.done", bl_id=bl_id, outcome="no_op")
                    continue
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
                summary["bls"].append(per_bl)
                yield _evt("bl.done", bl_id=bl_id, outcome="engineer_unmerged")
                if stop_on_failure:
                    yield _evt("aborted", reason=f"engineer did not merge {bl_id}")
                    return
                continue
            else:
                # Reindex post-engineer (only when engineer actually committed)
                async for e in _run_indexers(repo_dir, f"reindex_after_engineer.{bl_id}"):
                    yield e

            # QA
            yield _evt("qa.start", bl_id=bl_id)
            qa_outcome = None
            async for e in _qa_or_scorer_flow(repo_dir, repo_name, bl_id, "qa",
                                                timeout_per_role, retrieval_kwargs_builder):
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
                    yield _evt("bl.done", bl_id=bl_id, outcome="merged_no_qa")
                    yield _evt("aborted",
                               reason=f"QA doctrine failed for {bl_id} (stop_on_qa_doctrine_failure)")
                    return

            # Reindex post-QA (QA may add characterization tests)
            async for e in _run_indexers(repo_dir, f"reindex_after_qa.{bl_id}"):
                yield e

            # Scorer
            yield _evt("scorer.start", bl_id=bl_id)
            score_outcome = None
            async for e in _qa_or_scorer_flow(repo_dir, repo_name, bl_id, "scorer",
                                                timeout_per_role, retrieval_kwargs_builder):
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
            yield _evt("bl.done", bl_id=bl_id, outcome=outcome)

        yield _evt("sprint_complete", summary=summary)
    finally:
        # B15: archive any traces this run produced (clean exit OR aborted OR
        # consumer disconnect). Silently best-effort — yielding from an async
        # generator's finally during aclose() is illegal (PEP 525), so we
        # never try; operators inspect traces_archive/<run_id>/ directly.
        try:
            _archive_traces_since(repo_name, run_started_at, run_id)
        except Exception:
            pass
