"""QA cycle: author packet (with carry-forward), run QA agent, score."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import yaml

from ..agent_loop import run_agent
from ..config import AzureOpenAIConfig
from ..llm import build_llm
from ..state import CycleResult, GraphState
from ..tools import make_tools


def _hash_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def author_qa_packet(state: GraphState) -> GraphState:
    workspace = Path(state["workspace_root"]).resolve()
    target = Path(state["target_repo_path"]).resolve()
    item = state["backlog_items"][state["current_index"]]
    bl_id = item["bl_id"]
    bl_num = bl_id.split("-", 1)[1]
    qa_skill_id = state["qa_skill_id"]
    run_id = f"qa-lg-{qa_skill_id}-bl-{bl_num}"
    run_dir = workspace / "runs" / run_id
    (run_dir / "output_artifacts").mkdir(parents=True, exist_ok=True)
    (run_dir / "raw_logs").mkdir(parents=True, exist_ok=True)

    # Find prior QA run (most recent completed cycle's qa_run_dir)
    completed = state.get("completed_cycles", [])
    carry_from: str | None = None
    if completed:
        prior = completed[-1]
        prior_dir = Path(prior["qa_run_dir"])
        prior_suite = prior_dir / "journey_suite"
        if prior_suite.exists():
            shutil.copytree(prior_suite, run_dir / "journey_suite", dirs_exist_ok=True)
            carry_from = prior["qa_run_id"]
    if carry_from is None:
        (run_dir / "journey_suite").mkdir(parents=True, exist_ok=True)

    packet_dir = workspace / "briefs" / "qa-work-packets"
    packet_dir.mkdir(parents=True, exist_ok=True)
    packet_path = packet_dir / f"qa-lg-{qa_skill_id}-bl-{bl_num}.md"
    packet = _render_qa_packet(
        run_id=run_id,
        target_repo=target,
        target_commit=state["eng_final_commit"],
        bl_id=bl_id,
        bl_block=item["raw"],
        eng_run_id=state["eng_run_id"],
        carry_from=carry_from,
        run_dir=run_dir,
    )
    packet_path.write_text(packet, encoding="utf-8")
    packet_sha = _hash_file(packet_path)

    return {
        **state,
        "qa_run_id": run_id,
        "qa_run_dir": str(run_dir),
        "qa_packet_path": str(packet_path),
        "qa_packet_sha256": packet_sha,
        "qa_carry_forward_run_id": carry_from,
    }


def _render_qa_packet(*, run_id, target_repo, target_commit, bl_id, bl_block, eng_run_id, carry_from, run_dir):
    carry_text = (
        f"`{carry_from}` (copied into `{run_dir}/journey_suite/`)"
        if carry_from
        else "none (first QA cycle)"
    )
    return f"""# QA Work Packet: {bl_id}

## Run

- Run ID: `{run_id}`
- Target Repo: `{target_repo}`
- Target Commit: `{target_commit}` (engineering closing commit for {bl_id})
- Engineering Run: `{eng_run_id}`
- Engineering BL Under Test: `{bl_id}`
- Carry-Forward Suite: {carry_text}

## Selected Backlog Item

{bl_block}

## Mandatory Inputs

