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
    *,
    run_id: str | None = None,
    brief_hash: str | None = None,
    feature_slug: str | None = None,
    inject_lessons: bool = False,
) -> AsyncIterator[dict]:
    cfg = repo_config_svc.load(repo_dir)
    family = cfg.doctrine or prompts_svc.select_family(classify_target(repo_dir))
    prompt = prompts_svc.build_po(family, brief, project_name, repo_dir, feature_slug=feature_slug,
                                  inject_lessons=inject_lessons)
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
        validation = doctrine_svc.validate_po(wt.path, feature_slug=feature_slug)
        attempt = 0
        while not validation["ok"] and attempt < 2:
            attempt += 1
            yield _ptag({"type": "_meta", "phase": "doctrine_check", "kind": "incomplete",
                        "attempt": attempt, **validation}, "po", trace=trace)
            fix = doctrine_svc.build_fix_prompt("po", validation)
            async for event in stream_agent_task(fix, wt.path, timeout_seconds=max(300, timeout // 2),
                                                  trace=trace, **rk):
                yield _tag(event, "po")
            validation = doctrine_svc.validate_po(wt.path, feature_slug=feature_slug)
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
) -> AsyncIterator[dict]:
    cfg = repo_config_svc.load(repo_dir)
    family = cfg.doctrine or prompts_svc.select_family(classify_target(repo_dir))
    section = _resolve_engineer_section(repo_dir, bl_id, feature_slug, section_override)
    prompt = prompts_svc.build_engineer(family, bl_id, section, repo_dir, feature_slug=feature_slug,
                                        inject_lessons=inject_lessons)
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
                                                          base_ref=cfg.agent_branch, run_id=run_id)
            yield _ptag({"type": "_meta", "phase": "bl_tests",
                        **{k: gate.get(k) for k in ("ok", "kind", "regressions", "failing_tests", "reason", "post_tail")}},
                       "engineer", bl_id, trace=trace)
            gate_attempt = 0
            gate_signatures.append(f"{gate.get('kind')}:{','.join(sorted((gate.get('regressions') or []) + (gate.get('new_failures') or [])))}")
            # No-abort doctrine: keep fixing until the BL's tests are GREEN.
            # Retry on `failed` (a real unit-test failure to fix) or `no_tests`
            # (engineer must add the required unit tests). `error` is
            # operator-infra → break and escalate with a dossier.
            while not gate.get("ok") and gate.get("kind") in ("failed", "no_tests") and gate_attempt < MAX_FIX_ATTEMPTS:
                gate_attempt += 1
                if gate.get("kind") == "no_tests":
                    fix = (f"Your BL {bl_id} added no unit tests. Doctrine requires comprehensive "
                           "unit tests covering this BL's behavior. Add them now (e.g. under "
                           "`backend/tests/...` as `test_*.py`), make them pass, and commit a NEW "
                           "commit. The harness will run ONLY your BL's tests.")
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
                                                              base_ref=cfg.agent_branch, run_id=run_id)
                yield _ptag({"type": "_meta", "phase": "bl_tests",
                            "gate_attempt": gate_attempt,
                            **{k: gate.get(k) for k in ("ok", "kind", "regressions", "failing_tests", "reason", "post_tail")}},
                           "engineer", bl_id, trace=trace)
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
    bl_base_ref: str | None = None,
) -> AsyncIterator[dict]:
    cfg = repo_config_svc.load(repo_dir)
    family = cfg.doctrine or prompts_svc.select_family(classify_target(repo_dir))
    bf = backlog_svc.find_backlog(repo_dir, feature_slug=feature_slug)
    section = backlog_svc.extract_section(bf.read_text(encoding="utf-8"), bl_id)
    if role == "qa":
        prompt = prompts_svc.build_qa(family, bl_id, section, repo_dir, feature_slug=feature_slug,
                                      inject_lessons=inject_lessons)
    else:
        prompt = prompts_svc.build_score(family, bl_id, section, repo_dir, feature_slug=feature_slug,
                                         inject_lessons=inject_lessons)
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
        wt = await create_worktree(repo_dir, base_ref=cfg.agent_branch)
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
            validation = doctrine_svc.validate_qa(wt.path, bl_id, base_ref=cfg.agent_branch,
                                                  retrieval_log=trace.retrieval_path, feature_slug=feature_slug)
        else:
            validation = doctrine_svc.validate_scorer(wt.path, bl_id, base_ref=cfg.agent_branch,
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
                validation = doctrine_svc.validate_qa(wt.path, bl_id, base_ref=cfg.agent_branch,
                                                      retrieval_log=trace.retrieval_path, feature_slug=feature_slug)
            else:
                validation = doctrine_svc.validate_scorer(wt.path, bl_id, base_ref=cfg.agent_branch,
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
                                                          base_ref=_bl_base, run_id=run_id)
            yield _ptag({"type": "_meta", "phase": "bl_tests",
                        **{k: gate.get(k) for k in ("ok", "kind", "regressions", "failing_tests", "reason", "post_tail")}},
                       role, bl_id, trace=trace)
            gate_attempt = 0
            while not gate.get("ok") and gate.get("kind") in ("failed", "no_tests") and gate_attempt < MAX_FIX_ATTEMPTS:
                gate_attempt += 1
                if gate.get("kind") == "no_tests":
                    fix = (f"No unit tests are associated with BL {bl_id}. Doctrine requires the "
                           "BL to carry comprehensive unit tests. Add the missing tests (e.g. under "
                           "`backend/tests/...` as `test_*.py`), make them pass, and commit.")
                else:
                    fix = doctrine_svc.build_gate_fix_prompt("qa", gate, bl_id=bl_id,
                                                             attempt=gate_attempt, max_attempts=MAX_FIX_ATTEMPTS)
                async for event in stream_agent_task(fix, wt.path,
                                                      timeout_seconds=max(300, timeout // 2),
                                                      trace=trace, **rk):
                    yield _tag(event, role, bl_id)
                validation = doctrine_svc.validate_qa(wt.path, bl_id, base_ref=cfg.agent_branch,
                                                      retrieval_log=trace.retrieval_path, feature_slug=feature_slug)
                if not validation["ok"]:
                    break
                gate = await regression_gate_svc.run_bl_tests(repo_dir, agent_branch=wt.branch,
                                                              base_ref=_bl_base, run_id=run_id)
                yield _ptag({"type": "_meta", "phase": "bl_tests",
                            "gate_attempt": gate_attempt,
                            **{k: gate.get(k) for k in ("ok", "kind", "regressions", "failing_tests", "reason", "post_tail")}},
                           role, bl_id, trace=trace)
            if validation["ok"] and gate.get("ok"):
                merge = await fast_forward_target(repo_dir, wt.branch, target_ref=cfg.agent_branch)
                if not merge.get("ok") and merge.get("kind") == "error":
                    await asyncio.sleep(2)
                    merge_retry = await fast_forward_target(repo_dir, wt.branch, target_ref=cfg.agent_branch)
                    if merge_retry.get("ok"):
                        merge = merge_retry
                # A1: same non_ff auto-rebase as the engineer flow — operator
                # commits race QA worktrees too.
                if not merge.get("ok") and merge.get("kind") == "non_ff":
                    yield _ptag({"type": "_meta", "phase": "merge_rebase_attempt",
                                "branch": wt.branch, "target_ref": cfg.agent_branch},
                               role, bl_id, trace=trace)
                    rebase = await _rebase_in_worktree(wt.path, cfg.agent_branch)
                    if rebase.get("ok"):
                        yield _ptag({"type": "_meta", "phase": "merge_rebase_succeeded",
                                    "branch": wt.branch}, role, bl_id, trace=trace)
                        gate2 = await regression_gate_svc.run_gate(repo_dir, agent_branch=wt.branch,
                                                                   target_ref=cfg.agent_branch, run_id=run_id)
                        yield _ptag({"type": "_meta", "phase": "regression_gate", "post_rebase": True,
                                    **{k: gate2.get(k) for k in ("ok","kind","regressions","failing_tests","reason","post_tail")}},
                                   role, bl_id, trace=trace)
                        if gate2.get("ok"):
                            merge = await fast_forward_target(repo_dir, wt.branch,
                                                              target_ref=cfg.agent_branch)
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
            merge = await fast_forward_target(repo_dir, wt.branch, target_ref=cfg.agent_branch)
            if not merge.get("ok") and merge.get("kind") == "error":
                await asyncio.sleep(2)
                merge_retry = await fast_forward_target(repo_dir, wt.branch, target_ref=cfg.agent_branch)
                if merge_retry.get("ok"):
                    merge = merge_retry
            # A1: same non_ff auto-rebase as the QA/engineer flows — QA worktrees
            # advance the agent_branch under the scorer. No post-rebase gate:
            # the scorer changes no source, so nothing can regress.
            if not merge.get("ok") and merge.get("kind") == "non_ff":
                yield _ptag({"type": "_meta", "phase": "merge_rebase_attempt",
                            "branch": wt.branch, "target_ref": cfg.agent_branch},
                           role, bl_id, trace=trace)
                rebase = await _rebase_in_worktree(wt.path, cfg.agent_branch)
                if rebase.get("ok"):
                    yield _ptag({"type": "_meta", "phase": "merge_rebase_succeeded",
                                "branch": wt.branch}, role, bl_id, trace=trace)
                    merge = await fast_forward_target(repo_dir, wt.branch, target_ref=cfg.agent_branch)
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


def _resolve_app_boot_port(app_boot: dict, port: int) -> dict:
    """Return a copy of the app_boot contract with ``${PORT}`` substituted in
    cmd / ready_url / pre_cmd, and the chosen port recorded under ``_port``."""
    def _sub(s: str) -> str:
        return s.replace("${PORT}", str(port))
    out = dict(app_boot)
    out["cmd"] = [_sub(x) for x in app_boot.get("cmd", [])]
    if app_boot.get("ready_url"):
        out["ready_url"] = _sub(app_boot["ready_url"])
    if app_boot.get("pre_cmd"):
        out["pre_cmd"] = [[_sub(tok) for tok in step] for step in app_boot["pre_cmd"]]
    out["_port"] = port
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
        boot_block = (
            f"- BOOT THE APP NATIVELY — this target has NO docker-compose stack. "
            f"The harness has reserved **port {port}** and materialized the "
            f"gitignored runtime config into your worktree. Drive the boot "
            f"yourself from the worktree root:\n"
            f"{pre_lines}"
            f"  Then start the app (background it) and wait for it to serve:\n"
            f"    {env_str + ' ' if env_str else ''}{cmd_str}\n"
            f"  Poll `{ready_url}` until it returns 2xx (up to {ready_to}s).\n"
            f"- LEVEL-3 READINESS (REQUIRED before any journey): confirm the app "
            f"serves THIS sprint's feature — request at least one NEW-feature "
            f"route and verify it is NOT 404. A stale baseline build can answer "
            f"200 on old routes while 404ing the new ones; if that happens you "
            f"booted the wrong build/port — fix it before proceeding. Drive all "
            f"journeys over HTTP against `http://localhost:{port}`.\n"
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


# ─── ABL-0015 auto-dispatch follow-up engineer ─────────────────────────────
# §9 Decision 2: v1 dispatches at most one follow-up per sprint. Bump (or
# make operator-configurable) only after calibration. The framework's
# highest-risk action stays small until proven.
FOLLOWUP_COST_CAP = 1

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
            task_id=f"accept-{run_id}",
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
        _port = _alloc_free_port()
        resolved_app_boot = _resolve_app_boot_port(_app_boot_cfg, _port)
        mat_results = _materialize_app_boot(resolved_app_boot, wt.path)
        yield _seal(_evt(
            "acceptance.app_boot.prepared",
            run_id=run_id,
            port=_port,
            cmd=resolved_app_boot.get("cmd"),
            ready_url=resolved_app_boot.get("ready_url"),
            materialized=[m for m in mat_results if m["ok"]],
            rejected=[m for m in mat_results if not m["ok"]],
        ))

    try:
        for attempt in range(1, ACCEPTANCE_MAX_RETRIES + 2):  # 1, 2, 3 = 1 + 2 retries
            last_attempt = attempt
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
        # Archive whatever the agent produced (even on give_up, the report
        # is the most valuable evidence — keep it).
        archive_dest = _archive_acceptance_dir(acceptance_dir_wt, run_id)
        if archive_dest is not None:
            yield _evt(
                "acceptance.archived",
                run_id=run_id,
                archive=str(archive_dest),
            )
        # ABL-0014 §I.3 Batch B: persist acceptance findings to the
        # per-feature ledger. Prefer the archived copy (immutable,
        # survives worktree cleanup); fall back to the worktree copy
        # if archive failed but the worktree is still on disk. Never
        # raises — ledger failures are advisory and must not abort
        # the sprint, so a corrupt report.json yields an .error event
        # but the flow continues to `remove_worktree` and `done`.
        findings_persisted = 0
        report_src: Path | None = None
        if archive_dest is not None and (archive_dest / "report.json").exists():
            report_src = archive_dest / "report.json"
        elif (acceptance_dir_wt / "report.json").exists():
            report_src = acceptance_dir_wt / "report.json"
        if report_src is not None:
            try:
                report_dict = json.loads(report_src.read_text(encoding="utf-8"))
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

    # ABL-0015 Batch C: auto-dispatch a follow-up engineer on confirmed
    # product_bug findings. Runs AFTER the finally (acceptance worktree +
    # volumes already reaped) and BEFORE acceptance.done — so the follow-up
    # worktree is created AND reaped (by _engineer_flow's own finally)
    # before run_brief's closure_check.scan_all fires. Gated OFF by default
    # and requires the retrieval builder (Batch B). Advisory: a dispatch
    # failure must not abort the sprint.
    if run_acceptance_followup and retrieval_kwargs_builder is not None and feature_slug:
        try:
            async for evt in _dispatch_followup_engineers(
                repo_dir, repo_name, run_id, feature_slug,
                retrieval_kwargs_builder, timeout=timeout,
            ):
                yield evt
        except Exception as exc:  # noqa: BLE001 — advisory: never abort sprint
            yield _evt("acceptance.followup.error", run_id=run_id, error=str(exc))

    yield _seal(_evt(
        "acceptance.done",
        run_id=run_id,
        feature_slug=feature_slug,
        validator_ok=validation["ok"],
        attempts=last_attempt,
        acceptance_dir=str(feature_dir / "acceptance"),
        backend_bls=backend_bls,
        findings_persisted=findings_persisted,
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
    run_janitor: bool = True,  # Janitor/Ops role (operator 2026-06-07): spawn the
                               # environment-repair agent on non-code failures.
                               # Flag = named rollback (set False to disable wiring).
    warm_retrieval: bool = True,  # A56 (operator 2026-06-07): warm the LOCAL
                                  # retrieval backend before the PO so the first
                                  # agent isn't grounding-blind. Flag = rollback.
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

    try:
        # Structural fix (2026-06-06): operate on the configured agent branch,
        # never whatever happens to be checked out — keeps main_ref pristine and
        # makes the FF merge target == the checked-out branch.
        yield _ensure_on_agent_branch(repo_dir)

        # ── Step 2-3: initial indexing ─────────────────────────────────────────
        async for e in _run_indexers(repo_dir, "index_initial"):
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
                                    feature_slug=feature_slug, inject_lessons=inject_lessons):
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
        ordered = _dep_order(items)
        if max_bls is not None:
            ordered = ordered[:max_bls]
        yield _evt("backlog_parsed", count=len(ordered),
                   bls=[{"id": it.id, "title": it.title,
                         "deps": str(it.meta.get("dependencies") or "")} for it in ordered])
        _checkpoint(current_bl=None)  # A7: first checkpoint after PO+parse

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
        for it in ordered:
            bl_id = it.id
            if not _reached_start_bl:
                if bl_id == start_bl:
                    _reached_start_bl = True
                else:
                    yield _evt("bl.skipped", bl_id=bl_id, reason=f"before start_bl={start_bl}")
                    continue
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
                                               inject_lessons=inject_lessons):
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
                    yield _evt("bl.escalated", bl_id=bl_id, role="engineer",
                               reason=_esc_reason, dossier=_dossier)
                    yield _evt("bl.done", bl_id=bl_id, outcome="engineer_escalated")
                    if stop_on_failure:
                        terminal_status = "escalated"
                        yield _evt("escalated", bl_id=bl_id, role="engineer",
                                   reason=f"engineer escalated {bl_id} for operator review "
                                          f"(no-abort doctrine, Option A — dossier attached)",
                                   dossier=_dossier)
                        return
                    continue
                # A59: Janitor-recovered merge — reindex then fall through to the
                # normal QA/scorer continuation (same as a clean merge).
                async for e in _run_indexers(repo_dir, f"reindex_after_engineer.{bl_id}"):
                    yield e
            else:
                # Reindex post-engineer (only when engineer actually committed)
                async for e in _run_indexers(repo_dir, f"reindex_after_engineer.{bl_id}"):
                    yield e

            # QA
            yield _evt("qa.start", bl_id=bl_id)
            qa_outcome = None
            async for e in _qa_or_scorer_flow(repo_dir, repo_name, bl_id, "qa",
                                                timeout_per_role, retrieval_kwargs_builder,
                                                run_id=run_id, feature_slug=feature_slug,
                                                inject_lessons=inject_lessons,
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
                    terminal_status = "escalated"
                    yield _evt("escalated", bl_id=bl_id, role="qa",
                               reason=f"QA could not satisfy doctrine for {bl_id} after exhaustive "
                                      f"attempts (stop_on_qa_doctrine_failure) — escalating for operator review",
                               dossier=(qa_outcome or {}).get("dossier") or {})
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
                    terminal_status = "escalated"
                    yield _evt("escalated", bl_id=bl_id, role="qa",
                               reason=f"QA could not reach a green gate for {bl_id} after exhaustive "
                                      f"investigate→fix→re-test attempts — escalating for operator review",
                               dossier=_qa_dossier)
                    return
                # stop_on_failure=False: best-effort continue. The engineer's
                # merge stays on the trunk (rollback is scoped to aborts); the
                # merged_no_qa outcome flags that it shipped without QA.
                yield _evt("bl.done", bl_id=bl_id, outcome="merged_no_qa")
                continue

            # Reindex post-QA (QA may add characterization tests)
            async for e in _run_indexers(repo_dir, f"reindex_after_qa.{bl_id}"):
                yield e

            # Scorer
            yield _evt("scorer.start", bl_id=bl_id)
            score_outcome = None
            async for e in _qa_or_scorer_flow(repo_dir, repo_name, bl_id, "scorer",
                                                timeout_per_role, retrieval_kwargs_builder,
                                                run_id=run_id, feature_slug=feature_slug,
                                                inject_lessons=inject_lessons):
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

        # ABL-0014: acceptance pass — runs AFTER sprint_complete and BEFORE
        # doctrine_meta + closure_check. Advisory only (§E.1 Q3): exceptions
        # are surfaced as acceptance.error and never abort the sprint.
        # Default off until §E.1 Q6 calibration (3 smoke runs) flips it on.
        if run_acceptance:
            # A13-followup (A64): one TraceWriter shared by the regression
            # checkpoint AND the acceptance flow, so both seal their enforcement
            # phase events into a single co-located phase_events.jsonl that the
            # ABL-0017 efficacy aggregator joins against. Before A64 the
            # integration checkpoint — the one gate that protects PRE-EXISTING
            # behavior — was invisible to the self-hardening loop (its own crew
            # surfaced this gap from sealed evidence).
            acceptance_trace = TraceWriter(
                repo=repo_name, role="acceptance", task_id=run_id)
            # Simple gating model (2026-06-06) — the ONE full-suite regression
            # checkpoint: run the entire pre-existing suite of the assembled
            # feature against the sprint-start baseline to catch collateral
            # regressions to PRE-EXISTING functionality (per-BL gates only ran
            # each BL's own tests). run_gate's A49 arbitration still applies, so
            # a transient flake won't false-red it. Advisory here (acceptance is
            # post sprint_complete): a red is surfaced loudly for operator action.
            if run_base_sha:
                try:
                    _accfg = repo_config_svc.load(repo_dir)
                    rc = await regression_gate_svc.run_gate(
                        repo_dir, agent_branch=_accfg.agent_branch,
                        target_ref=run_base_sha, run_id=run_id)
                    rc_evt = _evt("regression_checkpoint",
                                  ok=rc.get("ok"), kind=rc.get("kind"),
                                  reason=rc.get("reason"),
                                  regressions=(rc.get("regressions") or [])[:50],
                                  failing_tests=(rc.get("failing_tests") or [])[:50])
                    try:  # A64: seal — defensive, observability never blocks
                        acceptance_trace.write_phase_event(rc_evt)
                    except Exception:  # noqa: BLE001
                        pass
                    yield rc_evt
                except Exception as exc:  # noqa: BLE001
                    yield _evt("regression_checkpoint.error", error=str(exc))
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
                    trace=acceptance_trace,  # A64: share the checkpoint's trace
                ):
                    yield evt
            except Exception as exc:
                yield _evt("acceptance.error", error=str(exc))

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
