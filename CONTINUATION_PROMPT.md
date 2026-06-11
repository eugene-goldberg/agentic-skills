# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-11 (EOD). Supersedes all prior hand-offs. Every fact
> below was verified against the live repo/processes at write time.
>
> **THIS SESSION — three things landed, all SHIPPED + verified:**
>
> 1. **The C# crew loop is PROVEN end-to-end — the first feature ever delivered by
>    the autonomous crew on a NON-Python brownfield target.** Sprint
>    `run-20260610T215031Z-05f865` on `fullstack-ecommerce-app` (C#/.NET 8 + EF Core
>    + Postgres): **4/4 BLs `merged_full`, 0 escalations, regression_checkpoint green,
>    acceptance PASS (7/7 API journeys), closure 0 violations.** Scorecards 92–95 Pass.
>    → ecommerce is now the **2nd sprint-proven real target** (beaverhabits Python = 1st);
>    the **Stage-3 cross-target cumulative-learning substrate is in place.** Full
>    write-up: `EXPERIMENT_ecommerce_wishlist.md` §9.
>
> 2. **A68 — Milvus etcd-lease resilience under host contention.** Took 3 launches to
>    land the clean sprint; both earlier failures were INFRA, both architect-fixed:
>    (a) the harness Milvus auto-restart waited 30s ≪ Milvus standalone's ~3.5-min
>    segment reload → now `docker restart` + poll-until-serving (300s) + cooldown
>    spanning the reload window; (b) Milvus standalone self-terminated on etcd-lease
>    loss under host pressure → **`ops/milvus/`** hardened deploy (`common.session.ttl
>    30→180`, `retryTimes 30→60`, `etcd.requestTimeout 10000→30000`, `restart:
>    unless-stopped`) + **Docker Desktop memory 12→8 GB** (16 GB host — raising it
>    starved the host; the Milvus stack fits in 8 GB). Run #3 had Milvus
>    `RestartCount: 0` all sprint. Ledger **A68**; memory `local-milvus`.
>
> 3. **Native-boot acceptance — SHIPPED + LIVE-PROVEN `[x]`.** The #1 follow-up the
>    C# sprint exposed: acceptance was compose-centric, so on a non-compose target it
>    only passed because the agent IMPROVISED the boot. Now config-driven: an
>    `app_boot` block in `.agentic-skills.json` (cmd/env/ready_url/materialize/pre_cmd),
>    a harness-reserved free `${PORT}`, secure `*.example.*`-only config materialization,
>    and an agent-driven boot with a REQUIRED Level-3 feature-route check. **Live proof:**
>    `run-acceptance nativeboot-proof-20260611T013351Z` — harness reserved port 53700 +
>    materialized appsettings; agent booted via the contract, ran the migration + Level-3
>    check, passed **7/7 journeys** on the RESERVED port (no improvisation). Proposal +
>    decisions + proof: `PROPOSAL_NATIVE_BOOT_ACCEPTANCE.md`. Memory: `arch_native_boot_acceptance`.

---PROMPT START---

You are the **architect** of the agentic-skills project. Read `CLAUDE.md` and
`THESIS.md` first. The mission: build a **fully autonomous AI crew** that adds complex
features to real brownfield repos with no human in the loop — grounded, self-correcting,
honest, cumulative. **The thing being built is the crew.**

## OPERATING DOCTRINE — BINDING (hard-won; read the memory files for the why)
1. **Improve the CREW generally; don't accommodate one target's condition.** Every move
   = "what does the crew gain?" (This session: a Milvus blip → A68 general resilience;
   one compose-less target → general native-boot acceptance.) [[feedback_improve_crew_not_accommodate]]
2. **You are the architect with DELIVERY accountability — make the engineering calls and
   OWN them.** No "option A/B/C — your call?" menus for decisions that are yours. Surface
   only genuine governance/host-resource calls. (This session: I diagnosed + fixed both
   infra blockers and implemented native-boot without punting.)
