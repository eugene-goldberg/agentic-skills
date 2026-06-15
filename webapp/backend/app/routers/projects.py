"""Project-scoped endpoints: brief decomposition + per-BL execution.

Layered on top of the existing /api/tasks stream service:

  POST /api/projects/{repo}/decompose-brief   →  PO agent  (SSE)
  GET  /api/projects/{repo}/backlog            →  parsed backlog items
  POST /api/projects/{repo}/execute-bl         →  Engineer agent for one BL (SSE)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services import backlog as backlog_svc
from app.services import disk_preflight as disk_preflight_svc
from app.services import orchestrator as orchestrator_svc
from app.services import run_state as run_state_svc
from app.services.claude_agent import stream_agent_task
from app.services.indexing import run_claude_context_index, run_graphify_update
from app.services.traces import TraceWriter, list_traces
from app.services.git_worktree import (
    Worktree,
    create_worktree,
    fast_forward_target,
    get_commit_sha,
    has_new_commits,
    remove_worktree,
)
from app.services import repo_config as repo_config_svc
from app.services import regression_gate as regression_gate_svc
from app.services import doctrine_validator as doctrine_svc
from app.services import prompts as prompts_svc
from app.services.prompts import (
    build_engineer_prompt,
    build_po_prompt,
    build_qa_prompt,
    build_score_prompt,
)
from app.services.brownfield import classify_target
from app.services import findings_ledger as findings_ledger_svc

router = APIRouter(prefix="/api/projects", tags=["projects"])

REPOS_ROOT = Path(
    os.environ.get(
        "AGENT_REPOS_ROOT",
        Path(__file__).resolve().parents[2] / "repos",
    )
).resolve()

# Reference repo handed to the retrieval MCP server. Default = the curated
# fastapi-good-patterns checkout used by the langgraph A/B test treatment arm.
_AGENTIC_ROOT = Path(__file__).resolve().parents[4]
RETRIEVAL_REFERENCE_REPO = Path(
    os.environ.get(
        "RETRIEVAL_REFERENCE_REPO",
        _AGENTIC_ROOT / "reference-repos" / "fastapi-good-patterns",
    )
).resolve()


class RetrievalUnavailable(RuntimeError):
    """Raised when the retrieval stack is not in a state to ground a brownfield run.

    Routers catch this, emit a `_meta phase=retrieval kind=unavailable reason=...`
    SSE event, and abort the run rather than silently degrading. Per CLAUDE.md
    the brownfield doctrine requires grounded retrieval — a degraded run would
    contaminate scores.
    """


# A3: Milvus auto-restart cooldown so we don't loop on a permanently-broken
# container. Module-local; resets when uvicorn restarts.
_MILVUS_LAST_RESTART_AT: float = 0.0
_MILVUS_CONTAINER = os.environ.get("MILVUS_CONTAINER_NAME", "milvus-standalone")
# A68: Milvus standalone reloads ALL accumulated segments on boot (every
# per-target lessons_/patterns_/code-context collection), which routinely takes
# MINUTES, not seconds — observed ~3.5 min cold-start in run-20260610T040613Z.
# The old fixed 30s poll + 60s cooldown escalated mid-reload (the run gave up at
# T+~165s; Milvus served at ~T+210s), spuriously failing a BL on a HARNESS infra
# blip rather than waiting it out. Wait generously (poll until it serves), and
# size the cooldown to SPAN the reload window so concurrent/retry calls poll the
# in-progress reload instead of re-issuing `docker restart` and thrashing it.
_MILVUS_RESTART_WAIT_S = float(os.environ.get("MILVUS_RESTART_WAIT_S", "300"))
_MILVUS_RESTART_COOLDOWN_S = _MILVUS_RESTART_WAIT_S


def _milvus_port_reachable(timeout: float = 1.0) -> bool:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(("127.0.0.1", 19530))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _try_milvus_restart() -> tuple[bool, str]:
    """A3/A68: best-effort recovery of a down/hung Milvus + poll until it serves.

    Uses ``docker restart`` (not ``start``) so a hung-but-running container is
    actually cycled, then polls :19530 for up to ``_MILVUS_RESTART_WAIT_S``
    (default 300s) because Milvus standalone's segment reload scales with
    accumulated data and routinely takes minutes. The cooldown spans the same
    window: a call arriving while a prior restart is still reloading does NOT
    re-issue ``docker restart`` (which would thrash the reload) — it polls the
    in-progress reload for the time remaining. Returns (ok, message).
    """
    global _MILVUS_LAST_RESTART_AT
    now = time.time()
    elapsed = now - _MILVUS_LAST_RESTART_AT
    if elapsed < _MILVUS_RESTART_COOLDOWN_S:
        # A restart was issued recently; Milvus may still be reloading segments.
        # Don't re-restart — wait out the rest of the reload window.
        remaining = max(0.0, _MILVUS_RESTART_WAIT_S - elapsed)
        deadline = time.time() + remaining
        while time.time() < deadline:
            if _milvus_port_reachable(timeout=0.5):
                return True, f"{_MILVUS_CONTAINER} reachable (reload finished ~{time.time() - _MILVUS_LAST_RESTART_AT:.0f}s after restart)"
            time.sleep(2.0)
        return False, f"{_MILVUS_CONTAINER} still unreachable ~{time.time() - _MILVUS_LAST_RESTART_AT:.0f}s after restart"
    _MILVUS_LAST_RESTART_AT = now
    import subprocess as _sp
    try:
        proc = _sp.run(
            ["docker", "restart", _MILVUS_CONTAINER],
            capture_output=True, text=True, timeout=90.0, check=False,
        )
    except (_sp.SubprocessError, OSError) as exc:
        return False, f"docker restart failed: {type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        return False, f"docker restart exit={proc.returncode}: {(proc.stderr or '').strip()[:200]}"
    # Poll the port until Milvus finishes reloading its segments (generous — see A68).
    deadline = time.time() + _MILVUS_RESTART_WAIT_S
    while time.time() < deadline:
        if _milvus_port_reachable(timeout=0.5):
            return True, f"restarted {_MILVUS_CONTAINER} (port healthy after {time.time() - _MILVUS_LAST_RESTART_AT:.0f}s)"
        time.sleep(2.0)
    return False, f"restarted {_MILVUS_CONTAINER} but port still unreachable after {_MILVUS_RESTART_WAIT_S:.0f}s"


def _preflight_retrieval() -> tuple[bool, str]:
    """Cheap fail-loud health check: reference repo + Milvus reachable.

    Returns (ok, reason). Reason is empty on success, human-readable on failure.
    Best-effort: a Milvus ping that times out in <1s counts as failure.

    A3/A68: if Milvus is unreachable, `docker restart` it and poll :19530 until
    it serves (up to _MILVUS_RESTART_WAIT_S, default 300s — standalone segment
    reload takes minutes). A cooldown spanning that window makes concurrent/retry
    calls poll the in-progress reload instead of re-restarting it.
    """
    if not RETRIEVAL_REFERENCE_REPO.exists():
        return False, f"RETRIEVAL_REFERENCE_REPO missing: {RETRIEVAL_REFERENCE_REPO}"
    if _milvus_port_reachable():
        return True, ""
    # Port closed → try to self-heal.
    restart_ok, restart_msg = _try_milvus_restart()
    if restart_ok:
        print(f"[preflight] {restart_msg}", flush=True)
        return True, ""
    return False, f"Milvus unreachable at 127.0.0.1:19530; auto-restart attempt: {restart_msg}"


def _retrieval_kwargs(wt: Worktree, role: str, bl_id: str | None = None, trace: TraceWriter | None = None,
                      lessons_repo: Path | None = None) -> dict:
    """Build stream_agent_task kwargs that enable the retrieval MCP server.

    Fail-loud: if the reference repo is missing or Milvus is unreachable, raise
    RetrievalUnavailable. The caller is responsible for emitting an SSE event
    and aborting the run. Silent fallback is no longer acceptable — see CLAUDE.md.

    Retrieval audit log is written into the persistent trace dir so it survives
    worktree cleanup; falls back to inside the worktree if no trace is supplied.
    """
    ok, reason = _preflight_retrieval()
    if not ok:
        raise RetrievalUnavailable(reason)
    if trace is not None:
        retrieval_log = trace.retrieval_path
    else:
        log_name = f"retrieval-{role}{('-' + bl_id) if bl_id else ''}.jsonl"
        retrieval_log = wt.path / ".agile-v" / "logs" / log_name
    kw = {
        "reference_repo": RETRIEVAL_REFERENCE_REPO,
        # Point retrieval at the STABLE main checkout (already indexed at
        # index_initial), NOT the per-agent worktree. Each worktree is a fresh
        # path → a fresh EMPTY code collection → claude-context-core re-indexes
        # the whole repo before that agent's first semantic_search (minutes on a
        # CPU-only host; it blew the warmup + search timeouts and forced the crew
        # to ground blind). The worktree is byte-identical to main at spawn, so
        # the main collection grounds correctly; the agent reads its own new
        # files directly. Mirrors the lessons_repo stable-key fix below.
        "target_repo": lessons_repo or wt.path,
        "retrieval_log_path": retrieval_log,
    }
    # ABL-0016 Stage 1.5: pass the STABLE main-checkout path so the lessons
    # vector collection key + ledger read agree between the write path
    # (orchestrator) and the read path (search_lessons MCP tool). Without it the
    # per-run worktree path would key a fresh empty collection every run.
    if lessons_repo is not None:
        kw["lessons_repo"] = lessons_repo
    return kw


def _repo_dir(repo: str) -> Path:
    # Reject '..' or absolute-path tricks by requiring `repo` to be a direct
    # child entry of REPOS_ROOT. Symlinks are intentionally allowed so users
    # can expose existing repos without copying them.
    entry = REPOS_ROOT / repo
    if entry.parent.resolve() != REPOS_ROOT:
        raise HTTPException(status_code=400, detail="repo name not allowed")
    p = entry.resolve()
    if not p.is_dir() or not (p / ".git").exists():
        raise HTTPException(status_code=404, detail=f"repo {repo!r} not found")
    return p


def _sse(event: dict) -> bytes:
    return f"data: {json.dumps(event, default=str)}\n\n".encode()


class DecomposeRequest(BaseModel):
    brief: str = Field(..., min_length=20)
    project_name: str | None = None
    timeout_seconds: int = Field(2400, ge=60, le=7200)


class ExecuteBLRequest(BaseModel):
    bl_id: str = Field(..., pattern=r"^BL-\d{4}$")
    extra_notes: str | None = None
    timeout_seconds: int = Field(2400, ge=60, le=7200)
    keep_worktree: bool = False


class BLActionRequest(BaseModel):
    """Shared shape for QA-on-BL and Score-BL."""
    bl_id: str = Field(..., pattern=r"^BL-\d{4}$")
    timeout_seconds: int = Field(1800, ge=60, le=7200)


# Rubric is shared across all repos and lives at the workspace root.
RUBRIC_PATH = Path(__file__).resolve().parents[4] / "rubrics" / "production_grade_scorecard.md"


def _read_rubric() -> str:
    if RUBRIC_PATH.is_file():
        return RUBRIC_PATH.read_text(encoding="utf-8")
    return (
        "# Rubric not found at runtime — score 0–5 per dimension on:\n"
        "Core (10): Brief comprehension, Scope control, Correctness, Verification quality, "
        "Security and privacy, Data integrity, Maintainability, Integration quality, "
        "Production readiness, Autonomy.\n"
        "Engineer role (5): Implementation completeness, Architectural fit, Test compatibility, "
        "Debugging behavior, Dependency discipline.\n"
    )


# ----------------------- listing -----------------------------------------

@router.post("/{repo}/index/graphify")
async def index_graphify(repo: str) -> dict:
    repo_dir = _repo_dir(repo)
    return await run_graphify_update(repo_dir)


@router.post("/{repo}/index/claude-context")
async def index_claude_context(repo: str) -> dict:
    repo_dir = _repo_dir(repo)
    return await run_claude_context_index(repo_dir)


@router.get("/{repo}/backlog")
def get_backlog(repo: str) -> dict:
    repo_dir = _repo_dir(repo)
    bf = backlog_svc.find_backlog(repo_dir)
    if bf is None:
        return {"path": None, "items": []}
    items = backlog_svc.parse_file(bf)
    return {
        "path": str(bf.relative_to(repo_dir)),
        "items": [
            {
                "id": it.id,
                "title": it.title,
                "type": it.meta.get("type"),
                "priority": it.meta.get("priority"),
                "status": it.meta.get("status"),
                "effort": it.meta.get("effort"),
                "dependencies": it.meta.get("dependencies"),
                "story": next(
                    (
                        ln.split(":", 1)[1].strip()
                        for ln in it.body.splitlines()
                        if ln.lower().startswith("**story:**")
                    ),
                    None,
                ),
                "body": it.body,
            }
            for it in items
        ],
    }


# ----------------------- decompose ---------------------------------------

@router.post("/{repo}/decompose-brief")
async def decompose_brief(repo: str, req: DecomposeRequest):
    repo_dir = _repo_dir(repo)
    _cfg = repo_config_svc.load(repo_dir)
    _family = _cfg.doctrine or prompts_svc.select_family(classify_target(repo_dir))
    prompt = prompts_svc.build_po(_family, req.brief, req.project_name or repo, repo_dir)

    async def gen():
        wt: Worktree | None = None
        trace: TraceWriter | None = None
        try:
            cfg = repo_config_svc.load(repo_dir)
            wt = await create_worktree(repo_dir, base_ref=cfg.agent_branch)
            trace = TraceWriter(repo=repo, role="po", task_id=wt.task_id)
            wt_evt = {
                "type": "_meta",
                "phase": "worktree_ready",
                "task_id": wt.task_id,
                "branch": wt.branch,
                "role": "po",
                "trace_dir": str(trace.dir),
            }
            trace.write_event(wt_evt)
            yield _sse(wt_evt)
            try:
                rk = _retrieval_kwargs(wt, role="po", trace=trace)
            except RetrievalUnavailable as e:
                yield _sse({"type": "_meta", "phase": "retrieval", "kind": "unavailable", "reason": str(e)})
                return
            async for event in stream_agent_task(
                prompt,
                wt.path,
                timeout_seconds=req.timeout_seconds,
                trace=trace,
                **rk,
            ):
                yield _sse(event)

            # ─── Doctrine pre-commit validator ───
            MAX_FIX_RETRIES = 2
            validation = doctrine_svc.validate_po(wt.path)
            attempt = 0
            while not validation["ok"] and attempt < MAX_FIX_RETRIES:
                attempt += 1
                yield _sse({
                    "type": "_meta",
                    "phase": "doctrine_check",
                    "kind": "incomplete",
                    "attempt": attempt,
                    "missing": validation["missing"],
                    "empty": validation["empty"],
                    "summary": validation["summary"],
                })
                fix_prompt = doctrine_svc.build_fix_prompt("po", validation)
                async for event in stream_agent_task(
                    fix_prompt,
                    wt.path,
                    timeout_seconds=max(300, req.timeout_seconds // 2),
                    trace=trace,
                    **rk,
                ):
                    yield _sse(event)
                validation = doctrine_svc.validate_po(wt.path)
            yield _sse({
                "type": "_meta",
                "phase": "doctrine_check",
                "kind": "complete" if validation["ok"] else "give_up",
                "attempts": attempt,
                "summary": validation["summary"],
            })

            commit_sha = await get_commit_sha(wt)
            new_commits = await has_new_commits(wt, base_ref="HEAD~1")

            # Copy artifacts back to main repo ONLY if doctrine passed.
            merged_bl_path: str | None = None
            imported_artifacts: list[str] = []
            if validation["ok"]:
                from shutil import copy2, copytree
                src_bl = wt.path / ".agile-v" / "BACKLOG.md"
                if src_bl.exists():
                    dst_bl = repo_dir / ".agile-v" / "BACKLOG.md"
                    dst_bl.parent.mkdir(parents=True, exist_ok=True)
                    copy2(src_bl, dst_bl)
                    merged_bl_path = str(dst_bl.relative_to(repo_dir))
                    imported_artifacts.append(merged_bl_path)
                from app.services.brownfield import pick_artifact_dir
                art = pick_artifact_dir(wt.path)
                src_bf = wt.path / art
                if src_bf.exists():
                    dst_bf = repo_dir / art
                    if dst_bf.exists():
                        import shutil
                        shutil.rmtree(dst_bf)
                    copytree(src_bf, dst_bf)
                    imported_artifacts.append(art + "/")
                import subprocess
                subprocess.run(["git", "add", ".agile-v/", art + "/"], cwd=repo_dir, check=False)
                subprocess.run(
                    ["git", "commit", "-m", f"po: import backlog + brownfield context from {wt.branch}",
                     "--author", "Claude PO Agent <po@webapp.local>"],
                    cwd=repo_dir,
                    check=False,
                )

            done_evt = {
                "type": "done",
                "role": "po",
                "task_id": wt.task_id,
                "branch": wt.branch,
                "commit_sha": commit_sha,
                "new_commits": new_commits,
                "doctrine_ok": validation["ok"],
                "doctrine_missing": validation["missing"],
                "doctrine_empty": validation["empty"],
                "doctrine_attempts": attempt,
                "imported_backlog_path": merged_bl_path,
                "imported_artifacts": imported_artifacts,
                "trace_dir": str(trace.dir) if trace else None,
            }
            if trace is not None:
                trace.write_event(done_evt)
            yield _sse(done_evt)
        except Exception as exc:  # noqa: BLE001
            err = {"type": "_error", "error": f"{type(exc).__name__}: {exc}"}
            if trace is not None:
                trace.write_event(err)
            yield _sse(err)
        finally:
            if trace is not None:
                trace.close()
            if wt is not None:
                try:
                    await remove_worktree(repo_dir, wt)
                    yield _sse({"type": "_meta", "phase": "worktree_removed"})
                except Exception as exc:  # noqa: BLE001
                    yield _sse({"type": "_error", "error": f"cleanup: {exc}"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ----------------------- execute BL --------------------------------------

@router.post("/{repo}/execute-bl")
async def execute_bl(repo: str, req: ExecuteBLRequest):
    repo_dir = _repo_dir(repo)
    bf = backlog_svc.find_backlog(repo_dir)
    if bf is None:
        raise HTTPException(status_code=400, detail="no BACKLOG.md found — decompose a brief first")
    text = bf.read_text(encoding="utf-8")
    section = backlog_svc.extract_section(text, req.bl_id)
    if section is None:
        raise HTTPException(status_code=404, detail=f"{req.bl_id} not found in backlog")

    _cfg = repo_config_svc.load(repo_dir)
    _family = _cfg.doctrine or prompts_svc.select_family(classify_target(repo_dir))
    full_prompt = prompts_svc.build_engineer(_family, req.bl_id, section, repo_dir)
    if req.extra_notes:
        full_prompt += f"\n\n## Extra user notes\n{req.extra_notes}\n"

    async def gen():
        wt: Worktree | None = None
        trace: TraceWriter | None = None
        try:
            cfg = repo_config_svc.load(repo_dir)
            wt = await create_worktree(repo_dir, base_ref=cfg.agent_branch)
            trace = TraceWriter(repo=repo, role="engineer", bl_id=req.bl_id, task_id=wt.task_id)
            wt_evt = {
                "type": "_meta",
                "phase": "worktree_ready",
                "task_id": wt.task_id,
                "branch": wt.branch,
                "bl_id": req.bl_id,
                "role": "engineer",
                "trace_dir": str(trace.dir),
            }
            trace.write_event(wt_evt)
            yield _sse(wt_evt)
            try:
                rk = _retrieval_kwargs(wt, role="engineer", bl_id=req.bl_id, trace=trace)
            except RetrievalUnavailable as e:
                yield _sse({"type": "_meta", "phase": "retrieval", "kind": "unavailable", "reason": str(e)})
                return
            async for event in stream_agent_task(
                full_prompt,
                wt.path,
                timeout_seconds=req.timeout_seconds,
                trace=trace,
                min_pregrounding=3,
                **rk,
            ):
                yield _sse(event)
            # ─── Doctrine pre-merge validator (brownfield) ───
            MAX_FIX_RETRIES = 2
            validation = doctrine_svc.validate_engineer(wt.path, req.bl_id, base_ref=cfg.agent_branch, retrieval_log=trace.retrieval_path)
            # R11 short-circuit: legitimately no-op BL (work already shipped upstream).
            # Skip retries / gate / merge — there is nothing to validate or merge.
            if validation.get("no_op"):
                yield _sse({
                    "type": "_meta",
                    "phase": "no_op",
                    "kind": "already_satisfied",
                    "bl_id": req.bl_id,
                    "base_ref": cfg.agent_branch,
                    "summary": validation["summary"],
                })
                return
            attempt = 0
            while not validation["ok"] and attempt < MAX_FIX_RETRIES:
                attempt += 1
                yield _sse({
                    "type": "_meta",
                    "phase": "doctrine_check",
                    "kind": "incomplete",
                    "attempt": attempt,
                    "missing": validation["missing"],
                    "empty": validation["empty"],
                    "summary": validation["summary"],
                })
                fix_prompt = doctrine_svc.build_fix_prompt("engineer", validation, bl_id=req.bl_id)
                async for event in stream_agent_task(
                    fix_prompt,
                    wt.path,
                    timeout_seconds=max(300, req.timeout_seconds // 2),
                    trace=trace,
                    **rk,
                ):
                    yield _sse(event)
                validation = doctrine_svc.validate_engineer(wt.path, req.bl_id, base_ref=cfg.agent_branch, retrieval_log=trace.retrieval_path)
            yield _sse({
                "type": "_meta",
                "phase": "doctrine_check",
                "kind": "complete" if validation["ok"] else "give_up",
                "attempts": attempt,
                "summary": validation["summary"],
            })

            commit_sha = await get_commit_sha(wt)
            new_commits = await has_new_commits(wt, base_ref="HEAD~1")
            merge_result = None
            gate_result = None
            if validation["ok"] and new_commits > 0:
                gate_result = await regression_gate_svc.run_gate(repo_dir, agent_branch=wt.branch, target_ref=cfg.agent_branch)
                yield _sse({
                    "type": "_meta",
                    "phase": "regression_gate",
                    **{k: gate_result.get(k) for k in ("ok", "kind", "pre", "post", "regressions", "new_failures", "reason", "command", "post_tail", "pre_tail")},
                })
                # R10.1: gate-failure auto-recovery. Re-invoke the engineer
                # with a focused fix-prompt (extracted Playwright/pytest
                # failures) and re-run doctrine + gate. Only `regressed`
                # is recoverable — `error` / `inconclusive` go straight to
                # awaiting_review since they're infra-level.
                MAX_GATE_RETRIES = 2
                gate_attempt = 0
                while (
                    not gate_result.get("ok")
                    and gate_result.get("kind") == "regressed"
                    and gate_attempt < MAX_GATE_RETRIES
                ):
                    gate_attempt += 1
                    fix_prompt = doctrine_svc.build_gate_fix_prompt(
                        "engineer", gate_result,
                        bl_id=req.bl_id, attempt=gate_attempt, max_attempts=MAX_GATE_RETRIES,
                    )
                    async for event in stream_agent_task(
                        fix_prompt,
                        wt.path,
                        timeout_seconds=max(300, req.timeout_seconds // 2),
                        trace=trace,
                        **rk,
                    ):
                        yield _sse(event)
                    # Re-validate doctrine after the gate-fix amend.
                    validation = doctrine_svc.validate_engineer(
                        wt.path, req.bl_id, base_ref=cfg.agent_branch,
                        retrieval_log=trace.retrieval_path,
                    )
                    if not validation["ok"]:
                        yield _sse({
                            "type": "_meta",
                            "phase": "doctrine_check",
                            "kind": "incomplete_after_gate_fix",
                            "attempt": gate_attempt,
                            "missing": validation["missing"],
                            "empty": validation["empty"],
                            "summary": validation["summary"],
                        })
                        break
                    # Re-run gate.
                    gate_result = await regression_gate_svc.run_gate(
                        repo_dir, agent_branch=wt.branch, target_ref=cfg.agent_branch,
                    )
                    yield _sse({
                        "type": "_meta",
                        "phase": "regression_gate",
                        "gate_attempt": gate_attempt,
                        **{k: gate_result.get(k) for k in ("ok", "kind", "pre", "post", "regressions", "new_failures", "reason", "command", "post_tail", "pre_tail")},
                    })
                if validation["ok"] and gate_result.get("ok"):
                    merge_result = await fast_forward_target(repo_dir, wt.branch, target_ref=cfg.agent_branch)
                    yield _sse({
                        "type": "_meta",
                        "phase": "merge_to_target",
                        "kind": merge_result.get("kind"),
                        "ok": merge_result.get("ok"),
                        "merged_sha": merge_result.get("merged_sha"),
                        "target_ref": merge_result.get("target_ref"),
                        "error": merge_result.get("error"),
                    })
                else:
                    yield _sse({"type": "_meta", "phase": "awaiting_review", "reason": gate_result.get("reason")})
            elif not validation["ok"]:
                yield _sse({"type": "_meta", "phase": "awaiting_review", "reason": "doctrine incomplete"})
            done_evt = {
                "type": "done",
                "role": "engineer",
                "bl_id": req.bl_id,
                "task_id": wt.task_id,
                "branch": wt.branch,
                "commit_sha": commit_sha,
                "new_commits": new_commits,
                "agent_branch": cfg.agent_branch,
                "doctrine_ok": validation["ok"],
                "doctrine_missing": validation["missing"],
                "doctrine_empty": validation["empty"],
                "doctrine_attempts": attempt,
                "gate_kind": (gate_result or {}).get("kind"),
                "gate_ok": (gate_result or {}).get("ok"),
                "regressions": (gate_result or {}).get("regressions") or [],
                "merged_to_target": bool(merge_result and merge_result.get("ok")),
                "merge_error": (merge_result or {}).get("error"),
                "trace_dir": str(trace.dir) if trace else None,
            }
            if trace is not None:
                trace.write_event(done_evt)
            yield _sse(done_evt)
        except Exception as exc:  # noqa: BLE001
            err = {"type": "_error", "error": f"{type(exc).__name__}: {exc}"}
            if trace is not None:
                trace.write_event(err)
            yield _sse(err)
        finally:
            if trace is not None:
                trace.close()
            if wt is not None and not req.keep_worktree:
                try:
                    await remove_worktree(repo_dir, wt)
                    yield _sse({"type": "_meta", "phase": "worktree_removed"})
                except Exception as exc:  # noqa: BLE001
                    yield _sse({"type": "_error", "error": f"cleanup: {exc}"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ----------------------- QA / Score on a single BL ---------------------

def _stream_role_on_bl(
    repo_dir,
    bl_id,
    role,
    prompt_builder,
    timeout,
    extra_builder_args=None,
    repo: str = "",
):
    bf = backlog_svc.find_backlog(repo_dir)
    if bf is None:
        raise HTTPException(status_code=400, detail="no BACKLOG.md found")
    section = backlog_svc.extract_section(bf.read_text(encoding="utf-8"), bl_id)
    if section is None:
        raise HTTPException(status_code=404, detail=f"{bl_id} not in backlog")

    prompt = prompt_builder(bl_id, section, **(extra_builder_args or {}))

    async def gen():
        wt = None
        trace: TraceWriter | None = None
        try:
            cfg = repo_config_svc.load(repo_dir)
            wt = await create_worktree(repo_dir, base_ref=cfg.agent_branch)
            trace = TraceWriter(repo=repo or repo_dir.name, role=role, bl_id=bl_id, task_id=wt.task_id)
            wt_evt = {
                "type": "_meta",
                "phase": "worktree_ready",
                "task_id": wt.task_id,
                "branch": wt.branch,
                "bl_id": bl_id,
                "role": role,
                "trace_dir": str(trace.dir),
            }
            trace.write_event(wt_evt)
            yield _sse(wt_evt)
            try:
                rk = _retrieval_kwargs(wt, role=role, bl_id=bl_id, trace=trace)
            except RetrievalUnavailable as e:
                yield _sse({"type": "_meta", "phase": "retrieval", "kind": "unavailable", "reason": str(e)})
                return
            # QA must ground before adding tests; scorer is read-only so no
            # grounding floor (its retrieval is incentivized by the rubric).
            qa_pregrounding = 3 if role == "qa" else 0
            async for event in stream_agent_task(
                prompt,
                wt.path,
                timeout_seconds=timeout,
                trace=trace,
                min_pregrounding=qa_pregrounding,
                **rk,
            ):
                yield _sse(event)
            # ─── Doctrine pre-merge validator (QA + scorer) ───
            validation = {"ok": True, "missing": [], "empty": [], "summary": "n/a"}
            attempt = 0
            if role in ("qa", "scorer"):
                MAX_FIX_RETRIES = 2
                if role == "qa":
                    _validate = lambda: doctrine_svc.validate_qa(
                        wt.path, bl_id, base_ref=cfg.agent_branch,
                        retrieval_log=trace.retrieval_path,
                    )
                else:  # scorer — R7 rubric self-consistency + R12 grounding
                    _validate = lambda: doctrine_svc.validate_scorer(
                        wt.path, bl_id, base_ref=cfg.agent_branch,
                        retrieval_log=trace.retrieval_path,
                    )
                validation = _validate()
                while not validation["ok"] and attempt < MAX_FIX_RETRIES:
                    attempt += 1
                    yield _sse({
                        "type": "_meta",
                        "phase": "doctrine_check",
                        "kind": "incomplete",
                        "attempt": attempt,
                        "missing": validation["missing"],
                        "empty": validation["empty"],
                        "summary": validation["summary"],
                    })
                    fix_prompt = doctrine_svc.build_fix_prompt(role, validation, bl_id=bl_id)
                    async for event in stream_agent_task(
                        fix_prompt,
                        wt.path,
                        timeout_seconds=max(300, timeout // 2),
                        trace=trace,
                        **rk,
                    ):
                        yield _sse(event)
                    validation = _validate()
                yield _sse({
                    "type": "_meta",
                    "phase": "doctrine_check",
                    "kind": "complete" if validation["ok"] else "give_up",
                    "attempts": attempt,
                    "summary": validation["summary"],
                })

            commit_sha = await get_commit_sha(wt)
            new_commits = await has_new_commits(wt, base_ref="HEAD~1")
            merge_result = None
            gate_result = None
            if role == "qa" and validation["ok"] and new_commits > 0:
                gate_result = await regression_gate_svc.run_gate(repo_dir, agent_branch=wt.branch, target_ref=cfg.agent_branch)
                yield _sse({
                    "type": "_meta",
                    "phase": "regression_gate",
                    **{k: gate_result.get(k) for k in ("ok", "kind", "pre", "post", "regressions", "new_failures", "reason", "command", "post_tail", "pre_tail")},
                })
                # R10.1: same gate-failure auto-recovery as the engineer flow.
                MAX_GATE_RETRIES = 2
                gate_attempt = 0
                while (
                    not gate_result.get("ok")
                    and gate_result.get("kind") == "regressed"
                    and gate_attempt < MAX_GATE_RETRIES
                ):
                    gate_attempt += 1
                    fix_prompt = doctrine_svc.build_gate_fix_prompt(
                        "qa", gate_result,
                        bl_id=bl_id, attempt=gate_attempt, max_attempts=MAX_GATE_RETRIES,
                    )
                    async for event in stream_agent_task(
                        fix_prompt,
                        wt.path,
                        timeout_seconds=max(300, timeout // 2),
                        trace=trace,
                        **rk,
                    ):
                        yield _sse(event)
                    validation = doctrine_svc.validate_qa(
                        wt.path, bl_id, base_ref=cfg.agent_branch,
                        retrieval_log=trace.retrieval_path,
                    )
                    if not validation["ok"]:
                        yield _sse({
                            "type": "_meta",
                            "phase": "doctrine_check",
                            "kind": "incomplete_after_gate_fix",
                            "attempt": gate_attempt,
                            "missing": validation["missing"],
                            "empty": validation["empty"],
                            "summary": validation["summary"],
                        })
                        break
                    gate_result = await regression_gate_svc.run_gate(
                        repo_dir, agent_branch=wt.branch, target_ref=cfg.agent_branch,
                    )
                    yield _sse({
                        "type": "_meta",
                        "phase": "regression_gate",
                        "gate_attempt": gate_attempt,
                        **{k: gate_result.get(k) for k in ("ok", "kind", "pre", "post", "regressions", "new_failures", "reason", "command", "post_tail", "pre_tail")},
                    })
                if validation["ok"] and gate_result.get("ok"):
                    merge_result = await fast_forward_target(repo_dir, wt.branch, target_ref=cfg.agent_branch)
                    yield _sse({
                        "type": "_meta",
                        "phase": "merge_to_target",
                        "kind": merge_result.get("kind"),
                        "ok": merge_result.get("ok"),
                        "merged_sha": merge_result.get("merged_sha"),
                        "target_ref": merge_result.get("target_ref"),
                        "error": merge_result.get("error"),
                    })
                else:
                    yield _sse({"type": "_meta", "phase": "awaiting_review", "reason": gate_result.get("reason")})
            done_evt = {
                "type": "done",
                "role": role,
                "bl_id": bl_id,
                "task_id": wt.task_id,
                "branch": wt.branch,
                "commit_sha": commit_sha,
                "new_commits": new_commits,
                "agent_branch": cfg.agent_branch,
                "doctrine_ok": validation["ok"],
                "doctrine_missing": validation["missing"],
                "doctrine_empty": validation["empty"],
                "doctrine_attempts": attempt,
                "gate_kind": (gate_result or {}).get("kind"),
                "gate_ok": (gate_result or {}).get("ok"),
                "regressions": (gate_result or {}).get("regressions") or [],
                "merged_to_target": bool(merge_result and merge_result.get("ok")),
                "merge_error": (merge_result or {}).get("error"),
                "trace_dir": str(trace.dir) if trace else None,
            }
            if trace is not None:
                trace.write_event(done_evt)
            yield _sse(done_evt)
        except Exception as exc:
            err = {"type": "_error", "error": f"{type(exc).__name__}: {exc}"}
            if trace is not None:
                trace.write_event(err)
            yield _sse(err)
        finally:
            if trace is not None:
                trace.close()
            if wt is not None:
                try:
                    await remove_worktree(repo_dir, wt)
                    yield _sse({"type": "_meta", "phase": "worktree_removed"})
                except Exception as exc:
                    yield _sse({"type": "_error", "error": f"cleanup: {exc}"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{repo}/qa-bl")
async def qa_bl(repo: str, req: BLActionRequest):
    repo_dir = _repo_dir(repo)
    _cfg = repo_config_svc.load(repo_dir)
    _family = _cfg.doctrine or prompts_svc.select_family(classify_target(repo_dir))
    return _stream_role_on_bl(
        repo_dir, req.bl_id, role="qa",
        prompt_builder=lambda bl, sec: prompts_svc.build_qa(_family, bl, sec, repo_dir),
        timeout=req.timeout_seconds,
        repo=repo,
    )


@router.post("/{repo}/score-bl")
async def score_bl(repo: str, req: BLActionRequest):
    repo_dir = _repo_dir(repo)
    _cfg = repo_config_svc.load(repo_dir)
    _family = _cfg.doctrine or prompts_svc.select_family(classify_target(repo_dir))
    return _stream_role_on_bl(
        repo_dir, req.bl_id, role="scorer",
        prompt_builder=lambda bl, sec, **_: prompts_svc.build_score(_family, bl, sec, repo_dir),
        timeout=req.timeout_seconds,
        extra_builder_args=None,
        repo=repo,
    )


# ----------------------- ABL-0001 Orchestrator ------------------------
#
# B2 concurrency safeguard: only one /run-brief allowed per repo at a time.
#
# Hard assumption: this process runs as a single uvicorn worker. asyncio.Lock
# is a coroutine-level primitive — it does NOT cross process boundaries. If
# you set WEB_CONCURRENCY>1 or run multiple uvicorn instances against the
# same target repo, two `/run-brief` calls can land on different workers and
# stomp each other. The startup warning below makes this loud.
_RUN_LOCKS: dict[str, asyncio.Lock] = {}
_RUN_META: dict[str, dict] = {}  # repo → {run_id, started_at, current_bl, brief_hash}

_workers_str = os.environ.get("WEB_CONCURRENCY", "") or "1"
try:
    _workers_count = int(_workers_str)
except ValueError:
    _workers_count = 1
if _workers_count > 1:
    print(
        f"[run-brief] WARNING: WEB_CONCURRENCY={_workers_count}; "
        f"the per-repo concurrency lock only protects within ONE worker. "
        f"Set WEB_CONCURRENCY=1 for the /run-brief endpoint to be safe.",
        flush=True,
    )


def _get_run_lock(repo: str) -> asyncio.Lock:
    """Return the process-local asyncio.Lock for this repo, creating on demand."""
    lock = _RUN_LOCKS.get(repo)
    if lock is None:
        lock = asyncio.Lock()
        _RUN_LOCKS[repo] = lock
    return lock


def _brief_hash(brief: str, project_name: str, repo: str) -> str:
    """B9: stable identity for a brief submission. sha256 over the inputs that
    determine what work the run will do — used to detect duplicate POSTs."""
    h = hashlib.sha256()
    h.update(repo.encode("utf-8"))
    h.update(b"\x00")
    h.update(project_name.encode("utf-8"))
    h.update(b"\x00")
    h.update(brief.encode("utf-8"))
    return h.hexdigest()


# A17 brief-persistence helpers were moved into orchestrator._po_flow so the
# brief lands in the target repo's brownfield artifact tree (alongside BACKLOG.md
# and per-BL contexts), not in agentic-skills. The brief describes a target
# feature; the agentic-skills repo holds doctrine, ledger, and invariants only.
# See _persist_brief_in_worktree + _slugify in app.services.orchestrator.


class InitFeatureRequest(BaseModel):
    """Bootstrap a fresh clean-baseline agent branch for a new feature.

    Replaces the manual RUNBOOK_clean_brownfield_reset.md procedure: fork a
    new branch off ``main_ref`` (default: ``master``), apply the harness
    infrastructure (gitignore + scripts/regression_gate.sh + compose.gate.yml),
    write ``.agentic-skills.json`` pointing ``agent_branch`` at the new
    branch, and create the empty ``_brownfield/features/<slug>/`` directory
    ready for ``REQUIREMENTS.md``.
    """

    feature_name: str = Field(..., min_length=2, max_length=120)
    main_ref: str | None = Field(None, description="Override the base ref to fork from; defaults to current .agentic-skills.json main_ref or 'master'.")
    test_cmd: list[str] | None = Field(None, description="Override regression-gate test command; default is ['sh', 'scripts/regression_gate.sh'].")


_HARNESS_GITIGNORE_ENTRIES = (
    "graphify-out",
    "_brownfield/features/*/events.jsonl",
)


def _run_git(repo_dir: Path, *args: str) -> str:
    """Run a git command in repo_dir; raise HTTPException with detail on failure."""
    import subprocess

    res = subprocess.run(
        ["git", *args],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "git_command_failed",
                "cmd": ["git", *args],
                "returncode": res.returncode,
                "stderr": (res.stderr or "").strip()[:500],
                "stdout": (res.stdout or "").strip()[:500],
            },
        )
    return (res.stdout or "").strip()


@router.post("/{repo}/init-feature")
def init_feature(repo: str, req: InitFeatureRequest):
    """Fork a clean-baseline agent branch + apply harness + create feature dir.

    On success returns the slug, the new branch name, the bootstrap commit
    SHA, and the absolute path where the operator should drop their
    REQUIREMENTS.md before submitting via /run-brief.

    Idempotency: this endpoint is **not** idempotent. If the branch already
    exists it returns 409. Re-running after a failed mid-bootstrap requires
    operator cleanup of the partial branch first.
    """
    from app.services.orchestrator import _slugify

    repo_dir = _repo_dir(repo)
    slug = _slugify(req.feature_name)
    if not slug or slug == "untitled":
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_feature_name", "feature_name": req.feature_name},
        )

    # Refuse to clobber uncommitted state.
    status_out = _run_git(repo_dir, "status", "--porcelain")
    if status_out:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "working_tree_dirty",
                "message": "Target repo has uncommitted changes; commit or stash before init-feature.",
                "changes": status_out.splitlines()[:10],
            },
        )

    # Refuse to clobber an existing branch.
    branches = _run_git(repo_dir, "branch", "--list", slug)
    if branches:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "branch_exists",
                "branch": slug,
                "message": f"Branch '{slug}' already exists; delete it or choose a different feature_name.",
            },
        )

    # Resolve main_ref from request > existing .agentic-skills.json > "master".
    main_ref = req.main_ref
    if main_ref is None:
        existing_cfg_path = repo_dir / ".agentic-skills.json"
        if existing_cfg_path.exists():
            try:
                main_ref = json.loads(existing_cfg_path.read_text()).get("main_ref")
            except Exception:
                main_ref = None
        if main_ref is None:
            main_ref = "master"

    # Verify main_ref exists locally.
    refs_check = _run_git(repo_dir, "rev-parse", "--verify", main_ref)
    if not refs_check:
        raise HTTPException(
            status_code=404,
            detail={"error": "main_ref_not_found", "main_ref": main_ref},
        )

    # Checkout main_ref then fork new branch.
    _run_git(repo_dir, "checkout", main_ref)
    _run_git(repo_dir, "checkout", "-b", slug)

    # --- Apply harness ---

    # 1. .gitignore additions (idempotent merge).
    gitignore = repo_dir / ".gitignore"
    existing = gitignore.read_text() if gitignore.exists() else ""
    additions = [e for e in _HARNESS_GITIGNORE_ENTRIES if e not in existing.split("\n")]
    if additions:
        suffix = ("" if existing.endswith("\n") or not existing else "\n") + "\n".join(additions) + "\n"
        gitignore.write_text(existing + suffix)

    # 2. scripts/regression_gate.sh + compose.gate.yml from canonical templates.
    templates_dir = Path(__file__).resolve().parents[1] / "templates"
    scripts_dir = repo_dir / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    gate_sh = scripts_dir / "regression_gate.sh"
    gate_sh.write_text((templates_dir / "regression_gate.sh").read_text())
    gate_sh.chmod(0o755)
    (repo_dir / "compose.gate.yml").write_text(
        (templates_dir / "compose.gate.yml").read_text()
    )

    # 3. .agentic-skills.json with agent_branch pointing at the new slug.
    test_cmd = req.test_cmd or ["sh", "scripts/regression_gate.sh"]
    cfg = {
        "agent_branch": slug,
        "main_ref": main_ref,
        "doctrine": "brownfield",
        "test_cmd": test_cmd,
    }
    (repo_dir / ".agentic-skills.json").write_text(json.dumps(cfg, indent=2) + "\n")

    # 4. Feature artifact directory + .gitkeep so the empty dir survives commit.
    feature_dir = repo_dir / "_brownfield" / "features" / slug
    feature_dir.mkdir(parents=True, exist_ok=True)
    keep = feature_dir / ".gitkeep"
    if not keep.exists():
        keep.write_text("")

    # Commit it all on the new branch.
    _run_git(repo_dir, "add", "-A")
    commit_msg = (
        f"chore({slug}): bootstrap feature branch from {main_ref}\n\n"
        f"Initialized via POST /api/projects/{repo}/init-feature.\n"
        f"- forked from {main_ref}\n"
        f"- harness: .gitignore + scripts/regression_gate.sh + compose.gate.yml\n"
        f"- .agentic-skills.json agent_branch={slug}\n"
        f"- _brownfield/features/{slug}/ (drop REQUIREMENTS.md here)\n"
    )
    _run_git(repo_dir, "commit", "-m", commit_msg)
    branch_sha = _run_git(repo_dir, "rev-parse", "HEAD")

    return {
        "slug": slug,
        "agent_branch": slug,
        "main_ref": main_ref,
        "branch_sha": branch_sha,
        "bootstrap_commit": branch_sha,
        "requirements_path": str(feature_dir / "REQUIREMENTS.md"),
        "feature_dir": str(feature_dir),
    }


class RunBriefRequest(BaseModel):
    brief: str = Field(..., min_length=20)
    project_name: str | None = None
    timeout_per_role: int = Field(2400, ge=60, le=7200)
    max_bls: int | None = Field(None, ge=1, le=50)
    skip_po: bool = False
    stop_on_failure: bool = True
    # A2: when True, a BL whose QA gives up on doctrine after 2 retries
    # aborts the sprint (instead of silently being marked merged_no_qa
    # and the loop continuing). Default False preserves prior behavior.
    stop_on_qa_doctrine_failure: bool = False
    # A4: skip BLs until this id, then resume. Convenience for backfilling a
    # specific BL after a mid-sprint scorer/qa abort (e.g. Sprint 3 BL-0002
    # had no scorer because the orchestrator died during reindex).
    start_bl: str | None = None
    # B-3 / I-7: run the doctrine-meta-agent after sprint_complete. Default
    # True — the self-hardening loop should be on for any real sprint. Set
    # False for short test runs where the post-sprint analysis adds latency
    # without value.
    run_doctrine_meta: bool = True
    # ABL-0014: acceptance pass — DEFAULT ON (2026-05-31).
    # Flipped after 3 clean calibration smokes against time-tracking
    # (smoke-20260530T161537Z, smoke-20260531T022625Z, smoke-20260531T034747Z):
    # smoke #3 hit validator_ok=True on attempt 1 with zero leaked
    # resources. Calibration data confirmed agent's natural output shape +
    # advisory-only semantics. §E.1 Q2: 3600s default timeout.
    run_acceptance: bool = True
    acceptance_timeout: int = Field(3600, ge=300, le=10800)
    # ABL-0014 Item 2 (Batch C, 2026-06-01): operator-tunable UI-coverage
    # floor. When 0.0 (default), the orchestrator emits the coverage
    # breakdown as informational only — sprint_complete fires with
    # coverage_subtype="full" regardless. When > 0.0, sprint_complete
    # carries coverage_subtype="partial" if the merged ratio of UI-touching
    # BLs falls below the threshold. This is operator-visibility, not a
    # gate: terminal_status remains "sprint_complete" either way (the
    # framework already merged everything; partial is a UX signal that the
    # assembled product may not be usable end-to-end from the user seat).
    min_ui_coverage_ratio: float = Field(0.0, ge=0.0, le=1.0)
    # ABL-0014 §I.3 Batch E (2026-06-01): inject classifier-accuracy priors
    # from the findings ledger into the acceptance agent's spawn prompt.
    # Default OFF until the 3-smoke calibration discipline (§I.1) clears
    # the flip; mirrors the run_acceptance default-OFF→ON history.
    inject_acceptance_priors: bool = False
    # ABL-0015 (2026-06-02): auto-dispatch a follow-up engineer on
    # operator-confirmed product_bug acceptance findings. Default OFF —
    # this is the framework's highest-risk action (acceptance becomes a
    # writer; engineer gets non-PO work). Flipped only after a live
    # calibration smoke per ABL-0015_AUTO_DISPATCH_DESIGN.md §11 Batch E.
    run_acceptance_followup: bool = False
    # ABL-0016 cumulative learning: inject prior operator-confirmed lessons
    # (target-scoped findings ledger) into the brownfield role prompts as
    # advisory context, plus the Stage 1.5 search_lessons / ABL-0019
    # search_patterns pull tools. DEFAULT ON (2026-06-08) — flipped after the
    # calibration smoke (run-20260608T162952Z-ed37bc, beaverhabits) passed
    # clean: lessons injected into all roles across 2/2 merged_full BLs,
    # regression checkpoint green (126 passed, 0 regressions). Advisory-only,
    # so un-gating is safe (agents ground against current code). Set False to
    # roll back. Mirrors the run_acceptance default-OFF→ON history.
    inject_lessons: bool = True
    # ABL-0018 Stage 3 cross-target ("community") push. Independent flag (higher
    # blast radius than per-target lessons → separate rollout). DEFAULT OFF until
    # the read-path smoke confirms global lessons render + no regression.
    inject_global_lessons: bool = False
    # ABL-0002 Stage 1: spawn the Architect to ADJUDICATE a code-gate exhaustion
    # (retry_reframed / defer / escalate) instead of halting the sprint. DEFAULT OFF
    # until live-proven on a hard feature.
    run_architect: bool = False
    # Wave-execution Phase 2 (operator 2026-06-14): schedule BLs by the R21
    # dependency DAG into topological waves + emit wave.start/done boundaries.
    # Phase 2 runs each wave at concurrency=1 (identical per-BL semantics); OFF =
    # today's flat sequential order. DEFAULT OFF (rollback) until live-proven.
    wave_execution: bool = False
    # Wave concurrency (PROPOSAL_WAVE_CONCURRENCY.md, Strategy A). Max BLs run
    # concurrently within a wave. DEFAULT 1 = byte-identical to the live-proven
    # serial scaffolding; >1 is opt-in intra-wave concurrency (Strategy A fan-in +
    # BL-id-ordered barrier assembly), LIVE-PROVEN 2026-06-15: happy-path,
    # conflicting-pair, and 3-wide/multi-wave scale.
    wave_concurrency: int = Field(1, ge=1, le=16)
    # Reindex incremental short-circuit (operator 2026-06-15). The claude-context
    # barrier reindexes embed only changed files (op=reindex) after a full
    # index_baseline at index_initial, instead of a full re-embed each barrier.
    # DEFAULT ON (live-proven); set False for the byte-identical full-index rollback.
    reindex_incremental: bool = True
    # A48 pre-flight disk-free check (2026-06-01). Default advisory:
    # the check ALWAYS runs and emits an SSE event with the breakdown,
    # but only refuses the run (HTTP 409) when enforce=True. This
    # matches the "operator opts in to gating" pattern used elsewhere
    # (min_ui_coverage_ratio, stop_on_qa_doctrine_failure) so backward
    # compat is preserved while operators can dial in stricter policy.
    enforce_disk_preflight: bool = False
    min_free_disk_gb: float = Field(
        disk_preflight_svc.DEFAULT_MIN_FREE_GB, ge=0.0, le=10000.0,
    )
    per_bl_disk_gb: float = Field(
        disk_preflight_svc.DEFAULT_PER_BL_GB, ge=0.0, le=100.0,
    )
    # A18: per-feature isolation. Operator-supplied feature name; server
    # slugifies it and creates <target>/_brownfield/features/<slug>/ which
    # holds the brief, BACKLOG.md, CODEBASE_CONTEXT.md, SPRINT_PLAN.md, the
    # per-BL artifacts, and the tailable events.jsonl. Required for new
    # sprints; legacy /run-brief invocations that omit this field fall back
    # to the pre-A18 path layout.
    feature_name: str | None = Field(None, min_length=1, max_length=120)
    # A56: warm the LOCAL retrieval backend before the PO so the first agent
    # isn't grounding-blind. Default ON; set False to disable (rollback knob).
    warm_retrieval: bool = True


class OnboardRequest(BaseModel):
    # Optional: the upcoming feature brief, passed as CONTEXT so the onboarder
    # can anticipate what services/deps the work will need. The onboarder never
    # builds the feature — it only prepares the environment.
    brief: str | None = Field(None, max_length=20000)
    # Per-agent wall-clock budget (onboarding can install deps + boot a DB).
    timeout: int = Field(3600, ge=300, le=14400)


@router.post("/{repo}/onboard")
async def onboard(repo: str, req: OnboardRequest):
    """Onboard a brand-new target repo (the Janitor/Ops-Steward in ONBOARDING
    MODE). Fulfils the environment prerequisites a `git clone` doesn't bring —
    dependencies, runtime/toolchain, services/DB, gitignored config, missing
    migrations — then wires the gate config + harness hygiene + integration
    branch and verifies the target builds/boots and `test_cmd` executes. It
    PROVISIONS THE ENVIRONMENT and never edits the target's committed source.

    Operator-invoked (no auto-trigger). Single SSE stream; the orchestrator
    independently verifies the onboarding postconditions before reporting
    `onboarding.done` (vs `onboarding.escalated`)."""
    repo_dir = _repo_dir(repo)
    run_id = f"onboard-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"

    async def _gen():
        yield _sse({"type": "_meta", "phase": "onboard.accepted", "run_id": run_id, "repo": repo})
        try:
            async for event in orchestrator_svc.run_onboarding(
                repo_dir, repo, run_id, brief=req.brief, timeout=req.timeout,
            ):
                if "_orchestrator_outcome" in event:
                    yield _sse({"type": "_meta", "phase": "onboard.outcome",
                                "status": event.get("status"),
                                "agent_status": event.get("agent_status"),
                                "verify": event.get("verify")})
                    continue
                yield _sse(event)
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "_error", "error": f"onboard: {exc}"})

    return StreamingResponse(_gen(), media_type="text/event-stream")


@router.post("/{repo}/run-brief")
async def run_brief(repo: str, req: RunBriefRequest):
    """ABL-0001 Orchestrator entry point.

    Single SSE stream covering the full pipeline:
    index → PO → for each BL: engineer → reindex → QA → reindex → scorer.

    Each event carries `phase=orchestrator.<step>` (or a per-role phase tagged
    with `orchestrator_step`) so the v2 UI can render a live timeline.
    """
    repo_dir = _repo_dir(repo)

    # A48 pre-flight disk-free check (filed 2026-05-31, fix #1 of 4
    # shipped 2026-06-01). Runs BEFORE any lock acquisition so it
    # fails fast and never holds state for a sprint that can't run.
    # Advisory by default: result is emitted as a `pre_flight.disk`
    # SSE event below; only refuses (HTTP 409) when
    # enforce_disk_preflight=True. Backward-compat: default opts the
    # operator into visibility but not gating.
    pre_flight = disk_preflight_svc.check(
        repo_dir,
        min_free_gb=req.min_free_disk_gb,
        per_bl_gb=req.per_bl_disk_gb,
        n_bls=req.max_bls,
    )
    if req.enforce_disk_preflight and not pre_flight.ok:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "pre_flight.insufficient_disk",
                "repo": repo,
                **pre_flight.to_event(),
            },
        )

    # B9: stable identity for THIS submission. Lets B2's 409 distinguish a
    # duplicate (same brief resubmitted) from a contention (different brief
    # while one is running) and gives operators a way to dedupe retries.
    project_name = req.project_name or repo
    brief_hash = _brief_hash(req.brief, project_name, repo)

    # B2: refuse concurrent run for same repo. Sync `locked()` + acquire are
    # atomic from a coroutine perspective (no await between them).
    lock = _get_run_lock(repo)
    existing_meta = dict(_RUN_META.get(repo) or {})
    if existing_meta.get("brief_hash") == brief_hash and lock.locked():
        # Exact same brief is already running → idempotent 409.
        raise HTTPException(
            status_code=409,
            detail={
                "error": "duplicate-brief",
                "repo": repo,
                **existing_meta,
            },
        )
    if lock.locked():
        raise HTTPException(
            status_code=409,
            detail={
                "error": "run-in-progress",
                "repo": repo,
                **existing_meta,
            },
        )

    # A7: detect orphaned disk state from a prior process that crashed mid-run.
    # If skip_po=True, the operator has signaled "this is a deliberate resume"
    # — reuse the orphan's run_id so checkpoints + traces stay correlated.
    # If skip_po=False, refuse with a hint so we don't clobber the prior run's
    # PO output by re-running PO on top of an existing BACKLOG.md.
    orphan = run_state_svc.find_active(repo, brief_hash) if not lock.locked() else None
    if orphan is not None and not req.skip_po:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "orphaned-run-detected",
                "repo": repo,
                "orphan_run_id": orphan.get("run_id"),
                "orphan_started_at": orphan.get("started_at"),
                "orphan_current_bl": orphan.get("current_bl"),
                "orphan_completed_bls": [o.get("bl_id") for o in (orphan.get("bl_outcomes") or [])],
                "hint": (
                    "A prior /run-brief for this repo + brief crashed mid-run. "
                    "Re-POST with skip_po=true to resume (orchestrator will short-circuit "
                    "already-merged BLs and re-run QA where missing). "
                    "Or rm webapp/backend/.orchestrator-state/<orphan_run_id>.json to discard."
                ),
            },
        )

    await lock.acquire()
    if orphan is not None and req.skip_po:
        # Reuse the prior run's identity so trace archival + state file move
        # land in the right place.
        run_id = orphan["run_id"]
    else:
        run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
    _RUN_META[repo] = {
        "run_id": run_id,
        "started_at": time.time(),
        "brief_hash": brief_hash,
        "resumed_from_orphan": bool(orphan is not None and req.skip_po),
    }

    # A18: derive feature_slug from feature_name; create the per-feature
    # artifact dir on the target so the events.jsonl appender can write to
    # it from the very first event. Falls back to None (legacy layout) when
    # the caller omitted feature_name.
    feature_slug: str | None = None
    feature_dir_abs: Path | None = None
    if req.feature_name:
        from app.services.orchestrator import _slugify as _orch_slugify
        feature_slug = _orch_slugify(req.feature_name)
        feature_dir_abs = repo_dir / "_brownfield" / "features" / feature_slug
        feature_dir_abs.mkdir(parents=True, exist_ok=True)

    def _rk_builder(wt: Worktree, role: str, bl_id: str | None, trace: TraceWriter | None) -> dict:
        # Reuses the same preflight + path conventions as the per-role endpoints.
        # repo_dir is the stable main checkout (worktrees fork off it) → use it
        # as the lessons key/ledger source for ABL-0016 Stage 1.5 search_lessons.
        return _retrieval_kwargs(wt, role=role, bl_id=bl_id, trace=trace, lessons_repo=repo_dir)

    async def gen():
        # A18: tailable per-feature event log. Open in append mode so re-runs
        # of the same feature accumulate history. The framework / harness can
        # `tail -F` this file to follow sprint progress regardless of whether
        # the run was kicked off via webapp UI or curl.
        events_fh = None
        if feature_dir_abs is not None:
            try:
                events_fh = open(feature_dir_abs / "events.jsonl", "a", buffering=1, encoding="utf-8")
            except OSError:
                events_fh = None

        def _persist_event(evt: dict) -> None:
            if events_fh is None:
                return
            try:
                rec = dict(evt)
                rec.setdefault("_persisted_at", datetime.now(timezone.utc).isoformat())
                rec.setdefault("run_id", run_id)
                events_fh.write(json.dumps(rec, default=str) + "\n")
            except (ValueError, TypeError, OSError):
                pass

        # A48 pre-flight disk advisory — always first event in the
        # stream so operators see the disk state before any heavy
        # subprocess fires. Emitted regardless of enforce flag; the
        # HTTP 409 path above handles the enforce-and-blocked case.
        _pre_flight_evt = {
            "type": "_meta",
            "phase": "orchestrator.pre_flight.disk",
            "run_id": run_id,
            "enforce": req.enforce_disk_preflight,
            **pre_flight.to_event(),
        }
        _persist_event(_pre_flight_evt)
        yield _sse(_pre_flight_evt)

        # A17/A18: the per-role brief_persisted SSE event is emitted from
        # inside _po_flow once the worktree exists and the brief has been
        # written under <target>/_brownfield/features/<slug>/brief.md.
        try:
            async for event in orchestrator_svc.run_brief(
                repo_dir=repo_dir,
                repo_name=repo,
                brief=req.brief,
                project_name=project_name,
                retrieval_kwargs_builder=_rk_builder,
                timeout_per_role=req.timeout_per_role,
                max_bls=req.max_bls,
                skip_po=req.skip_po,
                stop_on_failure=req.stop_on_failure,
                stop_on_qa_doctrine_failure=req.stop_on_qa_doctrine_failure,
                # A7: share run_id with the router's lock metadata so the disk
                # state file, trace archive dir, and 409 detail all line up.
                run_id=run_id,
                brief_hash=brief_hash,
                start_bl=req.start_bl,
                run_doctrine_meta=req.run_doctrine_meta,
                feature_slug=feature_slug,
                run_acceptance=req.run_acceptance,
                inject_acceptance_priors=req.inject_acceptance_priors,
                run_acceptance_followup=req.run_acceptance_followup,
                inject_lessons=req.inject_lessons,
                inject_global_lessons=req.inject_global_lessons,
                run_architect=req.run_architect,
                warm_retrieval=req.warm_retrieval,
                acceptance_timeout=req.acceptance_timeout,
                min_ui_coverage_ratio=req.min_ui_coverage_ratio,
                wave_execution=req.wave_execution,
                wave_concurrency=req.wave_concurrency,
                reindex_incremental=req.reindex_incremental,
            ):
                # Track current_bl from bl.start so 409 responses can name it.
                if event.get("phase") == "orchestrator.bl.start":
                    meta = _RUN_META.get(repo)
                    if meta is not None:
                        meta["current_bl"] = event.get("bl_id")
                _persist_event(event)
                yield _sse(event)
        except RetrievalUnavailable as e:
            yield _sse({"type": "_meta", "phase": "orchestrator.aborted",
                       "reason": f"retrieval unavailable: {e}"})
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "_error", "error": f"{type(exc).__name__}: {exc}"})
        finally:
            # B2: release lock + clear meta on every exit path (success, abort,
            # consumer disconnect). asyncio.Lock dies with the process anyway,
            # so a kill -9 self-clears.
            _RUN_META.pop(repo, None)
            if lock.locked():
                lock.release()
            if events_fh is not None:
                try:
                    events_fh.close()
                except OSError:
                    pass

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ----------------------- manual review / merge ------------------------

class MergeBranchRequest(BaseModel):
    branch: str
    skip_gate: bool = False


@router.post("/{repo}/merge-branch")
async def merge_branch(repo: str, req: MergeBranchRequest):
    """Manually trigger the regression gate + fast-forward for an agent branch.

    Used by the UI's 'Review & merge' button when an earlier run left a
    branch behind (gate red, or non-FF, or QA verdict not PASS).
    """
    repo_dir = _repo_dir(repo)
    cfg = repo_config_svc.load(repo_dir)
    if req.skip_gate:
        merge = await fast_forward_target(repo_dir, req.branch, target_ref=cfg.agent_branch)
        return {"gate": {"kind": "skipped"}, "merge": merge,
                "ledger_synced": _sync_followup_ledger(repo_dir, req.branch, merge)}
    gate = await regression_gate_svc.run_gate(repo_dir, agent_branch=req.branch, target_ref=cfg.agent_branch)
    if not gate.get("ok"):
        return {"gate": gate, "merge": None}
    merge = await fast_forward_target(repo_dir, req.branch, target_ref=cfg.agent_branch)
    return {"gate": gate, "merge": merge,
            "ledger_synced": _sync_followup_ledger(repo_dir, req.branch, merge)}


def _sync_followup_ledger(repo_dir, branch: str, merge: dict):
    """A50: after a successful merge of a follow-up dispatch branch, close the
    owning finding's dispatch lifecycle (dispatch_state → "merged") so the
    findings ledger reflects the merge an out-of-band review-&-merge produced.

    Best-effort: returns the sync result dict (or None when not applicable /
    the merge didn't land); never raises — the merge already happened.
    """
    if not (merge and merge.get("ok") and merge.get("merged_sha")):
        return None
    return findings_ledger_svc.sync_followup_merge_to_ledger(
        repo_dir, branch, merge.get("merged_sha"),
    )


# ----------------------- end-sprint (operator kill + cleanup) ---------

class EndSprintRequest(BaseModel):
    """Operator 'End current Sprint': stop the run + full backend cleanup.

    The running sprint is killed CLIENT-side (the UI aborts the SSE, which the
    orchestrator treats as a consumer disconnect → the run ends and its own
    finally-blocks reap the in-flight worktree). This endpoint does the
    server-side sweep that a hard stop can leave behind: reap any agent/gate
    worktrees, tear down leftover docker compose stacks + their volumes,
    archive live orchestrator run-state, optionally purge the run-scoped
    docker images that are no longer needed, and clear the per-repo run lock
    so a fresh /run-brief isn't blocked.
    """
    purge_images: bool = True


@router.post("/{repo}/end-sprint")
async def end_sprint(repo: str, req: EndSprintRequest):
    """Kill-aftermath cleanup for a repo (idempotent; safe when nothing runs)."""
    repo_dir = _repo_dir(repo)
    summary = await asyncio.to_thread(_end_sprint_cleanup, repo_dir, req.purge_images)
    # Clear in-process run bookkeeping so a stale B2 lock/meta from a hard
    # client disconnect doesn't 409 the next /run-brief.
    _RUN_META.pop(repo, None)
    lock = _RUN_LOCKS.get(repo)
    if lock is not None and lock.locked():
        try:
            lock.release()
        except RuntimeError:
            pass
    summary["lock_cleared"] = True
    return summary


def _end_sprint_cleanup(repo_dir: Path, purge_images: bool) -> dict:
    """Synchronous end-sprint sweep (runs in a worker thread). Best-effort:
    each stage is independently guarded so one failure doesn't abort the rest."""
    import subprocess

    summary: dict = {
        "worktrees_removed": [], "stacks_reaped": [], "images_removed": 0,
        "state_archived": [], "errors": [],
    }

    def _git(*args, timeout=60):
        return subprocess.run(["git", *args], cwd=str(repo_dir),
                              capture_output=True, text=True, timeout=timeout)

    def _docker(*args, timeout=120):
        return subprocess.run(["docker", *args], capture_output=True,
                              text=True, timeout=timeout)

    # 1) Reap agent/gate worktrees left under the target repo.
    try:
        wl = _git("worktree", "list", "--porcelain")
        for ln in wl.stdout.splitlines():
            if not ln.startswith("worktree "):
                continue
            path = ln[len("worktree "):].strip()
            if "/.agent-worktrees/" in path or "/.gate-worktrees/" in path:
                _git("worktree", "remove", "--force", path)
                summary["worktrees_removed"].append(path.rsplit("/", 1)[-1])
        _git("worktree", "prune")
    except Exception as exc:  # noqa: BLE001
        summary["errors"].append(f"worktrees: {type(exc).__name__}: {exc}")

    # 2) Tear down leftover orchestrator / acceptance docker compose stacks
    #    (containers + their anonymous volumes), matched by project label.
    try:
        ps = _docker("ps", "-a", "--format",
                     '{{.Label "com.docker.compose.project"}}')
        projects = {ln.strip() for ln in ps.stdout.splitlines()
                    if ln.strip() and (ln.startswith("agentic-skills-")
                                       or ln.startswith("acceptance-"))}
        for proj in sorted(projects):
            ids = _docker("ps", "-aq", "--filter",
                          f"label=com.docker.compose.project={proj}").stdout.split()
            if ids:
                _docker("rm", "-f", *ids)
            vols = _docker("volume", "ls", "-q", "--filter",
                           f"label=com.docker.compose.project={proj}").stdout.split()
            if vols:
                _docker("volume", "rm", "-f", *vols)
            summary["stacks_reaped"].append(proj)
    except Exception as exc:  # noqa: BLE001
        summary["errors"].append(f"stacks: {type(exc).__name__}: {exc}")

    # 3) Purge run-scoped gate/acceptance images no longer needed (skip any
    #    still referenced by a running container).
    if purge_images:
        try:
            in_use = set(_docker("ps", "--format", "{{.Image}}").stdout.split())
            seen: set[str] = set()
            for row in _docker("images", "--format", "{{.ID}}\t{{.Repository}}").stdout.splitlines():
                if "\t" not in row:
                    continue
                iid, name = row.split("\t", 1)
                if ((name.startswith("agentic-skills-") or name.startswith("acceptance-"))
                        and name not in in_use and iid not in seen):
                    if _docker("rmi", "-f", iid).returncode == 0:
                        summary["images_removed"] += 1
                        seen.add(iid)
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append(f"images: {type(exc).__name__}: {exc}")

    # 4) Archive live orchestrator run-state → done/.
    try:
        state_dir = Path(__file__).resolve().parents[2] / ".orchestrator-state"
        if state_dir.is_dir():
            done = state_dir / "done"
            for f in state_dir.glob("*.json"):
                done.mkdir(exist_ok=True)
                f.rename(done / f.name)
                summary["state_archived"].append(f.name)
    except Exception as exc:  # noqa: BLE001
        summary["errors"].append(f"state: {type(exc).__name__}: {exc}")

    return summary


# ----------------------- doctrine-meta (B-4 / I-7) --------------------

class RunDoctrineMetaRequest(BaseModel):
    """B-4: invoke the doctrine-meta-agent against an already-archived run.

    Use this to re-mine a past sprint's traces for doctrine proposals — e.g.
    after editing the doctrine_meta SKILLS.md, or to backfill if the post-
    sprint hook was disabled (run_doctrine_meta=False) on the original run.
    """
    run_id: str = Field(..., min_length=1)
    timeout_seconds: int = Field(2400, ge=60, le=7200)


@router.post("/{repo}/run-doctrine-meta")
async def run_doctrine_meta(repo: str, req: RunDoctrineMetaRequest):
    """Stream the doctrine-meta-agent against traces_archive/<run_id>/.

    Read-only against trace data; writes proposal markdown files under
    .planning/doctrine_proposals/. Never modifies code or doctrine. Operator
    approval is required before any proposal becomes a doctrine change.
    """
    repo_dir = _repo_dir(repo)
    if not repo_dir.exists():
        raise HTTPException(status_code=404, detail=f"repo not found: {repo}")

    async def gen():
        try:
            async for event in orchestrator_svc._doctrine_meta_flow(
                repo_name=repo,
                run_id=req.run_id,
                timeout=req.timeout_seconds,
            ):
                yield _sse(event)
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "_error", "error": f"{type(exc).__name__}: {exc}"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class RunAcceptanceRequest(BaseModel):
    """ABL-0014: invoke the acceptance agent against an already-shipped feature.

    Use this to smoke-test the acceptance pass on its own (without re-running
    the BL pipeline) — e.g. the calibration smokes required before flipping
    ``run_acceptance=True`` to the default in ``RunBriefRequest``.

    Requires:
    - ``<target>/_brownfield/features/<feature_slug>/brief.md`` exists
    - The merged ``agent_branch`` carries the feature
    - No regression-gate docker stack is up for ``run_id`` (else skipped)
    """
    run_id: str = Field(..., min_length=1)
    feature_slug: str = Field(..., min_length=1)
    acceptance_timeout: int = Field(3600, ge=300, le=10800)
    # ABL-0014 Item 1 Batch B (2026-06-01): override the auto-computed
    # backend BL list (e.g. for re-runs against a fixed scope or for
    # testing). When None, the orchestrator computes it from the merged
    # agent_branch via `_compute_backend_bls`. An EMPTY list means
    # "pure-frontend sprint — skip API validation entirely."
    backend_bls_override: list[str] | None = None
    # ABL-0014 §I.3 Batch E (2026-06-01): inject classifier-accuracy priors
    # from the findings ledger into the agent's spawn prompt. Default OFF
    # until the 3-smoke calibration discipline (§I.1) clears the flip.
    inject_acceptance_priors: bool = False


@router.post("/{repo}/run-acceptance")
async def run_acceptance(repo: str, req: RunAcceptanceRequest):
    """Stream the acceptance agent against an existing feature.

    Standalone entry point that mirrors ``/run-doctrine-meta``: bypasses
    the BL loop and invokes ``_acceptance_flow`` directly. Read-only on
    code; writes outputs under
    ``<target>/_brownfield/features/<feature_slug>/acceptance/`` and
    archives a copy at
    ``webapp/backend/traces_archive/<run_id>/acceptance/``.
    """
    repo_dir = _repo_dir(repo)
    if not repo_dir.exists():
        raise HTTPException(status_code=404, detail=f"repo not found: {repo}")

    async def gen():
        try:
            async for event in orchestrator_svc._acceptance_flow(
                repo_dir=repo_dir,
                repo_name=repo,
                run_id=req.run_id,
                feature_slug=req.feature_slug,
                timeout=req.acceptance_timeout,
                backend_bls_override=req.backend_bls_override,
                inject_acceptance_priors=req.inject_acceptance_priors,
            ):
                yield _sse(event)
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "_error", "error": f"{type(exc).__name__}: {exc}"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{repo}/branches")
async def list_branches(repo: str):
    """List agent/* branches that have not been merged into the configured agent_branch."""
    import subprocess
    repo_dir = _repo_dir(repo)
    cfg = repo_config_svc.load(repo_dir)
    proc = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname:short)%09%(objectname:short)%09%(committerdate:iso8601)", "refs/heads/agent/"],
        cwd=str(repo_dir), capture_output=True, text=True,
    )
    rows = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        branch, sha, when = parts
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", branch, cfg.agent_branch],
            cwd=str(repo_dir), capture_output=True,
        )
        if ancestor.returncode == 0:
            continue  # already merged
        rows.append({"branch": branch, "sha": sha, "when": when})
    rows.sort(key=lambda r: r["when"], reverse=True)
    return {"agent_branch": cfg.agent_branch, "unmerged": rows}