Run inside the target repo at commit `{target_commit}`. Capture exit code + verbatim stdout for each:

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl{bl_id.split('-', 1)[1]}.py
.venv/bin/python scripts/full_http_smoke.py
```

Plus any earlier-BL verifier present at this commit (e.g. `verify_bl0001.py`, etc.).

## Journey suite

Lives at `{run_dir}/journey_suite/`. {("Already contains the prior cycle's suite — extend it in place." if carry_from else "Author it fresh in this cycle.")} Requirements:

- Use subprocess Uvicorn + real HTTP + fresh tmp SQLite per scenario. Do NOT use `TestClient(app)`.
- Authenticate via real `/signup` and `/login`.
- Cover the BL acceptance criteria with multi-step flows; add adversarial scenarios for the role × HTTP matrix, existence-leak parity, and concurrency where applicable.
- Top-level entry: `run.py`. Emit `{run_dir}/journey_results.json` with per-scenario pass/fail.
- Exit non-zero on any unknown failure. Known-bug failures (carried forward from prior cycles) can be annotated with a `known_bug_id` field and excluded from the exit code.
- All prior-BL scenarios must continue to pass against this commit, except those marked `known_bug_id`. Any new regression is a finding.

## Deliverables

Under `{run_dir}/`:

- `engineer_stack_results.txt`
- `gap_audit.md`
- `journey_suite/` (full implementation)
- `journey_results.json`
- `bug_report.md`
- `raw_logs/invocation.md`
- `metadata.yaml`

## Scope rules

- Do NOT modify any engineer-authored artifact in the target repo. You report findings; engineering fixes.
- Do NOT advance the target repo past `{target_commit}`. Use `git checkout {target_commit}` if needed and restore the prior HEAD when done.
- Do NOT use `TestClient(app)` in your journey suite.
- Do NOT skip the engineer-authored verification stack.

## Final report

Return an assistant message (no tool calls) summarizing: engineer stack pass/fail per command, journey suite total/pass/fail with known-bug call-out, bug count by severity, top finding, and any decisions on ambiguous points.
"""


QA_USER_PROMPT = """You are the QA agent for run `{run_id}`. Gate the engineering BL `{bl_id}` at commit `{target_commit}` in target repo `{target_repo}`.

## Inputs (read IN THIS ORDER before doing anything)

1. QA skill instructions are the system prompt — follow them.
2. QA work packet: read `{packet_path}` — this is your scope contract.
3. Engineering run scorecard (for context): `{eng_run_dir}/scorecard.md` if present.
4. Prior QA bug reports (if a carry-forward exists): the prior cycle's `bug_report.md`.

## Working directory

`{target_repo}`. Use `git status -s` to confirm clean. Then `git checkout {target_commit}` to align with the engineering BL closing commit. Verify `git rev-parse HEAD` == `{target_commit}`. When done, `git checkout {original_head}` to restore the repo. Working tree must be clean before and after.

## Scope rules

- Do NOT modify any tracked engineer artifact in the target repo.
- Do NOT use `TestClient(app)` in the journey suite.
- Do NOT skip the engineer-authored verification stack.

## Required deliverables

All under `{run_dir}/`. The packet at `{packet_path}` lists them in detail; produce all of them.

## metadata.yaml schema

```yaml
run_id: "{run_id}"
role: "QA"
status: "executed"
bl_id: "{bl_id}"
target_commit: "{target_commit}"
carry_forward: "{carry_from}"
verification:
  engineer_stack_result: ""        # pass | fail
  journey_suite_result: ""         # pass | pass-with-known-bugs | fail
  total_scenarios: 0
  scenarios_passed: 0
  scenarios_failed: 0
  known_bug_failures: 0
  unknown_failures: 0
bug_counts:
  new_findings:
    critical: 0
    high: 0
    medium: 0
    low: 0
    cosmetic: 0
  carried_known_bugs: 0
outcome:
  decision: ""
  total_score: null
  summary: ""
