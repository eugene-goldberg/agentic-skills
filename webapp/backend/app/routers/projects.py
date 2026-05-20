"""Project-scoped endpoints: brief decomposition + per-BL execution.

Layered on top of the existing /api/tasks stream service:

  POST /api/projects/{repo}/decompose-brief   →  PO agent  (SSE)
  GET  /api/projects/{repo}/backlog            →  parsed backlog items
  POST /api/projects/{repo}/execute-bl         →  Engineer agent for one BL (SSE)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services import backlog as backlog_svc
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


def _retrieval_kwargs(wt: Worktree, role: str, bl_id: str | None = None, trace: TraceWriter | None = None) -> dict:
    """Build stream_agent_task kwargs that enable the retrieval MCP server.

    Retrieval audit log is written into the persistent trace dir so it survives
    worktree cleanup; falls back to inside the worktree if no trace is supplied.
    """
    if not RETRIEVAL_REFERENCE_REPO.exists():
        return {}
    if trace is not None:
        retrieval_log = trace.retrieval_path
    else:
        log_name = f"retrieval-{role}{('-' + bl_id) if bl_id else ''}.jsonl"
        retrieval_log = wt.path / ".agile-v" / "logs" / log_name
    return {
        "reference_repo": RETRIEVAL_REFERENCE_REPO,
        "target_repo": wt.path,
        "retrieval_log_path": retrieval_log,
    }


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
            async for event in stream_agent_task(
                prompt,
                wt.path,
                timeout_seconds=req.timeout_seconds,
                trace=trace,
                **_retrieval_kwargs(wt, role="po", trace=trace),
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
                    **_retrieval_kwargs(wt, role="po", trace=trace),
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
            async for event in stream_agent_task(
                full_prompt,
                wt.path,
                timeout_seconds=req.timeout_seconds,
                trace=trace,
                **_retrieval_kwargs(wt, role="engineer", bl_id=req.bl_id, trace=trace),
            ):
                yield _sse(event)
            # ─── Doctrine pre-merge validator (brownfield) ───
            MAX_FIX_RETRIES = 2
            validation = doctrine_svc.validate_engineer(wt.path, req.bl_id, base_ref=cfg.agent_branch)
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
                    **_retrieval_kwargs(wt, role="engineer", bl_id=req.bl_id, trace=trace),
                ):
                    yield _sse(event)
                validation = doctrine_svc.validate_engineer(wt.path, req.bl_id, base_ref=cfg.agent_branch)
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
                    **{k: gate_result.get(k) for k in ("ok", "kind", "pre", "post", "regressions", "new_failures", "reason", "command")},
                })
                if gate_result.get("ok"):
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
            async for event in stream_agent_task(
                prompt,
                wt.path,
                timeout_seconds=timeout,
                trace=trace,
                **_retrieval_kwargs(wt, role=role, bl_id=bl_id, trace=trace),
            ):
                yield _sse(event)
            # ─── Doctrine pre-merge validator (QA only; scorer is read-only) ───
            validation = {"ok": True, "missing": [], "empty": [], "summary": "n/a"}
            attempt = 0
            if role == "qa":
                MAX_FIX_RETRIES = 2
                validation = doctrine_svc.validate_qa(wt.path, bl_id)
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
                    fix_prompt = doctrine_svc.build_fix_prompt("qa", validation, bl_id=bl_id)
                    async for event in stream_agent_task(
                        fix_prompt,
                        wt.path,
                        timeout_seconds=max(300, timeout // 2),
                        trace=trace,
                        **_retrieval_kwargs(wt, role=role, bl_id=bl_id, trace=trace),
                    ):
                        yield _sse(event)
                    validation = doctrine_svc.validate_qa(wt.path, bl_id)
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
                    **{k: gate_result.get(k) for k in ("ok", "kind", "pre", "post", "regressions", "new_failures", "reason", "command")},
                })
                if gate_result.get("ok"):
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
        return {"gate": {"kind": "skipped"}, "merge": merge}
    gate = await regression_gate_svc.run_gate(repo_dir, agent_branch=req.branch, target_ref=cfg.agent_branch)
    if not gate.get("ok"):
        return {"gate": gate, "merge": None}
    merge = await fast_forward_target(repo_dir, req.branch, target_ref=cfg.agent_branch)
    return {"gate": gate, "merge": merge}


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