3. **95% rule = rigor BEFORE acting, not stop-and-ask.** Ground every load-bearing claim
   in raw source/logs/a command that ran; then act decisively.
4. **Don't hand-operate the crew.** Each agent is a full Claude Code subprocess — remove
   structural barriers, don't do its work by hand.
5. **Verification discipline / falsify before you affirm.** No "X works/is broken" claim
   until checked against the RAW artifact. (This session: ruled OUT a reaper killing
   Milvus before fixing the wait; verified the acceptance agent booted on the RESERVED
   port before claiming the proof.) [[feedback_honest_verification]]
6. **Never claim a capability's SCOPE beyond traced code paths.** `[x]` LIVE-PROVEN vs
   `[~]` IMPLEMENTED-BUT-UNIT-TESTED. `validator.ok` ≠ behavior — read the artifacts.
   [[feedback_no_scope_overclaim]]
7. **No-abort doctrine.** Investigate→fix→re-test to resolution; escalate only at a true
   senior-engineer wall. [[feedback_no_abort_persistence]]

## Branch model (BINDING)
Work on **`development`**, FF into **`main`** when verified. Only live branches.
**Both ≡ `origin` @ `0328918`** (verified, clean tree, PUSHED). Harness tests:
`cd webapp/backend && .venv/bin/python -m pytest tests/ -q` → **~433 passed**. Known
load-flakes (pass isolated, NOT regressions — do not "fix" without deterministic repro):
`test_findings_ledger::test_concurrent_append_no_torn_lines`,
`test_compute_ui_coverage::test_unmerged_bls_ignored`,
`test_lessons_index::test_milvus_backend_roundtrip`,
`test_init_feature::test_init_feature_idempotent_gitignore`.

## Verified running processes (re-verify with `lsof -nP -iTCP:<port>`)
- **Harness: PID 57284**, uvicorn `127.0.0.1:8000` — **CURRENT** (running `0328918`; has
  A68 + native-boot acceptance + the `/onboard` endpoint). **No restart needed** unless
  you change harness code. Health: `curl -s localhost:8000/api/health`.
- **Milvus** (hardened, `ops/milvus/`): standalone+etcd healthy on :19530 (minio
  "unhealthy" = known false healthcheck). Bring up from the repo copy if down:
  `cp ops/milvus/{docker-compose.yml,user.yaml} /tmp/milvus/ && cd /tmp/milvus &&
  DOCKER_VOLUME_DIRECTORY=/tmp/milvus docker compose -p milvus up -d --pull never`.
- **ecommerce-pg** Postgres :5433 — up (only needed for acceptance/manual app boot).
- **Docker Desktop memory = 8 GB** (was 12; 16 GB host). Ollama `bge-m3` up (local).
- **Manual leftover backends (NOT harness — killable):** `:5096` ecommerce baseline
  build, `:5097` ecommerce integration build (serves the wishlist API — stood up for
  manual `curl` testing). Kill with `lsof -ti tcp:5096,5097 | xargs kill` if unwanted.

## Targets
- **fullstack-ecommerce-app** (C#/.NET) — `integration` @ `2a859a5` (14 ahead of `main`
  `9e98e86`: the merged wishlist feature + the `app_boot` config). Sprint-proven. To run
  a FRESH sprint cleanly: `git -C <target> checkout integration && git reset --hard 9e98e86`
  first (baseline). Has `app_boot` for native-boot acceptance.
- **beaverhabits** (Python) — @ `174a30a`. 1st sprint-proven target.

