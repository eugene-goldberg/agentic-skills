"""Engineering cycle: author work packet, run engineering agent, score, capture artifacts.

Three orchestrator nodes plus the agent node:
- `author_eng_packet`: pure-Python; writes `briefs/engineering-work-packets/bl-XXXX-*.md`
  from the BL item + relevant REQs + engineering guide. Sets up run dir.
- `run_eng_agent`: LLM-driven; hands the agent the packet + skill + target repo;
  agent commits per BL item; captures `verification.txt`, `diff.patch`,
  `output_artifacts/`, `raw_logs/invocation.md`, `metadata.yaml`.
- `score_eng`: LLM-driven; reads run artifacts + rubric and writes `scorecard.md`
  plus the outcome block in `metadata.yaml`.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

import yaml

from ..agent_loop import run_agent
from ..config import AzureOpenAIConfig
from ..llm import build_llm
from ..state import GraphState
from ..tools import make_tools


def _hash_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s[:80] or "untitled"


def _extract_reqs(requirements_text: str, req_ids: list[str]) -> str:
    """Pull the REQ-XXXX blocks named in `req_ids` from REQUIREMENTS.md."""
    if not req_ids:
        return ""
    pattern = re.compile(r"^##\s+(REQ-\d{4}).*?$", re.MULTILINE)
    matches = list(pattern.finditer(requirements_text))
    chunks = []
    for i, m in enumerate(matches):
        req_id = m.group(1)
        if req_id not in req_ids:
            continue
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(requirements_text)
        chunks.append(requirements_text[start:end].rstrip())
    return "\n\n".join(chunks)


def author_eng_packet(state: GraphState) -> GraphState:
    workspace = Path(state["workspace_root"]).resolve()
    target = Path(state["target_repo_path"]).resolve()
    item = state["backlog_items"][state["current_index"]]
    bl_id = item["bl_id"]
    bl_num = bl_id.split("-", 1)[1]
    slug = _slugify(item["title"])
    eng_skill_id = state["eng_skill_id"]
    run_id = f"eng-lg-{eng_skill_id}-bl-{bl_num}"
    run_dir = workspace / "runs" / run_id
    (run_dir / "output_artifacts").mkdir(parents=True, exist_ok=True)
    (run_dir / "raw_logs").mkdir(parents=True, exist_ok=True)

    # Determine baseline commit (target repo HEAD before this BL)
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=target, capture_output=True, text=True, check=False,
    )
    baseline_commit = proc.stdout.strip() or "(no commits yet)"

    # Pull relevant REQs
    req_path = Path(state.get("requirements_path") or (target / "REQUIREMENTS.md"))
    req_excerpts = ""
    if req_path.exists():
        req_excerpts = _extract_reqs(req_path.read_text(encoding="utf-8"), item["req_ids"])

    # Namespace by run_id so the graph never overwrites manually-authored packets.
    packet_dir = workspace / "briefs" / "engineering-work-packets"
    packet_dir.mkdir(parents=True, exist_ok=True)
    packet_path = packet_dir / f"{run_id}.md"

    packet = _render_eng_packet(
        run_id=run_id,
        target_repo=target,
        baseline_commit=baseline_commit,
        bl_id=bl_id,
        bl_block=item["raw"],
        req_excerpts=req_excerpts,
        eng_skill_id=eng_skill_id,
    )
    packet_path.write_text(packet, encoding="utf-8")
    packet_sha = _hash_file(packet_path)

    return {
        **state,
        "eng_run_id": run_id,
        "eng_run_dir": str(run_dir),
        "eng_packet_path": str(packet_path),
        "eng_packet_sha256": packet_sha,
        "eng_baseline_commit": baseline_commit,
    }


def _render_eng_packet(*, run_id, target_repo, baseline_commit, bl_id, bl_block, req_excerpts, eng_skill_id):
    return f"""# Engineering Work Packet: {bl_id}

## Run

- Run ID: `{run_id}`
- Engineering Skill: `{eng_skill_id}`
- Target Repo: `{target_repo}`
- Baseline Commit: `{baseline_commit}`
- Backlog Item: `{bl_id}`

## Source Context

- Requirements: `REQUIREMENTS.md`
- Backlog: `.agile-v/BACKLOG.md`
- Sprint Plan: `.agile-v/sprints/C1/SPRINT_PLAN_C1.md`
- Engineering guide: `ENGINEERING_GUIDE.md` (if present)

