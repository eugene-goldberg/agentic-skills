---
name: arch_live_acceptance_loop
description: Live-acceptance loop — acceptance boots the WHOLE app (backend+frontend), Playwright-verifies every AC with real evidence, and loops fix→re-test until accepted live or escalates. Built 2026-06-13.
metadata:
  type: project
---

**Operator directive 2026-06-13 (BINDING) — the customer-acceptance standard.**
Acceptance must behave like the paying customer who just received the app: boot
the WHOLE real application, exercise 100% of every acceptance criterion through
the running UI/API (incl. persistence re-checks), and **loop fix→re-test until
every criterion is accepted against the live booted app** — never a build/API
proxy for UI, never a self-reported "verified", never a routine give-up.

Closes the honesty gap where I overclaimed a finished frontend-boot+Playwright-
every-AC loop that was actually backend-only/"improvised"/self-reported.
Supersedes the "frontend boot is a follow-up capability" posture in
[[arch_acceptance_honesty_gap]] / [[arch_zero_escape_chain]].

Spec: `PROPOSAL_LIVE_ACCEPTANCE_LOOP.md`. Shipped on `development`≡`main`
(`8c9912c` spec+schema, `d141aa3` boot+R20-evidence+loop, `69c099b` SKILL+doctrine).

**What was built (8 parts):**
- **A app_boot v2** (`repo_config._normalize_app_boot` + `_normalize_frontend_boot`):
  optional `frontend` sub-block (dir/cmd/pre_cmd/ready_url/base_url_env) + fixed
  `port` (for frontend-hardcoded-URL targets). Backward compatible.
- **B ecommerce contract** (target `.agentic-skills.json`, baseline commit `370f09f`):
  backend `dotnet run --project backend/Ecommerce.Infrastructure --urls
  http://localhost:5096` (port pinned 5096 — frontend hardcodes it in
  `frontend/src/types/Auth.ts`; brief forbids editing frontend/src), pre_cmd
  `bash dev-setup.sh` (pg+appsettings+migrations+dotnet-ef), materialize
  appsettings.example.json; frontend dir `frontend`, `npm install` + `npm run dev
  -- --host --port ${FE_PORT}`.
- **C boot wiring** (`_resolve_app_boot_port` resolves ${FE_PORT}; acceptance prep
  reserves a 2nd free FE port; `_build_acceptance_task` prompt mandates booting the
  real frontend + Playwright-driving every UI AC + persistence re-check + per-AC
  evidence). `acceptance.app_boot.prepared` gains frontend_port/full_app.
- **E R20 evidence-enforce** (`_unverified_criteria` + `_evidence_exists`): an
  ac_coverage entry counts as verified ONLY if it cites a real artifact that EXISTS
  on disk (screenshot/recorded response). Self-report alone = unverified.
- **F convergence loop** (run_brief wraps acceptance; `_acceptance_loop_next` →
  accept|reround|escalate from integrity_ok + dispatched_count;
  `ACCEPTANCE_LOOP_MAX_ROUNDS=5`): boot→exercise→fix→re-boot until accepted live or
  honest escalate. Events `acceptance.loop.{reround,progress,accepted,escalated}`.
- **D acceptance SKILL**: full-app boot bullet + ac_coverage MUST cite real evidence
  + persistence re-check.
- **G** doctrine_spec R17/R20 + CLAUDE.md R-rule rows amended; consistency test green.

**Verification ledger:**
- `[x]` harness code-complete, 506 backend tests pass; deployed to remote
  192.168.12.180 (43 acceptance tests pass on remote).
- `[x]` **FULL-APP BOOT PROVEN** on remote: backend 5096 (HTTP 200, real seeded
  products) + frontend Vite (HTTP 200, real React) booted simultaneously via the
  contract commands. Confirmed `dotnet run --project Ecommerce.Infrastructure` is
  the real host.
- `[~]` **end-to-end live proof IN FLIGHT**: reviews sprint
  `run-20260613T014347Z-e838ee` (the 401 is the canonical defect the loop must
  catch+fix via live UI). Acceptance booting full app + Playwright-per-AC +
  loop-to-clean is NOT yet observed end-to-end — that completes when this sprint
  reaches the acceptance phase. Do NOT claim it proven until the
  `acceptance.app_boot.prepared full_app=true` + per-AC screenshots + a
  `acceptance.loop.accepted` (or honest escalate) are in the trace.

**Update 2026-06-13 (boot-hardening, commit `5874d11`):** the prior run's loop escalated NOT
because the fix failed but because round 2 tested STALE code — the agent backgrounds the boot
on the FIXED port (frontend hardcodes :5096) and a prior round's process lingered, so round 2
polled the old pre-fix binary (proven: a fresh boot of current integration authenticates a real
JWT — no 401). Fix: `_free_app_boot_ports` makes the HARNESS kill any listener on the
backend+frontend ports before each round/attempt boot + reap in finally; frontend pinned to the
CORS-allowlisted **:5173** (`frontend.port` in `.agentic-skills.json`, closes the F3 CORS gap).
Also: classification sharpened (`4f9f0a9`) — a 401/403/500 from the app's OWN endpoint is a
product_bug, never infra_bug. **Convergence (acceptance.loop.accepted) NOT yet proven** —
verification re-run `run-20260613T192653Z-1babd8` IN FLIGHT (the standing objective; see
CONTINUATION_PROMPT.md for the 5-condition /goal). Residual: 500-on-missing-userId (endpoint
should derive reviewer from JWT) + baseline-auth scope decision (operator).

Boot facts: dotnet-ef is a GLOBAL tool at ~/.dotnet/tools (PATH export needed);
backend host = Ecommerce.Infrastructure project; Postgres ecommerce-pg :5433
persistent (shared across runs). `pkill -f bridge.js` (not "spike-node/bridge.js").
