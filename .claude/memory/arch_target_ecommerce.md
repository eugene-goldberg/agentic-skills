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

**OPEN (honest, not done):** the harness **acceptance phase** boots the app for
API testing — for THIS target that needs Postgres + a materialized
`appsettings.json` in the agent worktree (worktrees only carry tracked files, so
the gitignored appsettings won't be there). How our acceptance flow boots a
**non-Python** app is **UNTRACED** — that's the E12 shakedown's job. Per-BL gate
needs none of this (Moq). See [[feedback_no_scope_overclaim]] — don't claim the
full crew loop works on C# until a live shakedown proves it.
