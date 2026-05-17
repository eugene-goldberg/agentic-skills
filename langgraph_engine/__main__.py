"""CLI entry point.

Example:

    python -m langgraph_engine run \
        --project-name "my-project" \
        --workspace /Users/eugenegoldberg/dev/ai-projects/agentic-skills \
        --target-repo /path/to/empty-or-initialized-target-repo \
        --brief /path/to/brief.md \
        --po-skill /path/to/po-SKILLS.md \
        --eng-skill /path/to/eng-SKILLS.md \
        --qa-skill /path/to/qa-SKILLS.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import AzureOpenAIConfig
from .graph import build_graph


def main() -> int:
    parser = argparse.ArgumentParser(prog="langgraph_engine")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the PO -> Eng -> QA loop end to end.")
    run.add_argument("--project-name", required=True)
    run.add_argument("--workspace", required=True, help="Absolute path to the agentic-skills workspace.")
    run.add_argument("--target-repo", required=True, help="Absolute path to the target repo (PO/Eng/QA all act here).")
    run.add_argument("--brief", required=True, help="Path to the project brief markdown file.")
    run.add_argument("--po-skill", required=True, help="Path to the PO SKILLS.md file.")
    run.add_argument("--eng-skill", required=True, help="Path to the Engineer SKILLS.md file.")
    run.add_argument("--qa-skill", required=True, help="Path to the QA SKILLS.md file.")
    run.add_argument("--env", default=None, help="Optional path to a .env file (defaults to workspace/.env).")

    args = parser.parse_args()

    if args.command == "run":
        workspace = Path(args.workspace).resolve()
        env_path = Path(args.env).resolve() if args.env else workspace / ".env"
        cfg = AzureOpenAIConfig.from_env(env_path)
        if cfg.provider == "anthropic":
            print(f"Using Anthropic model: {cfg.model}")
        elif cfg.provider == "huggingface":
            print(f"Using Hugging Face model: {cfg.model} @ {cfg.endpoint}")
        elif cfg.provider == "openai":
            print(f"Using OpenAI model: {cfg.model}{(' @ ' + cfg.endpoint) if cfg.endpoint else ''}")
        else:
            print(f"Using Azure OpenAI deployment: {cfg.deployment} @ {cfg.endpoint}")

        graph = build_graph(cfg)
        initial_state = {
            "project_name": args.project_name,
            "workspace_root": str(workspace),
            "target_repo_path": str(Path(args.target_repo).resolve()),
            "project_brief_path": str(Path(args.brief).resolve()),
            "po_skill_source_path": str(Path(args.po_skill).resolve()),
            "eng_skill_source_path": str(Path(args.eng_skill).resolve()),
            "qa_skill_source_path": str(Path(args.qa_skill).resolve()),
        }
        result = graph.invoke(initial_state, config={"recursion_limit": 1000})

        # Summary
        completed = result.get("completed_cycles", []) or []
        print()
        print(f"Cycles completed: {len(completed)}")
        for c in completed:
            print(f"  {c['bl_id']}: eng={c.get('eng_decision','?')}({c.get('eng_score',0)}) qa={c.get('qa_decision','?')}({c.get('qa_score',0)})")
        if result.get("error"):
            print(f"\nError: {result['error']}")
            return 1
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