```

Leave the `outcome` block empty — scoring is a separate node.

## Final report

Return an assistant message (no tool calls) summarizing: engineer stack result per command, journey suite total/pass/fail with known-bug call-out, new bug counts, top finding, confirmation target repo restored to `{original_head}`.
"""


def run_qa_agent(state: GraphState, cfg: AzureOpenAIConfig) -> GraphState:
    workspace = Path(state["workspace_root"]).resolve()
    target = Path(state["target_repo_path"]).resolve()
    run_dir = Path(state["qa_run_dir"]).resolve()
    bl_id = state["backlog_items"][state["current_index"]]["bl_id"]

    # Capture original HEAD to restore later
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=target, capture_output=True, text=True, check=False,
    )
    original_head = proc.stdout.strip()

    skill_text = Path(state["qa_skill_snapshot_path"]).read_text(encoding="utf-8")
    packet_text = Path(state["qa_packet_path"]).read_text(encoding="utf-8")

    system_prompt = (
        skill_text
        + "\n\n---\n\nQA work packet follows. Treat it as your scope contract.\n\n"
        + packet_text
    )

    user_prompt = QA_USER_PROMPT.format(
        run_id=state["qa_run_id"],
        bl_id=bl_id,
        target_commit=state["eng_final_commit"],
        target_repo=str(target),
        packet_path=state["qa_packet_path"],
        eng_run_dir=state["eng_run_dir"],
        run_dir=str(run_dir),
        original_head=original_head,
        carry_from=state.get("qa_carry_forward_run_id") or "none",
    )

    llm = build_llm(cfg)
    tools = make_tools(workspace, bash_timeout=900)
    result = run_agent(
        llm=llm,
        tools=tools,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_iterations=300,
    )

    (run_dir / "raw_logs" / "invocation.md").write_text(
        f"# QA run {state['qa_run_id']}\n\n"
        f"Iterations: {result.iterations}\nTool calls: {result.tool_calls_made}\n"
        f"Truncated: {result.truncated}\n\n## Final report\n\n{result.final_message}\n",
        encoding="utf-8",
    )

    # Ensure target repo is restored to original_head
    subprocess.run(["git", "checkout", original_head], cwd=target, capture_output=True, text=True, check=False)

    return {**state, "qa_agent_report": result.final_message}


SCORE_PROMPT = """You are the QA scoring node. Read artifacts under `{run_dir}` (engineer_stack_results.txt, gap_audit.md, journey_results.json, bug_report.md, raw_logs/invocation.md, metadata.yaml) and the rubric at `{rubric_path}`. Produce a scorecard at `{run_dir}/scorecard.md` modeled after the existing QA scorecards under `{workspace}/runs/qa-001-test-engineer-bl-0003/scorecard.md` and `{workspace}/runs/qa-001-test-engineer-bl-0006/scorecard.md` (read those for format reference).

Then update `{run_dir}/metadata.yaml` so its `outcome` block is filled (`decision`, `total_score`, `failure_mode_labels`, `summary`). Use `edit_file` to replace the empty outcome block in place; do NOT rewrite the whole file.

Be strict but fair. Use the rubric's 0-5 scale. Total = 10 core dims + 5 QA-specific dims (max 75). If any required deliverable is missing or the engineer stack was not executed, decision is `Fail`. Otherwise, evaluate suite continuity, growth, real-deployment fidelity, and finding quality per the QA evaluation protocol at `{workspace}/docs/qa_evaluation_protocol.md`.

When done, return a final assistant message (no tool calls) with the decision and total score.
"""


def score_qa(state: GraphState, cfg: AzureOpenAIConfig) -> GraphState:
    workspace = Path(state["workspace_root"]).resolve()
    run_dir = Path(state["qa_run_dir"]).resolve()
    rubric_path = workspace / "rubrics" / "production_grade_scorecard.md"

    llm = build_llm(cfg)
    tools = make_tools(workspace)
    run_agent(
        llm=llm,
        tools=tools,
        system_prompt="You are a strict-but-fair QA scoring agent. You must read artifacts and write a scorecard.",
        user_prompt=SCORE_PROMPT.format(
            run_dir=str(run_dir),
            rubric_path=str(rubric_path),
            workspace=str(workspace),
        ),
        max_iterations=80,
    )

    scorecard_path = run_dir / "scorecard.md"
    decision = ""
    total_score = 0
    unknown_failures = 0
    known_bug_failures = 0
    if (run_dir / "metadata.yaml").exists():
        try:
            md = yaml.safe_load((run_dir / "metadata.yaml").read_text(encoding="utf-8")) or {}
            outcome = md.get("outcome") or {}
            decision = str(outcome.get("decision", ""))
            total_score = int(outcome.get("total_score") or 0)
            ver = md.get("verification") or {}
            unknown_failures = int(ver.get("unknown_failures") or 0)
            known_bug_failures = int(ver.get("known_bug_failures") or 0)
        except Exception:  # noqa: BLE001
            pass

    bl_id = state["backlog_items"][state["current_index"]]["bl_id"]
    cycle: CycleResult = {
        "bl_id": bl_id,
        "eng_run_id": state["eng_run_id"],
        "eng_run_dir": state["eng_run_dir"],
        "eng_decision": state.get("eng_decision", ""),
        "eng_score": state.get("eng_score", 0),
        "eng_final_commit": state["eng_final_commit"],
        "qa_run_id": state["qa_run_id"],
        "qa_run_dir": state["qa_run_dir"],
        "qa_decision": decision,
        "qa_score": total_score,
        "qa_unknown_failures": unknown_failures,
        "qa_known_bug_failures": known_bug_failures,
    }
    completed = list(state.get("completed_cycles", []))
    completed.append(cycle)

    return {
        **state,
        "qa_scorecard_path": str(scorecard_path),
        "qa_decision": decision,
        "qa_score": total_score,
        "completed_cycles": completed,
    }