# ----------------------- traces ----------------------------------------

@router.get("/{repo}/traces")
async def list_repo_traces(repo: str, limit: int = 100):
    """Recent agent-run trace summaries for this repo (newest first)."""
    _repo_dir(repo)  # validate
    return {"traces": list_traces(repo=repo, limit=limit)}


@router.get("/{repo}/traces/{trace_id}")
async def get_trace(repo: str, trace_id: str):
    """Return meta + stream + retrieval log for a single trace.

    trace_id is the directory name (last path segment of meta.trace_dir).
    """
    _repo_dir(repo)
    from app.services.traces import TRACES_ROOT, _slug
    base = (TRACES_ROOT / _slug(repo) / trace_id).resolve()
    if not str(base).startswith(str(TRACES_ROOT.resolve())) or not base.is_dir():
        raise HTTPException(status_code=404, detail="trace not found")
    meta_path = base / "meta.json"
    stream_path = base / "stream.jsonl"
    retrieval_path = base / "retrieval.jsonl"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="trace meta missing")
    meta = json.loads(meta_path.read_text())
    stream = []
    if stream_path.exists():
        for line in stream_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                stream.append(json.loads(line))
            except json.JSONDecodeError:
                stream.append({"_unparsed": line})
    retrieval = []
    if retrieval_path.exists():
        for line in retrieval_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                retrieval.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return {"meta": meta, "stream": stream, "retrieval": retrieval}