## Selected Backlog Item

{bl_block}

## Related Requirements

{req_excerpts or "(no REQ excerpts available)"}

## In Scope

Implement only the behavior in this BL item's Acceptance section. Stay within the BL's stated REQ references.

## Out Of Scope

- Anything from other backlog items.
- Refactors, dependency bumps, or hygiene changes not required to deliver this slice.
- Running or fixing `verify_blNNNN.py` for any BL other than this one. Cross-BL regression coverage is the QA role's responsibility, not engineering's. If a prior-BL verifier appears broken due to environment/tooling noise, IGNORE it — do not modify it, do not investigate it. Your only verifier is `verify_bl{bl_id.split('-', 1)[1]}.py` for this BL.

## Expected Artifacts

- Updated source files in the target repo.
- New or updated tests under `tests/`.
- A `verify_bl{bl_id.split('-', 1)[1]}.py` BL-specific sanity checker at the repo root.
- Updated `scripts/full_http_smoke.py` (if it exists, extend its coverage for this BL).

## Verification Commands

```bash
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl{bl_id.split('-', 1)[1]}.py
.venv/bin/python scripts/full_http_smoke.py
```

Run these inside the target repo. All must pass before you declare the cycle complete.

## Done Criteria

- Every Acceptance criterion in the BL block above is covered by at least one test.
- All verification commands exit zero.
- The target repo is on a new commit that begins with `Implement {bl_id}`.
- No file in `REQUIREMENTS.md`, `.agile-v/BACKLOG.md`, or `.agile-v/sprints/C1/SPRINT_PLAN_C1.md` has been modified.
"""


ENG_USER_PROMPT = """You are the engineering agent for run `{run_id}`. Implement BL item `{bl_id}` as a single vertical slice in the target repo.

## Inputs (read in this order)

1. Engineering skill instructions are the system prompt — follow them.
2. Engineering guide: read `{target_repo}/ENGINEERING_GUIDE.md` if it exists.
3. Engineering work packet: read `{packet_path}` — this is your scope contract.
4. Requirements: read the REQ blocks named in the packet from `{target_repo}/REQUIREMENTS.md`.
5. The full BL block from `{target_repo}/.agile-v/BACKLOG.md`.

## Working directory

`{target_repo}` — all implementation happens here. The repo is currently at commit `{baseline_commit}`. Use `.venv/bin/python` if a `.venv/` exists; otherwise use `python3`.

## Scope rules

- Implement only `{bl_id}`. Do not touch unrelated backlog items.
- Do NOT modify `REQUIREMENTS.md`, `.agile-v/BACKLOG.md`, or any file under `.agile-v/sprints/`.
- Do NOT run or modify `verify_blNNNN.py` files for any BL other than this one. Cross-BL regression is the QA role's responsibility. If a prior-BL verifier looks broken, ignore it — do not investigate, do not fix.
- Commit your work atomically. Use a final commit whose message begins with `Implement {bl_id}`.
- Keep the repo runnable after every meaningful increment.

## Verification

Run these inside the target repo before declaring success. If any fails, fix root cause and re-run from the top.

```
.venv/bin/python -m py_compile app.py
.venv/bin/python -m pytest -q
.venv/bin/python verify_bl{bl_num}.py
.venv/bin/python scripts/full_http_smoke.py
```

(`scripts/full_http_smoke.py` may not exist yet on the first BL; create it if appropriate or skip if not relevant.)

## Run artifacts you must write

Under `{run_dir}/`:

- `verification.txt` — commands, working dir, `Result: pass`, and verbatim stdout per command.
- `diff.patch` — `git diff {baseline_commit}..HEAD` from inside the target repo, written to this path.
- `output_artifacts/` — copies of the final versions of every file you touched (preserve subpaths under the target repo).
- `raw_logs/invocation.md` — your final report describing decisions made, commits authored (SHA + message), and final verification results.
- `metadata.yaml` — see schema below; leave `outcome` empty (scoring is a separate node).

## metadata.yaml schema

```yaml
run_id: "{run_id}"
role: "Engineer"
status: "executed"
bl_id: "{bl_id}"
target_repo: "{target_repo}"
baseline_commit: "{baseline_commit}"
final_commit: "<sha at end of cycle>"
verification:
  commands:
    - "..."
  result: "pass"   # or "fail"
  output_path: "{run_dir}/verification.txt"
agent:
  iterations: 0
  tool_calls: 0
outcome:
  decision: ""
  total_score: null
  summary: ""
```

