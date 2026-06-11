---
name: arch_native_boot_acceptance
description: "Native-boot acceptance for non-compose targets — config-driven app_boot contract; SHIPPED + LIVE-PROVEN [x] 2026-06-11"
metadata: 
  node_type: memory
  type: project
  originSessionId: 16ab235a-a819-4ddb-a98c-5da1a1a63294
---

**Native-boot acceptance — SHIPPED + LIVE-PROVEN `[x]` 2026-06-11** (commits `3d0845b`
impl + `0328918` proof; proposal `PROPOSAL_NATIVE_BOOT_ACCEPTANCE.md`).

**Problem:** the acceptance phase (THE single integration checkpoint post-A55) was
**compose-centric** (`_build_acceptance_task` threaded `compose_project`; the skill's
inputs were `compose.gate.yml`). On a NON-compose target (fullstack-ecommerce-app: native
`dotnet run` + standalone Postgres + gitignored `appsettings.json`) acceptance only passed
the first C# sprint because the agent **improvised** the boot — not repeatable.

**Fix (config-driven, agent-driven):** optional **`app_boot`** block in the target's
`.agentic-skills.json`: `cmd` (may contain `${PORT}`), `env`, `ready_url`,
`ready_timeout_s`, `materialize` (list of {from,to}), `pre_cmd` (e.g. migrations).
- `repo_config.py`: `app_boot` field + `_normalize_app_boot` (type-validate; mirrors the
  A67 `test_file_globs` optional-field pattern).
- `orchestrator.py`: `_alloc_free_port` (free `${PORT}` → kills the stale-build
  port-collision class), `_resolve_app_boot_port` (`${PORT}` subst), `_materialize_app_boot`
  (copies the gitignored config from the committed template). `_build_acceptance_task`
  emits a native-boot contract block (compose path unchanged when `app_boot` absent);
  wired into `_acceptance_flow` via **getattr** (test-double tolerant). Emits
  `acceptance.app_boot.prepared` (port + materialized + rejected).
- acceptance `SKILLS.md`: boot contract generalized to "compose OR native app_boot".

**Three operator decisions LOCKED (binding):**
- **A — materialize security:** `materialize[].from` MUST be a committed `*.example.*`
  template, worktree-scoped + path-safe (enforced in `_materialize_app_boot`, telemetry on
  reject). Never copies a real secrets file.
- **agent-driven boot:** the agent runs the boot against the explicit contract (adapts to
  surprises like stale-build port squat) — NOT the orchestrator booting directly.
- **Level-3 readiness:** before journeys, poll `ready_url` AND verify a NEW-feature route
  serves (not 404) → kills the false-pass-on-stale-binary class.

**Live proof:** `run-acceptance nativeboot-proof-20260611T013351Z` (ecommerce-wishlist):
harness reserved **port 53700** + materialized appsettings from the `*.example.*` template;
agent ran `dotnet ef database update` (pre_cmd) → `Now listening on :53700` → Level-3 check
(`GET /api/v1/Nonsenses → 404`, then wishlist routes serve) → **7/7 API journeys pass**,
`validator_ok=true, attempt 1`. Booted on the RESERVED port (no improvisation).

**Open follow-up (filed, frontier #2):** native boot LEAKS the agent-backgrounded app
process past worktree reaping (a `dotnet` listener survived on :53700; reaped manually).
Needs a process/port reaper on acceptance teardown, analogous to the compose volume reaper.

See [[arch_target_ecommerce]] (the C# target), [[feedback_no_scope_overclaim]] (the `[x]`
vs `[~]` discipline applied to the proof). Tests: `tests/test_acceptance_app_boot.py` (+10).
