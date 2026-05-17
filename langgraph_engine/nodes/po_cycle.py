"""PO cycle: hand the brief to the PO agent, capture the planning artifacts.

Mirrors PO-001: the agent should produce `REQUIREMENTS.md`, `.agile-v/BACKLOG.md`,
and a sprint plan inside the target repo. The agent's final message is recorded
as the run report. Run metadata is written to `runs/<po_run_id>/metadata.yaml`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from ..agent_loop import run_agent
from ..config import AzureOpenAIConfig
from ..llm import build_llm
from ..state import GraphState
from ..tools import make_tools


PO_USER_PROMPT_TEMPLATE = """You are running the PO (Product Owner) cycle for the project named '{project_name}'.

## Your role

The skill instructions for your role have been provided as the system prompt. Follow them. You are a PO decomposing a project brief into a backlog and supporting planning artifacts that the engineering agent will consume one item at a time.

## Inputs

- Project brief (your source of truth): `{brief_path}`
- Target repo where you will write planning artifacts: `{target_repo}`

## Required deliverables (write inside the target repo)

You must produce, at minimum:

1. `REQUIREMENTS.md` — numbered REQ-XXXX items with Requirement / Constraint / Verification Criteria / Done Criteria for each.
2. `.agile-v/BACKLOG.md` — ordered backlog of `BL-XXXX` items. Each item must include: heading `## BL-XXXX: <title>`, a Type line, Priority, a `**REQ:**` list referencing requirements, a `**Story:**`, an `**Acceptance:**` enumerated list, an `**Effort:**` value, a `**Dependencies:**` list (use `none` if empty), and a `**Status:**` of `Ready` or `Backlog`. The engineering loop processes only `Ready` items in document order, so order matters.
3. `.agile-v/sprints/C1/SPRINT_PLAN_C1.md` — sprint plan covering the first cohort of ready items.
4. `ENGINEERING_GUIDE.md` — short guide the engineering agent will read at the start of every cycle (project layout, conventions, runtime expectations).

## Working rules

- All file paths above are relative to the target repo `{target_repo}` and you write them using the `write_file` tool with absolute paths under that directory.
- You have full read/write/bash inside the workspace `{workspace_root}`. Use `bash` for any inspection or scaffolding you need (e.g. `mkdir -p`, `git init` if not already a repo).
- Do not implement features. Your output is planning artifacts only.
- If the target repo is not yet a git repository, initialize it with `git init`, configure a local user (`git -c user.name=PO -c user.email=po@local config ...` or via local config), and create a single initial commit after writing the planning artifacts. Use commit message exactly: `PO planning artifacts for {project_name}`.
- Make the backlog items small enough that an engineering agent can implement one BL-XXXX in a single vertical slice with tests.
- The first few BL items should establish the foundation (auth, primary data model) and later items should build on them. Use `**Dependencies:**` to encode ordering.

## Final report

When you are done, return a final assistant message (with no tool calls) summarizing: the REQ count, the BL count, which BL ids you marked `Ready`, the final commit SHA, and any decisions you made on ambiguous points in the brief.
"""


def po_cycle(state: GraphState, cfg: AzureOpenAIConfig) -> GraphState:
    workspace = Path(state["workspace_root"]).resolve()
    target_repo = Path(state["target_repo_path"]).resolve()
    brief = Path(state["project_brief_path"]).resolve()

    run_id = f"po-lg-{state['po_skill_id']}"
    run_dir = workspace / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "raw_logs").mkdir(exist_ok=True)

    skill_text = Path(state["po_skill_snapshot_path"]).read_text(encoding="utf-8")
    brief_text = brief.read_text(encoding="utf-8")

    system_prompt = (
        skill_text
        + "\n\n---\n\nProject brief follows. Treat it as your source of truth.\n\n"
        + brief_text
    )

    user_prompt = PO_USER_PROMPT_TEMPLATE.format(
        project_name=state["project_name"],
        brief_path=str(brief),
        target_repo=str(target_repo),
        workspace_root=str(workspace),
    )

    llm = build_llm(cfg)
    tools = make_tools(workspace)
    result = run_agent(
        llm=llm,
        tools=tools,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_iterations=200,
    )

    # Persist the agent's final message as the invocation log
    (run_dir / "raw_logs" / "invocation.md").write_text(
        f"# PO run {run_id}\n\n"
        f"Iterations: {result.iterations}\nTool calls: {result.tool_calls_made}\n"
        f"Truncated: {result.truncated}\n\n## Final report\n\n{result.final_message}\n",
        encoding="utf-8",
    )

    # Discover the artifacts the PO is supposed to have written
    backlog_path = target_repo / ".agile-v" / "BACKLOG.md"
    requirements_path = target_repo / "REQUIREMENTS.md"
    sprint_plan_path = target_repo / ".agile-v" / "sprints" / "C1" / "SPRINT_PLAN_C1.md"

    metadata = {
        "run_id": run_id,
        "role": "PO",
        "skill": {
            "id": state["po_skill_id"],
            "snapshot": state["po_skill_snapshot_path"],
            "sha256": state["po_skill_sha256"],
        },
        "target_repo": str(target_repo),
        "brief": str(brief),
        "deliverables": {
            "requirements": str(requirements_path) if requirements_path.exists() else None,
            "backlog": str(backlog_path) if backlog_path.exists() else None,
            "sprint_plan": str(sprint_plan_path) if sprint_plan_path.exists() else None,
        },
        "agent": {
            "iterations": result.iterations,
            "tool_calls": result.tool_calls_made,
            "truncated": result.truncated,
        },
    }
    (run_dir / "metadata.yaml").write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")

    return {
        **state,
        "po_run_id": run_id,
        "po_run_dir": str(run_dir),
        "backlog_path": str(backlog_path),
        "requirements_path": str(requirements_path),
        "sprint_plan_path": str(sprint_plan_path),
        "po_final_report": result.final_message,
    }
