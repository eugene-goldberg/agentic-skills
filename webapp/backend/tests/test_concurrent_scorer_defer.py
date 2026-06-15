"""wave-concurrency follow-up #1 regression guard.

The bug: in `_one_bl_concurrent` the scorer was invoked via `_qa_or_scorer_flow`
with `base_branch_override=work_branch` but WITHOUT `merge_target_override`, so
`_qa_or_scorer_flow` defaulted `_merge_target` to `cfg.agent_branch` (the
integration trunk) and the scorer's scorecard-persistence FF-merge landed the BL's
work on the trunk mid-wave — bypassing the BL-id-ordered assembly barrier and
breaking the defer-merge guarantee (BL-0001 then assembled as `noop`).

`_one_bl_concurrent` is a nested closure inside `run_brief`, so it is not unit-
addressable; this AST guard asserts the structural invariant at the source level:
BOTH role calls (QA and scorer) inside `_one_bl_concurrent` must pass
`merge_target_override` so neither defaults its merge target to the trunk. The
behavioral end-to-end proof is the conflicting-pair live concurrency run.
"""
from __future__ import annotations

import ast
from pathlib import Path

ORCH = Path(__file__).resolve().parents[1] / "app" / "services" / "orchestrator.py"


def _find_func(tree: ast.AST, name: str) -> ast.AST | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _qa_or_scorer_calls(fn: ast.AST):
    """All `_qa_or_scorer_flow(...)` calls inside `fn`, keyed by their role
    (4th positional arg)."""
    out = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            target = node.func
            name = getattr(target, "id", None) or getattr(target, "attr", None)
            if name == "_qa_or_scorer_flow":
                # role is the 4th positional arg: (repo_dir, repo_name, bl_id, role, ...)
                if len(node.args) >= 4 and isinstance(node.args[3], ast.Constant):
                    out.setdefault(node.args[3].value, []).append(node)
    return out


def test_concurrent_scorer_passes_merge_target_override():
    tree = ast.parse(ORCH.read_text(encoding="utf-8"))
    fn = _find_func(tree, "_one_bl_concurrent")
    assert fn is not None, "_one_bl_concurrent not found in orchestrator.py"
    calls = _qa_or_scorer_calls(fn)
    assert "scorer" in calls, "no scorer _qa_or_scorer_flow call in _one_bl_concurrent"
    for call in calls["scorer"]:
        kws = {k.arg for k in call.keywords}
        assert "merge_target_override" in kws, (
            "scorer call in _one_bl_concurrent must pass merge_target_override "
            "(else _merge_target defaults to the integration trunk and the "
            "scorecard FF-merge leaks BL work onto the trunk mid-wave)"
        )


def test_concurrent_qa_also_passes_merge_target_override():
    """The QA call already carried the override; lock it so the defer-merge
    invariant covers both writing roles."""
    tree = ast.parse(ORCH.read_text(encoding="utf-8"))
    fn = _find_func(tree, "_one_bl_concurrent")
    calls = _qa_or_scorer_calls(fn)
    assert "qa" in calls, "no qa _qa_or_scorer_flow call in _one_bl_concurrent"
    for call in calls["qa"]:
        kws = {k.arg for k in call.keywords}
        assert "merge_target_override" in kws
