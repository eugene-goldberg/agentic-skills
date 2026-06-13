# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-13. Supersedes all prior hand-offs. **Headline: this session
> built the LIVE-ACCEPTANCE LOOP — acceptance now boots the WHOLE app (backend+frontend),
> Playwright-exercises every acceptance criterion with real on-disk evidence + persistence
> re-checks, and loops fix→re-boot→re-test until live-clean or honest escalation. It is
> mechanically proven (caught the canonical review-submit 401, auto-dispatched a fixer that
> edited the code, re-booted, re-exercised). A verification re-run is IN FLIGHT to prove it
> CONVERGES to `acceptance.loop.accepted`.**

---PROMPT START---

You are the **architect** of agentic-skills. Read `CLAUDE.md` + `THESIS.md` first. Mission:
a fully autonomous AI crew that ships complex features into real brownfield repos with no
human — grounded, self-correcting, honest, cumulative. Doctrine unchanged (quality-over-
speed, no-abort, improve-the-crew, **95%-verified-before-claim**, no-scope-overclaim `[x]`
live-proven vs `[~]` unit-only). **BINDING operator feedback this session: stop asking for
confirmation — investigate→fix→verify autonomously until the objective is met; and never
claim a fix at <95% verified.** Honor `.claude/memory/`.

## THE CURRENT OBJECTIVE (a `/goal`-style measurable condition)
Prove the ecommerce-reviews live-acceptance loop CONVERGES. Done only when ALL hold, each
shown via quoted command output:
1. latest reviews run log has `orchestrator.acceptance.loop.accepted` with `integrity_ok=true`
   and empty `unverified_criteria` (an `acceptance.loop.escalated` qualifies ONLY if its sole
   remaining item is the operator-approved out-of-scope **baseline JWT-audience/auth** defect);
2. that run's `acceptance.app_boot.prepared` shows `full_app=true`, backend `:5096` + frontend `:5173`;
3. a live authenticated review submit returns **2xx (NOT 401)** — quoted from an api-log/curl;
4. acceptance evidence (report.json + screenshots/ + fixtures/api_logs/) committed in-target under
   `_brownfield/features/ecommerce-reviews/acceptance/` on `integration` (quote `git ls-files | grep acceptance`);
5. no target baseline-auth change beyond operator-approved scope.
If any fail → diagnose→fix (harness, or get operator scope decision)→re-run until all hold.
(`/goal` is a real built-in v2.1.139+; its evaluator reads the TRANSCRIPT, so you must SURFACE
the proving grep/curl output into chat. You cannot self-invoke `/goal`; the operator pastes it.)

## Git state
**`development` ≡ `main` ≡ `origin` @ `5874d11`** (clean; only untracked `MIGRATION_PLAN_infra_to_180.md`).
This session's commits (newest first): `5874d11` boot-port hardening · `a806cdb` in-target
acceptance persistence · `4f9f0a9` infra_bug-vs-product_bug classification · `dda59b8` memory ·
`69c099b` SKILL+doctrine R17/R20 · `d141aa3` boot wiring+R20-evidence+convergence loop ·
`8c9912c` spec + app_boot v2 schema · `bb3ef2e` retrieval has_index short-circuit.
Spec doc: `PROPOSAL_LIVE_ACCEPTANCE_LOOP.md`. Memory: `arch_live_acceptance_loop`,
`arch_retrieval_has_index_shortcircuit`.