# ─── ABL-0014 §I.3 Batch C: findings ledger endpoints ─────────────────────
#
# Operator triage surface for acceptance findings. The ledger is owned by
# app.services.findings_ledger and populated by orchestrator._acceptance_flow
# (Batch B). These endpoints expose read + verdict-write for the AppV2
# triage panel shipping in Batch D, and (later) for the ABL-0015 auto-
# dispatch reader.

import re as _re
from enum import Enum as _Enum

# Slug grammar matches what /init-feature accepts and what SKILLS.md
# documents. Anchored to prevent path-traversal via "../" or absolute
# paths landing in FindingsLedger(repo_root, slug).
_SLUG_RE = _re.compile(r"^[a-z0-9_][a-z0-9_-]{0,127}$")


def _validate_feature_slug(slug: str) -> None:
    if not _SLUG_RE.match(slug):
        raise HTTPException(
            status_code=400,
            detail=(
                "invalid feature_slug: must match [a-z0-9_][a-z0-9_-]{0,127} "
                "(prevents path traversal into the ledger directory)"
            ),
        )


class _Verdict(str, _Enum):
    confirmed = "confirmed"
    refuted = "refuted"
    deferred = "deferred"


class VerdictRequest(BaseModel):
    feature_slug: str = Field(..., min_length=1, max_length=128)
    finding_id: str = Field(..., min_length=1)
    verdict: _Verdict
    note: str | None = None


