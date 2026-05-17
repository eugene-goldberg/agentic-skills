"""One-shot: run the engineering agent on BL-0001 with the modified eng SKILLS.md.

Reuses existing PO artifacts (BACKLOG, work packet, REQUIREMENTS, ENGINEERING_GUIDE).
Resets the target repo to the PO baseline before running.
Then runs score_eng to produce a scorecard.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

from langgraph_engine.config import LLMConfig
from langgraph_engine.nodes.engineering import run_eng_agent, score_eng

WORKSPACE = Path("/Users/eugenegoldberg/dev/ai-projects/agentic-skills").resolve()
TARGET = WORKSPACE / "target-repos" / "lg-graph-test"
ENG_SKILL = WORKSPACE / "skills" / "eng" / "lg-SKILLS" / "SKILLS.md"  # user's modified file
ENG_PACKET = WORKSPACE / "briefs" / "engineering-work-packets" / "eng-lg-lg-SKILLS-bl-0001.md"
BASELINE_COMMIT = "a7d4fdd6942e53b34162727a49ceda2f8b1ea3a4"
RUN_ID = "eng-lg-lg-SKILLS-bl-0001"
RUN_DIR = WORKSPACE / "runs" / RUN_ID


def reset_target_to_baseline() -> None:
    subprocess.run(["git", "reset", "--hard", BASELINE_COMMIT], cwd=TARGET, check=True)
    subprocess.run(["git", "clean", "-fdx", "-e", ".venv"], cwd=TARGET, check=True)


def fresh_run_dir() -> None:
    if RUN_DIR.exists():
        shutil.rmtree(RUN_DIR)
    (RUN_DIR / "raw_logs").mkdir(parents=True)
    (RUN_DIR / "output_artifacts").mkdir(parents=True)
    metadata = {
        "run_id": RUN_ID,
        "role": "Engineer",
        "status": "in_progress",
        "bl_id": "BL-0001",
        "target_repo": str(TARGET),
        "baseline_commit": BASELINE_COMMIT,
        "final_commit": "",
        "verification": {"commands": [], "result": "", "output_path": ""},
        "agent": {"iterations": 0, "tool_calls": 0},
        "outcome": {
            "decision": "",
            "total_score": "",
            "failure_mode_labels": [],
            "summary": "",
        },
        "timestamp_started_utc": datetime.now(timezone.utc).isoformat(),
    }
    (RUN_DIR / "metadata.yaml").write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")


def main() -> None:
    assert ENG_SKILL.exists(), f"Missing eng skill: {ENG_SKILL}"
    assert ENG_PACKET.exists(), f"Missing eng packet: {ENG_PACKET}"

    env_file = os.environ.get("LG_ENV_FILE", ".env.gpt54")
    cfg = LLMConfig.from_env(WORKSPACE / env_file)
    print(f"Provider={cfg.provider} model={cfg.model}")
    print(f"Skill: {ENG_SKILL}")
    print(f"Packet: {ENG_PACKET}")
    print(f"Target: {TARGET}")
    print(f"Baseline commit: {BASELINE_COMMIT}")

    reset_target_to_baseline()
    fresh_run_dir()

    state = {
        "workspace_root": str(WORKSPACE),
        "target_repo_path": str(TARGET),
        "eng_run_id": RUN_ID,
        "eng_run_dir": str(RUN_DIR),
        "eng_skill_snapshot_path": str(ENG_SKILL),
        "eng_packet_path": str(ENG_PACKET),
        "eng_baseline_commit": BASELINE_COMMIT,
        "current_index": 0,
        "backlog_items": [{"bl_id": "BL-0001"}],
        "completed_cycles": [],
    }

    print("\n=== run_eng_agent ===")
    state = run_eng_agent(state, cfg)
    print(f"final_commit: {state.get('eng_final_commit')}")

    print("\n=== score_eng ===")
    state = score_eng(state, cfg)
    print(f"decision: {state.get('eng_decision')}")
    print(f"score: {state.get('eng_score')}/75")
    print(f"scorecard: {state.get('eng_scorecard_path')}")


if __name__ == "__main__":
    main()
