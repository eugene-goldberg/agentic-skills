---
name: agentic-skills-json-convention
description: Per-brownfield-target config file pattern — what fields it carries and how the webapp uses them
metadata:
  type: project
---

Every brownfield target repo carries `.agentic-skills.json` at its root.
Loaded by `webapp/backend/app/services/repo_config.py` on every agent
endpoint hit.

Fields:

```json
{
  "agent_branch":   "integration",
  "main_ref":       "main",
  "doctrine":       "brownfield",
  "test_cmd":       ["/abs/path/to/target/.venv/bin/pytest", "backend/tests", "-q"]
}
```

(Example = current target `project-management-app`, Docker-free. A Docker-based
target would use `["docker","compose","exec","-T","backend","pytest","-q"]`.)

- `agent_branch` — branch every agent worktree forks off of AND into which
  Engineer/QA fast-forward on a green gate. Default `agentic-skills-work`.
  Crucial: keeps upstream `main`/`master` pristine.
- `main_ref` — pristine upstream branch name (some repos use `master`).
- `doctrine` — explicit family override (`brownfield`/`greenfield`).
  Otherwise derived at runtime from `mcp__retrieval__target_status()` /
  `brownfield.classify_target()`.
- `test_cmd` — override for the regression gate's pre/post pytest run. If
  omitted, auto-detected from `pyproject.toml` / `package.json` /
  `Makefile`. Must be runnable from the uvicorn process's environment.

**Current target = `project-management-app`** (Docker-free; created
2026-06-06). Its `.agentic-skills.json` is committed on `main`, sets
`agent_branch=integration`, and its `test_cmd[0]` is the target's own
`.venv/bin/pytest` (absolute path). Because the repo has no
`compose.yml`/`compose.gate.yml`, `run_bl_tests` runs that pytest natively
in the gate worktree (no Docker). The prior `full-stack-fastapi-template`
clone (Docker-based, `master`/`agentic-skills-work`) was removed 2026-06-06.