@router.get("/{repo}/findings")
async def list_findings(repo: str, feature_slug: str, status: str = "pending"):
    """List findings from the per-feature acceptance ledger.

    ``status=pending`` (default) returns only un-verdict'd findings —
    what the AppV2 triage panel needs by default. ``status=all`` returns
    everything (used for the audit view and the ABL-0015 prior loader).

    Returns ``[]`` (not 404) when the ledger file doesn't exist yet, so
    the UI can call this unconditionally on every feature.
    """
    if status not in ("pending", "all"):
        raise HTTPException(
            status_code=400,
            detail="status must be 'pending' or 'all'",
        )
    repo_dir = _repo_dir(repo)
    _validate_feature_slug(feature_slug)
    ledger = findings_ledger_svc.FindingsLedger(repo_dir, feature_slug)
    method = ledger.list_pending if status == "pending" else ledger.list_all
    findings = await asyncio.to_thread(method)
    # Pydantic-free serialization: dataclass → dict via asdict (already in
    # Finding.to_jsonl, but we want a dict here, not a JSON string).
    from dataclasses import asdict as _asdict
    return {"findings": [_asdict(f) for f in findings], "count": len(findings)}


@router.post("/{repo}/verdict")
async def set_finding_verdict(repo: str, req: VerdictRequest):
    """Record an operator verdict on a finding.

    Verdict semantics:
      - confirmed: classifier was right; this is a real bug — eligible
        for ABL-0015 auto-dispatch (Batch B of §I.4).
      - refuted: classifier was wrong; finding will count against the
        classification's accuracy prior (Batch E).
      - deferred: real but intentionally deferred (e.g., post-MVP).

    Returns the updated finding on success. 404 if finding_id is unknown
    to the ledger.
    """
    repo_dir = _repo_dir(repo)
    _validate_feature_slug(req.feature_slug)
    ledger = findings_ledger_svc.FindingsLedger(repo_dir, req.feature_slug)
    try:
        updated = await asyncio.to_thread(
            ledger.set_verdict,
            req.finding_id,
            req.verdict.value,
            req.note,
        )
    except ValueError as exc:
        # Two paths raise ValueError: unknown finding_id (404) and invalid
        # verdict enum (422-ish — but Pydantic already caught it; defensive).
        msg = str(exc)
        if "unknown finding_id" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    from dataclasses import asdict as _asdict
    return {"finding": _asdict(updated)}


