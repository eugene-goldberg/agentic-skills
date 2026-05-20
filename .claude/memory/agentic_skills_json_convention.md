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
  "agent_branch":   "agentic-skills-work",
  "main_ref":       "master",
  "doctrine":       "brownfield",
  "test_cmd":       ["docker", "compose", "exec", "-T", "backend", "pytest", "-q"]
}
```

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

**The current full-stack-fastapi-template clone has this file already**;
it's tracked on `agentic-skills-work` (was added in the same commit
`72fd7de` that removed `_brownfield/` from gitignore).