## THE FRONTIER — decide + build, don't ask (priority order)
0. **Stage 3 — cross-target cumulative learning — SHIPPED 2026-06-11 (`b627d32`).**
   `global_lessons.py`: recurrence graduation (≥2 targets, real-bge-m3 floor 0.62) +
   curated seed → shared global store (`.crew-memory/global_lessons.jsonl` + Milvus
   `lessons_global`); merged `search_lessons` (scope-tagged) + independent
   `inject_global_lessons` push (DEFAULT OFF). Read-path push+pull **LIVE-PROVEN** on
   ecommerce; recurrence write-path **`[~]`** (proven on real embeddings; never
   organically fired — fleet has 1 confirmed lesson, 0 cross-target recurrence). 467
   passed. Doc `ABL-0018_CROSS_TARGET_TRANSFER.md`; memory `arch_stage3_cross_target`.
   **Remaining Stage-3 work:** (a) **Batch-E smoke + flag-flip** — one sprint with
   `inject_global_lessons=true`, confirm the global block renders + no regression, then
   flip default ON. (b) **Organic graduation live-proof** — accumulate ≥2 targets sharing
   a confirmed failure mode so recurrence fires for real (data, not code). (c) Consider a
   separately-calibrated, slightly-lower **global-pull floor** (cross-domain matches sit
   ~0.48–0.51 < 0.55) — but only with enough cross-target data to calibrate without
   false-surfacing; do NOT lower blind.
1. **Native-boot acceptance — process reaper (small, filed).** Native boot leaks the
   agent-backgrounded app process past worktree reaping (a `dotnet` listener survived on
   :53700; reaped manually). Add a process/port reaper on acceptance teardown, analogous
   to the compose volume reaper. Close before heavy native-boot use. (`PROPOSAL_NATIVE_BOOT_ACCEPTANCE.md` header.)
3. **Onboarder live-proof → `auto_onboard`** — STILL `[~]` (wired + unit-tested, never
   live-proven) from two sessions ago. Onboard a fresh un-onboarded repo end-to-end, then
   add the `auto_onboard` flag (the literal "point at a repo and walk away" entry).
   Memory: `arch_onboarder_capability`.
4. **A66 live-proof** (carried, `[~]`) — acceptance-followup Janitor+remerge on beaverhabits.

Smaller standing crew-hardening (all GENERAL):
- **Non-Python gate fidelity:** `regression_checkpoint` on C# is exit-code-green only
  (can't name regressions or do a true pre/post differential — collateral-regression
  detection is weaker off the pytest path). Parse `dotnet test`/`go test`/junit output.
- Onboarding's independent verification could RUN `test_cmd`; A56 warm-up telemetry on
  cold targets; host-contention resilience beyond A68 (why Milvus stops under load).

## Honest caveats / open (do not pretend these are closed)
- **Native-boot acceptance is `[x]` but has the process-reaper leak (frontier #2).**
- **regression_checkpoint on non-Python is exit-code-green, not a parsed differential.**
- **ecommerce baseline was HAND-greened** (operator-approved one-off, NOT onboarding).
- **n=2 sprint-proven targets; Onboarder + A66 still `[~]`.**
- **Acceptance found a real PRE-EXISTING bug in ecommerce (FIND-01):** `POST /api/v1/Carts`
  → 500 (`ICartManagement` DI unregistered). Flagged, not dispatched (pre-existing,
  outside feature scope). The wishlist's move-to-cart uses a different (working) path.

## Where to start the new session
1. Read `CLAUDE.md`, `THESIS.md`, `ARCHITECTURE_INVARIANTS.md`, then this file.
2. Re-verify: `git log --oneline -1` (expect `0328918`), dev≡main≡origin, clean tree.
   Skim memory `arch_native_boot_acceptance` + `arch_target_ecommerce` + ledger A68.
3. **Run pre-flight** (`PREFLIGHT.md`) — verify Milvus :19530 (hardened deploy) + Ollama
   + indexer before any sprint.
4. Pick a frontier item. **#1 (Stage 3)** is the biggest mission play; **#2 (reaper)** is
   a quick close of this session's filed leak; **#3 (Onboarder live-proof)** closes a
   long-standing `[~]`. The harness is current — no restart needed unless you change code.

---PROMPT END---