class DispatchFollowupRequest(BaseModel):
    feature_slug: str = Field(..., min_length=1, max_length=128)
    finding_id: str = Field(..., min_length=1)
    timeout_seconds: int = Field(3600, ge=60, le=7200)


@router.post("/{repo}/dispatch-followup")
async def dispatch_followup(repo: str, req: DispatchFollowupRequest):
    """ABL-0021: operator-triggered on-demand follow-up engineer dispatch
    on ONE confirmed product_bug finding — the triage panel's "Dispatch fix"
    button.

    Reuses the ABL-0015 dispatch machinery unchanged (the follow-up engineer
    clears the same doctrine + regression gate + auto-merge bar as any BL;
    R15 dispatch-at-most-once). Eligibility is pre-validated for clean HTTP
    codes; then the follow-up engineer is SSE-streamed
    (``acceptance.followup.{start,done}`` + engineer sub-events). The
    operator must POST /verdict (confirmed) first.
    """
    repo_dir = _repo_dir(repo)
    if not repo_dir.exists():
        raise HTTPException(status_code=404, detail=f"repo not found: {repo}")
    _validate_feature_slug(req.feature_slug)

    finding, ledger, reason = orchestrator_svc.select_followup_finding(
        repo_dir, req.feature_slug, req.finding_id,
    )
    if reason == "unknown":
        raise HTTPException(status_code=404,
                            detail=f"unknown finding_id: {req.finding_id}")
    if reason in ("not_product_bug", "not_confirmed"):
        raise HTTPException(
            status_code=409,
            detail=("finding not eligible for dispatch "
                    f"({reason}) — only operator-confirmed product_bug "
                    "findings can be dispatched"),
        )
    if reason == "already_dispatched":
        raise HTTPException(
            status_code=409,
            detail=(f"finding already dispatched (state={finding.dispatch_state}) "
                    "— R15 dispatch-at-most-once"),
        )

    run_id = (
        f"manual-dispatch-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        f"-{uuid.uuid4().hex[:6]}"
    )

    async def gen():
        try:
            async for event in orchestrator_svc._dispatch_one_followup(
                repo_dir, repo, run_id, req.feature_slug, finding, 0,
                _retrieval_kwargs, ledger, timeout=req.timeout_seconds,
            ):
                yield _sse(event)
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "_error", "error": f"{type(exc).__name__}: {exc}"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
