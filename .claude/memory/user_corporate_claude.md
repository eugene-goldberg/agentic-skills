---
name: user-corporate-claude
description: User authenticates Claude Code via corporate OAuth — no personal ANTHROPIC_API_KEY available
metadata: 
  node_type: memory
  type: user
  originSessionId: 2b184b19-1809-4a2e-bad8-ec19ea9ee94c
---

User runs Claude Code through their employer's account, so `~/.claude/` already has working OAuth credentials but **no personal `ANTHROPIC_API_KEY` is available**. Any solution that requires the user to "just set ANTHROPIC_API_KEY" is a non-starter.

Practical implication: subprocess invocations of the `claude` CLI inherit `HOME` and pick up corporate auth automatically. The webapp's `services/claude_agent.py` relies on this — `env={**os.environ, ...}` preserves HOME so the spawned `claude` finds `~/.claude/`.

**How to apply:** when building or extending agent invocations, never assume `ANTHROPIC_API_KEY` is available. The auth path is: terminal `claude /login` has already run → credentials are in `~/.claude/` → subprocess inherits HOME → it works. For non-user contexts (systemd, containers, different user) HOME must be set explicitly.
