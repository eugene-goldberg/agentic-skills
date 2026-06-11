---
name: arch_target_ecommerce
description: "2nd brownfield target — fullstack-ecommerce-app (C#/.NET 8 + EF Core + Postgres + React); the FIRST non-Python target; wired + baseline-green + bootable 2026-06-09"
metadata: 
  node_type: memory
  type: project
  originSessionId: e0df5d9d-765b-436e-a657-5217d5cb77bd
---

**Second real brownfield target, onboarded 2026-06-09: `MohamadNach/fullstack-ecommerce-app`**
(MIT, ~6 MB). The FIRST **non-Python** target — ASP.NET Core 8 / C# / EF Core /
**PostgreSQL** backend (CLEAN architecture: Domain/Service/Infra/Presentation),
React 18 + TS + Redux + Vite frontend. Lives at
`~/dev/ai-projects/brownfield-targets/fullstack-ecommerce-app`, symlinked into
`webapp/backend/repos/fullstack-ecommerce-app`. The Stage-3 cross-target
cumulative-learning substrate (beaverhabits is the Python n=1).

**Wiring (`.agentic-skills.json`):** agent_branch=`integration`, main_ref=`main`,
doctrine=`brownfield`, **test_cmd=`["dotnet","test","backend/Ecommerce.sln","--nologo"]`**.
Per-BL gate is **Docker-free/DB-free** — xUnit+Moq unit tests, no DbContext.

**What it took (target commits on main≡integration):**
- `a3519f5` — **greened the baseline** (was 21/75 red): catch-all anti-pattern
  masking typed exceptions (24 sites) + real bugs (Shipment NPE, BaseService
  mapping/EntityNotFoundException). Production fixes only, no assertion weakening
  → **75/75 green**.
- `ad7e829` — greened the **frontend** prod build (unused imports + `''||null`).
- `9e98e86` — **dev environment**: committed the missing **EF InitialCreate
  migration** (upstream `.gitignore` wrongly excluded `Migrations/` — that's why
  no schema was ever committed; added negations), `appsettings.example.json`
  template (real `appsettings.json` stays gitignored), `dev-setup.sh` (idempotent
  Postgres-16 container + appsettings + migrate), `DEV_SETUP.md`.

**Live infra (this session):** Postgres 16 container **`ecommerce-pg`** on host
port **5433**→5432, volume `ecommerce-pg-data`, db `ecommerce_dev` / user+pw
`ecommerce`. Backend boots **http-only** on :5096 (app has `UseHttpsRedirection`
→ give it ONLY an http URL to avoid 307s on API tests). Schema applied + seeded
(17 tables, products/categories). **Verified end-to-end live:** register→login→
JWT→authed GET all 200; frontend dev :5173 HTTP 200; `npm run build` clean.
Boot anytime: `./dev-setup.sh --run` (needs `~/.dotnet/tools` on PATH for
`dotnet-ef`; installed 8.0.11).

**The harness enabler:** [[arch_gate_multitoken_testcmd]]-style generalization —
**A67** (`7566120` in agentic-skills): language-agnostic per-BL test scoping
(`_bl_test_files` spans .cs/.go/.java/etc.; non-pytest runners run `test_cmd`
as-is). graphify already grounds C# (915 C# nodes, 747 symbol-level).

**SPRINT-PROVEN 2026-06-11 — the full C# crew loop works end-to-end.** First feature
sprint (Wishlist, backend-only) `run-20260610T215031Z-05f865`: **4/4 BLs `merged_full`,
0 escalations, regression_checkpoint green, acceptance PASS (7/7 API journeys),
closure 0 violations.** Scorecards 92-95 Pass. See `EXPERIMENT_ecommerce_wishlist.md`
§9. This makes ecommerce the **2nd sprint-proven real target** (beaverhabits=Python n=1)
→ the **Stage-3 cross-target cumulative-learning substrate is now in place.**
- **Acceptance native-boot RESOLVED (exceeded):** the prior OPEN "how does acceptance
  boot a non-Python app" — the acceptance agent **improvised** it: `dotnet run` on
  `:5097` (avoided the stale baseline build holding `:5096`) against `ecommerce-pg`
  Postgres + a self-materialized gitignored `appsettings.json`, ran 7 real HTTP
  journeys, even surfaced a pre-existing cart-DI 500 (FIND-01). **Caveat ([[feedback_no_scope_overclaim]]):**
  this was AGENT improvisation, NOT a codified harness path — the acceptance skill is
  still compose-centric. Codifying native-boot acceptance is the logical follow-up.
- **Two infra blockers surfaced + fixed by the architect (it took 3 launches):** A68
  (Milvus auto-restart wait 30s ≪ ~3.5-min segment reload → `docker restart` + 300s
  poll) and Milvus etcd-lease loss under host contention (16 GB Mac, Docker was 12 GB
  → host swap → keepalive miss → self-exit; fixed via `ops/milvus/` hardened deploy:
  session.ttl 30→180, retryTimes 30→60, requestTimeout 10000→30000, restart:
  unless-stopped + Docker memory 12→8 GB). Run #3 had Milvus `RestartCount: 0` across
  the whole sprint. See `DESIGN_SHORTCOMINGS.md` A68 + [[local-milvus]].
