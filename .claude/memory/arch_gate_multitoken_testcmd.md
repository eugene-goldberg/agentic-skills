---
name: arch_gate_multitoken_testcmd
description: A57 — regression gate now supports multi-token test_cmd + per-target test_env; structural enabler for real third-party brownfield targets
metadata: 
  node_type: memory
  type: project
  originSessionId: be51e21b-1239-4b56-b567-6fbcd02be99e
---

**A57 (shipped 2026-06-07, commit b9c2aa9).** The regression gate previously
assumed every target's `test_cmd` was a single, env-free, pytest-style binary
(true of the purpose-built toy targets, false of real repos). Two defects,
both fixed:

1. `regression_gate.run_bl_tests` native (no-compose) branch kept only
   `test_cmd[0]` — `["uv","run","pytest"]` would have run `uv -v <files>`,
   silently dropping `run pytest`. Now uses the FULL command:
   `[*base, *vflag, *bl_tests]`, `-v` added when `pytest` is anywhere in argv.
2. No path to inject per-target env (only `COMPOSE_PROJECT_NAME` was set).
   Added optional `test_env: dict[str,str]` to `.agentic-skills.json` →
   `RepoConfig` (repo_config.py); threaded into `run_bl_tests` (`env=`) and
   both pre/post `_run_tests` calls in `_run_gate_once` (`extra_env=`).
   `_run_tests` merges `test_env`+`COMPOSE_PROJECT_NAME` and widened its `-v`
   auto-add to match wrapped pytest (keeps the per-test differential exact
   rather than collapsing to the green-by-exit-code fallback).

**Why it matters:** this is the structural enabler for ANY real third-party
brownfield target whose suite isn't a bare `pytest`. First consumer:
[[arch_target_beaverhabits]] (`uv run pytest` + SQLite/storage env).

Regression test: `test_simple_gating.py::test_run_bl_tests_multitoken_cmd_and_env`
(asserts full command preserved + test_env reaches the subprocess). Verified
live, not just unit: run_gate 48/48 0-regressions, run_bl_tests green.

Class: I-5 (gate ran the wrong command instead of erroring) + harness-capability
gap. Filed + fixed same session. See [[arch_test_hygiene]], [[arch_gate_throughput]].
