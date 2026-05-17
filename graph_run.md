cd /Users/eugenegoldberg/dev/ai-projects/agentic-skills && source .venv-lg/bin/activate && python -m langgraph_engine run \
      --project-name "project_tracker_v1" \
      --workspace /Users/eugenegoldberg/dev/ai-projects/agentic-skills \
      --target-repo /Users/eugenegoldberg/dev/ai-projects/agentic-skills/target-repos/lg-graph-test \
      --brief briefs/project_tracker_v1_po_planning.md \
      --po-skill skills/po/po-001-agile-v-product-owner/SKILLS.md \
      --eng-skill skills/engineer/eng-001-incremental-implementation/SKILLS.md \
      --qa-skill skills/qa/qa-001-test-engineer/SKILLS.md

  For background + log: prepend nohup and append > /tmp/lg-run.log 2>&1 &.

  Prereqs: wipe prior runs/*lg-SKILLS*, briefs/engineering-work-packets/bl-*.md, briefs/qa-work-packets/qa-lg-*, and target-repos/lg-graph-test, then re-bootstrap target venv with
  FastAPI/SQLAlchemy/Pydantic/uvicorn/pytest/httpx