## THE REMOTE CREW HOST (192.168.12.180) — the crew runs HERE, Mac is the control terminal
SSH: `ssh -i ~/.ssh/id_ed25519_18012 -o IdentitiesOnly=yes user@192.168.12.180` (user is `user`;
sudo needs a password we don't have = operator-only). Strip SSH banner noise by piping through
`grep -v "post-quantum\|store now\|may need to be upgraded\|openssh.com"`.
- **Harness**: uvicorn `127.0.0.1:8000`, **pid 1412646** (drifts — re-check `lsof -tnP -iTCP:8000 -sTCP:LISTEN`).
  Restart: `cd ~/dev/ai-projects/agentic-skills/webapp/backend && nohup env PATH="$HOME/.local/bin:$PATH" .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >> ~/harness.log 2>&1 & disown`
- **Docker**: `milvus-standalone/minio/etcd` (vector store :19530) + `ecommerce-pg` (postgres:16 `:5433`, db `ecommerce_dev`, user/pass `ecommerce`/`ecommerce`).
- **Ollama**: bge-m3, systemd (restart=sudo=operator). `dotnet` 8 + global `dotnet-ef` at `~/.dotnet/tools` (PATH-export needed). `graphify`/`claude`/`uv`/node18 present.
- Target: `~/dev/ai-projects/brownfield-targets/fullstack-ecommerce-app` (symlinked into `webapp/backend/repos/`), on branch `integration`. `webapp/.env` uses localhost for Ollama+Milvus (correct, local to remote).
- **Boot the app (proven recipe)**: `bash dev-setup.sh` (pg+appsettings+migrations) then
  `ASPNETCORE_ENVIRONMENT=Development dotnet run --project backend/Ecommerce.Infrastructure --urls http://localhost:5096`;
  frontend `cd frontend && npm install && npm run dev -- --host --port 5173`. Seeded users: `email1..6@example.com`, password `123456789m`. Free fixed ports first: `fuser -k 5096/tcp 5173/tcp`.

## IN-FLIGHT verification run (CHECK FIRST)
`run-20260613T192653Z-1babd8`, log `~/reviews_rerun2.log`, `skip_po=True`, payload `~/reviews_rerun_payload.json`.
At write time: 4/5 BLs done (at `reindex_after_engineer.BL-0004`), launcher ALIVE, heading to BL-0005 →
`sprint_complete` → **the acceptance loop** (the verdict that matters). Monitor: bounded-wait loop
grepping for `acceptance.loop.(accepted|escalated)` / `acceptance.app_boot.prepared` / `closure_check.done`.
NOTE: skip_po engineers are NOT instant no-ops — they re-engineer (~10-20min/BL, committing per-criterion
gates, e.g. integration HEAD `bdf839e`). `index_initial` re-indexes every run (~15min, benign — agents
ground via has_index short-circuit). So a full run is ~1.5-2.5h.
**On the verdict**: if `acceptance.loop.accepted` + integrity_ok=true → objective MET (surface the proof,
update memory, tell operator). If `escalated` → read `traces_archive/<run_id>/acceptance/report.json`
ac_coverage + findings; if the only residual is the baseline JWT-audience/auth defect → that's the operator
scope call; any OTHER residual → diagnose→fix→re-run.

## What the loop proved already (run-20260613T124519Z-05b6e9, the prior run)
Full-app boot fired → real Playwright/API caught the review-submit **401** → classified `product_bug`
→ 5 fixers auto-dispatched → fixers edited real code (`reviewService.ts` attaches bearer; `Program.cs`/
`JwtBearerConfiguration` sets `ValidAudience`) → re-booted → re-exercised → honest escalation. The
non-convergence was NOT a fix failure: **round 2 tested STALE code** because the agent backgrounds the
boot on the FIXED port and a prior round's process lingered (proven: a fresh boot of current integration
accepts a real JWT — no 401). That's why `5874d11` makes the **harness own/free the boot ports per round**
+ pins the frontend to the CORS-allowlisted `:5173`. The current run verifies that fix converges.

## Known residual defects / open items
- **[x] F1 JWT `ValidAudience`**: FIXED in code + verified (fresh boot authenticates a real token).
- **[~] 500-on-missing-userId** (real, SECONDARY): `POST /reviews/product/{id}` 500s (DB error in
  `BaseRepository.CreateAsync`, `ReviewManagement.cs:138`) when the body omits `userId` — it should derive
  the reviewer from the JWT, not require it in the body (also a security smell: trusting body userId). With
  `userId` present it works (`409` on dup = correct). Acceptance journeys include userId, so it doesn't block
  the core ACs. Decide: fix (derive from token) or log.
- **Baseline auth scope decision (operator)**: the JWT-audience config lives in baseline auth (`Program.cs`),
  which the brief said "do NOT modify auth." The fixer touched it anyway. Decide whether baseline-auth fixes
  are in-scope for feature crews or always escalate.
- **index_initial re-indexes every run** (~15min CPU) — never short-circuited even when the collection is
  populated. High-leverage remote-speed win (the has_index op exists; wire it into index_initial too).
- **Deferred**: standalone `/run-acceptance` endpoint lacks the convergence loop + dispatch builder (only
  `run_brief` has them) — wiring it would let you re-prove the loop WITHOUT a full sprint rebuild.
- **Per-run DB hygiene**: reviews persist in the shared `ecommerce-pg` across runs → dup-409 can mask the
  create path. This session manually `DELETE FROM reviews` before the re-run; acceptance should reset/seed
  fresh per run (or use fresh users) for repeatability.

## Honest verification ledger
`[x]` live-acceptance loop built + 506 harness tests green + deployed to remote (43 acceptance tests pass there).
`[x]` full-app boot PROVEN (backend :5096 + frontend Vite both 200, real data/UI). `[x]` loop mechanically
proven (caught 401 → product_bug → fixer edits code → re-boot → re-exercise → honest escalate). `[x]` F1
fix verified in code. `[x]` in-target acceptance persistence shipped (`_persist_acceptance_in_target`, 4
tests). `[~]` loop CONVERGENCE to `acceptance.loop.accepted` — verification re-run IN FLIGHT (the standing
objective). `[ ]` 500/userId-derivation fix. `[ ]` baseline-auth scope decision.

---PROMPT END---
