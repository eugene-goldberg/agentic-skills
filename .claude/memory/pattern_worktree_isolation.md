---
name: pattern-worktree-isolation
description: "Every agent subprocess invocation runs in its own `git worktree add -b agent/<task_id>` so concurrent runs cannot clobber each other"
metadata: 
  node_type: memory
  type: project
  originSessionId: 2b184b19-1809-4a2e-bad8-ec19ea9ee94c
---

In both the langgraph harness and the webapp, every Claude Code agent invocation runs in an isolated `git worktree`:

```python
# webapp/backend/app/services/git_worktree.py
git worktree add -b agent/<task_id> <repo_parent>/.agent-worktrees/<task_id>
# run claude with cwd=that_path
git worktree remove --force <that_path>   # branch retained for inspection
```

The PO flow then merges its `.agile-v/BACKLOG.md` back into the main checkout and commits, so subsequent execute-bl calls see the backlog. Engineer/QA/Scorer flows leave their branches in place — manual merge required to bring them to main.

**Why:** running two agents concurrently against the same checkout would race and corrupt working-copy state; worktrees give each agent a separate index, HEAD, and working dir while sharing the same `.git/`.

**Gotcha discovered 2026-05-17:** if a target repo has no `.git/` of its own, `git commit` from a subprocess will walk UP the directory tree and silently commit into the parent repo's `.git/` (detached HEAD). Always `git init` inside target repos before running agents against them.

**How to apply:** any new endpoint/flow that spawns `claude` against user code must use `create_worktree → run → remove_worktree` pattern. Don't run `claude` directly in the checkout's main working dir.