## Final report

When you are done, return a final assistant message (no tool calls) summarizing: the final commit SHA, files changed, verification results per command, and any decisions made on ambiguous points.
"""


def run_eng_agent(state: GraphState, cfg: AzureOpenAIConfig) -> GraphState:
    workspace = Path(state["workspace_root"]).resolve()
    target = Path(state["target_repo_path"]).resolve()
    run_dir = Path(state["eng_run_dir"]).resolve()
    bl_id = state["backlog_items"][state["current_index"]]["bl_id"]
    bl_num = bl_id.split("-", 1)[1]

    skill_text = Path(state["eng_skill_snapshot_path"]).read_text(encoding="utf-8")
    packet_text = Path(state["eng_packet_path"]).read_text(encoding="utf-8")

    system_prompt = (
        skill_text
        + "\n\n---\n\nWork packet follows. Treat it as your scope contract.\n\n"
        + packet_text
    )

    user_prompt = ENG_USER_PROMPT.format(
        run_id=state["eng_run_id"],
        bl_id=bl_id,
        bl_num=bl_num,
        target_repo=str(target),
        baseline_commit=state["eng_baseline_commit"],
        packet_path=state["eng_packet_path"],
        run_dir=str(run_dir),
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
        f"# Engineering run {state['eng_run_id']}\n\n"
        f"Iterations: {result.iterations}\nTool calls: {result.tool_calls_made}\n"
        f"Truncated: {result.truncated}\n\n## Final report\n\n{result.final_message}\n",
        encoding="utf-8",
    )

    # Capture HEAD as final commit
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=target, capture_output=True, text=True, check=False,
    )
    final_commit = proc.stdout.strip() or state["eng_baseline_commit"]

    return {
        **state,
        "eng_agent_report": result.final_message,
        "eng_final_commit": final_commit,
        "last_eng_commit": final_commit,
    }


SCORE_PROMPT = """You are the scoring node. Read the run artifacts under `{run_dir}` (verification.txt, raw_logs/invocation.md, diff.patch) and read the rubric at `{rubric_path}`. Produce a scorecard at `{run_dir}/scorecard.md` using the same shape as the existing scorecards under `{workspace}/runs/eng-001-incremental-implementation-bl-0006/scorecard.md` and `{workspace}/runs/eng-001-incremental-implementation-bl-0007/scorecard.md` (read those for format reference).

Then update `{run_dir}/metadata.yaml` so its `outcome` block is filled (`decision`, `total_score`, `failure_mode_labels`, `summary`). Use the `edit_file` tool to replace the empty outcome block in place; do NOT rewrite the whole file.

Be strict but fair. Use the rubric's 0-5 scale per dimension. The total_score is the sum of the 10 core dimensions plus the 5 role-specific dimensions (max 75). If a verification command failed or any required artifact is missing, decision is `Fail` and the total cannot exceed 50. Otherwise the decision is `Pass`.

When done, return a final assistant message (no tool calls) with a one-paragraph rationale and the chosen total_score.
"""


def score_eng(state: GraphState, cfg: AzureOpenAIConfig) -> GraphState:
    workspace = Path(state["workspace_root"]).resolve()
    run_dir = Path(state["eng_run_dir"]).resolve()
    rubric_path = workspace / "rubrics" / "production_grade_scorecard.md"

    llm = build_llm(cfg)
    tools = make_tools(workspace)
    result = run_agent(
        llm=llm,
        tools=tools,
        system_prompt="You are a strict-but-fair scoring agent. You must read artifacts and write a scorecard.",
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
    if (run_dir / "metadata.yaml").exists():
        try:
            md = yaml.safe_load((run_dir / "metadata.yaml").read_text(encoding="utf-8"))
            outcome = (md or {}).get("outcome") or {}
            decision = str(outcome.get("decision", ""))
            total_score = int(outcome.get("total_score") or 0)
        except Exception:  # noqa: BLE001
            pass

    completed_cycles = list(state.get("completed_cycles", []))
    return {
        **state,
        "eng_scorecard_path": str(scorecard_path),
        "eng_decision": decision,
        "eng_score": total_score,
        "completed_cycles": completed_cycles,  # QA appends after its score
    }
