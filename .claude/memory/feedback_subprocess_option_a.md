---
name: feedback-subprocess-option-a
description: "For the webapp's Claude Code integration, user chose Option A (Python subprocess) over Option B (TypeScript SDK)"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 2b184b19-1809-4a2e-bad8-ec19ea9ee94c
---

When asked to design the FastAPI/React webapp invoking Claude Code, the user said: *"Do not use the 'option B (i.e. typescript SDK)'. Use Option A (python subprocess using SSE streaming so the web UI can be updated as tasks get executed)."*

**Why:** keeps Python as the only orchestration language; no Node sidecar daemon to keep running; matches the rest of the agentic-skills stack which is Python.

**How to apply:**
- All future webapp agent invocations go through `asyncio.create_subprocess_exec("claude", "--print", "--output-format", "stream-json", ...)` — never `@anthropic-ai/claude-code` via Node.
- If we ever need fine-grained message-level streaming the TS SDK offers, prefer wrapping it in HTTP and treating it as a black box, not switching primary orchestration to TypeScript.
- Note that the **claude-context retrieval** layer DOES use a small Node bridge (`.spike-node/bridge.js`) — that's different and acceptable because (a) claude-context-core is npm-only, (b) the bridge is short-lived per call, (c) it's not the primary agent invocation path.
