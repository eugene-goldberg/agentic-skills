"""Finalize: write a summary report at runs/_summary.md and append to docs/progress_tracker.md."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..state import GraphState


def finalize(state: GraphState) -> GraphState:
    workspace = Path(state["workspace_root"]).resolve()
    summary_path = workspace / "runs" / f"_summary-{state.get('po_run_id', 'run')}.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Run summary — {state['project_name']}",
        "",
        f"Date: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Inputs",
        "",
        f"- Target repo: `{state['target_repo_path']}`",
        f"- Project brief: `{state['project_brief_path']}`",
        f"- PO skill: `{state['po_skill_snapshot_path']}` (sha256 `{state['po_skill_sha256']}`)",
        f"- Engineer skill: `{state['eng_skill_snapshot_path']}` (sha256 `{state['eng_skill_sha256']}`)",
        f"- QA skill: `{state['qa_skill_snapshot_path']}` (sha256 `{state['qa_skill_sha256']}`)",
        "",
        "## PO cycle",
        "",
        f"- Run ID: `{state.get('po_run_id', '')}`",
        f"- Run dir: `{state.get('po_run_dir', '')}`",
        f"- Backlog: `{state.get('backlog_path', '')}`",
        f"- Requirements: `{state.get('requirements_path', '')}`",
        f"- Backlog items parsed: {len(state.get('backlog_items', []))}",
        "",
        "## Engineering + QA cycles",
        "",
        "| BL | Engineer run | Eng decision | Eng score | QA run | QA decision | QA score | QA unknown fail | QA known-bug fail |",
        "|---|---|---|---:|---|---|---:|---:|---:|",
    ]
    for c in state.get("completed_cycles", []):
        lines.append(
            f"| {c['bl_id']} | `{c['eng_run_id']}` | {c.get('eng_decision', '')} | {c.get('eng_score', 0)} | "
            f"`{c['qa_run_id']}` | {c.get('qa_decision', '')} | {c.get('qa_score', 0)} | "
            f"{c.get('qa_unknown_failures', 0)} | {c.get('qa_known_bug_failures', 0)} |"
        )

    if state.get("error"):
        lines += ["", "## Error", "", state["error"]]

    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Append a short pointer to the progress tracker
    tracker = workspace / "docs" / "progress_tracker.md"
    if tracker.exists():
        with tracker.open("a", encoding="utf-8") as fh:
            fh.write(f"\n\n<!-- langgraph_engine run {state.get('po_run_id', '')} -->\n")
            fh.write(f"See `{summary_path.relative_to(workspace)}` for run summary.\n")

    return state
