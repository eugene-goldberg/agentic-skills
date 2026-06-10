# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-09 (EOD — 2nd brownfield target onboarded + A67 +
> the Onboarder crew capability). Supersedes all prior hand-offs. Every fact
> below was verified against the live repo/processes at write time.
>
> **THIS SESSION (delta on top of everything below). Three things happened:**
>
> 1. **2nd REAL brownfield target onboarded end-to-end — `fullstack-ecommerce-app`
>    (the FIRST non-Python target: C#/.NET 8 + EF Core + Postgres + React, MIT).**
>    Cloned → assessed → greened its baseline (was 21/75 red → **75/75**, by honest
>    production fixes, no assertion weakening) → wired `.agentic-skills.json`
>    (`dotnet test backend/Ecommerce.sln`), `.gitignore`, `integration` branch →
>    symlinked → **graphify proved C# grounding (915 C# nodes, 747 symbol-level)** →
>    stood up **Postgres in Docker** (`ecommerce-pg` :5433) + EF `InitialCreate`
>    migration (17 tables + seed) + gitignored `appsettings.json` (+ committed
>    `appsettings.example.json`, `dev-setup.sh`, `DEV_SETUP.md`) → **booted +
>    live-verified** the backend (:5096; register/login/JWT/seeded reads all 200)
>    and the frontend (:5173, `npm run build` clean). Target `main≡integration`
>    @ `9e98e86` (a SEPARATE repo — we never push it). Memory: `arch_target_ecommerce`.
>
> 2. **A67 — language-agnostic per-BL test scoping (the harness enabler).** The
>    per-BL gate was pytest-hardcoded (`_bl_test_files` `.py`-only → every C# BL
>    falsely `no_tests`; scoping appended `.cs` paths `dotnet test` rejects).
>    Generalized to `_TEST_FILE_CONVENTIONS` (.cs/.go/.java/.kt/.rb/JS-TS unit;
>    `.spec.*`/e2e excluded) + `test_file_globs` override; non-pytest runners run
>    `test_cmd` as-is; verdict stays exit-code-authoritative. Ledger **A67**.
>    Shipped `7566120`. Full suite **408 passed** (1 unrelated Milvus-flake).
>
> 3. **The Onboarder crew capability (operator-requested).** Turned the manual
>    onboarding above into a reusable crew member: **the Janitor/Ops-Steward in
>    ONBOARDING MODE**. **BINDING SCOPE (operator correction):** onboarding =
>    fulfilling the ENVIRONMENT prerequisites a `git clone` doesn't bring (deps,
>    runtime, DB/services, gitignored config, missing migrations, gate config,
>    branch) — it **NEVER edits the target's committed source to fix pre-existing
>    defects** (those are FLAGGED, not fixed). Shipped: the `onboarder` skill,
>    `orchestrator._onboarding_flow`/`run_onboarding` (with INDEPENDENT
>    postcondition verification — `onboarded` only when BOTH agent verdict AND the
>    orchestrator's own check pass), `POST /api/projects/{repo}/onboard`,
>    `scripts/onboard_target.py`, `ONBOARDING.md`, `tests/test_onboarding_flow.py`
>    (+7). Commits `76312b3`→`e256c7c`→`ada209a`. Memory: `arch_onboarder_capability`.
>    **HONEST: wired + unit-tested, NOT live-proven; operator-invoked (no
>    auto_onboard trigger yet).**
>
> **HOW TO INVOKE ONBOARDING** (full ref `ONBOARDING.md`): harness server up +
> target symlinked under `webapp/backend/repos/<repo>` + repo not yet onboarded →
> `python scripts/onboard_target.py <repo>` (or `POST .../onboard`). Ends
> `onboarding.done` (→ `/run-brief`-ready) or `onboarding.escalated`.

---PROMPT START---

You are the **architect** of the agentic-skills project. Read `CLAUDE.md` and
`THESIS.md` first. The mission: build a **fully autonomous AI crew** that adds
complex features to real brownfield repos with no human in the loop — grounded,
self-correcting, honest, cumulative. **The thing being built is the crew.**

## OPERATING DOCTRINE — read twice (hard-won, BINDING on you)

1. **Improve the CREW, generally. Do NOT accommodate a specific brownfield
   condition.** Every move = *"what does the crew gain?"* When you hit a target
   condition, ask *"what GENERAL capability closes this whole class?"* and build
   THAT. (This session: hand-onboarding one repo → the general Onboarder crew
   member; a pytest-only gate → A67 language-agnostic scoping.)

2. **You are the architect with DELIVERY accountability. Make the engineering
   calls and OWN them.** No "option A/B/C — your call?" menus for decisions that
   are yours. Decide, build, verify, report. (Surface a genuine governance/trust
   call; decide everything else.)

3. **The 95% rule is rigor-BEFORE-acting, NOT stop-and-ask.** Research, ground
   every load-bearing claim in raw source, verify — then act decisively.

4. **Don't hand-operate the crew.** Each crew agent is a full Claude Code
   subprocess. Remove the *structural* barriers; don't do its work by hand.

5. **Verification discipline.** No "X works / is broken / never fired" claim until
   checked against the RAW artifact (a command that ran, a file that exists, a
   test that passed, the log line). Mark Verified vs Hypothesis.

6. **Never claim a capability's SCOPE beyond traced code paths (BINDING,
   2026-06-09).** "Works on path X" ≠ "the crew does Y everywhere." Distinguish
   `[x]` SHIPPED-AND-LIVE-PROVEN from `[~]` IMPLEMENTED-BUT-UNIT-TESTED. A mocked
   test proves wiring, not behavior under a real run. (The Onboarder is `[~]`.)

7. **Scope of onboarding (operator, 2026-06-09, BINDING).** "Onboarding" = the
   crew/harness fulfil the ENVIRONMENT prerequisites a `git clone` lacks so the
   crew CAN begin (deps, runtime, services/DB, gitignored config, missing
   migrations, gate config, branch). Onboarding is **NOT** rectifying pre-existing
   defects in the committed source — flag those, never fix them in onboarding.

## Branch model (BINDING)
Work on **`development`**, fast-forward into **`main`** when verified. Only live
branches. **Both at `ada209a`** (verified dev≡main, 2026-06-09 EOD). Tree clean
after you commit the memory/hand-off (see below).
Remote: `origin` (github.com/eugene-goldberg/agentic-skills) — **`ada209a` is
UNPUSHED** (origin/main at `488b7a0`; **4 commits ahead**: A67 + 3 onboarder).
Operator pushes when ready: `git push origin main development`. Harness tests:
`cd webapp/backend && .venv/bin/python -m pytest tests/ -q --deselect tests/test_findings_ledger.py::test_concurrent_append_no_torn_lines --deselect tests/test_compute_ui_coverage.py::test_unmerged_bls_ignored`
→ **~412 passed**. Known load-flakes (pass in isolation, NOT regressions, do not
"fix" without deterministic repro): `test_findings_ledger::test_concurrent_append_no_torn_lines`,
`test_compute_ui_coverage::test_unmerged_bls_ignored`, and
`test_lessons_index::test_milvus_backend_roundtrip` (Milvus-contention timeout).

## Verified running processes (re-verify with `lsof -nP -iTCP:<port>`)
- **Harness orchestrator: PID 14484**, uvicorn `127.0.0.1:8000` — **STALE.** It
  predates ALL this session's work (started ~`96a5b17`); it does **NOT** have A67,
  the `onboarder` skill, or the `/onboard` endpoint. **To use onboarding OR run a
  C# sprint you MUST restart it on `ada209a`** (SIGTERM, not kill -9 — reaps Docker
  stacks): `kill -TERM 14484`, wait for `:8000` free, then
  `cd webapp/backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
  (nohup to a log). After restart re-verify: `from app.routers import projects;
  any('/onboard' in r.path for r in projects.router.routes)` is True.
- **fullstack-ecommerce-app** dev stack (up now, for browsing/manual use):
  Postgres `ecommerce-pg` :5433, backend :5096 (pid 42412), frontend :5173
  (pid 49002 → http://localhost:5173). Re-boot anytime with the target's
  `./dev-setup.sh --run` (+ `cd frontend && npm run dev`). NOT needed for harness work.
- Milvus stack up (`milvus-minio` "unhealthy" = known false healthcheck). Ollama
  `bge-m3` (1024-dim) up. ALL retrieval is LOCAL.

## THE FRONTIER — what the new session should take on (decide + build, don't ask)
Priority order:

1. **PRIMARY — live-prove the Onboarder (`[~]` → `[x]`).** It's wired + unit-tested
   only. Sequence: (a) **restart the harness on `ada209a`** (PID 14484 is stale);
   (b) re-verify `/onboard` is in the running process; (c) pick a **fresh
   un-onboarded repo** (a small real one — a clean clone NOT yet carrying
   `.agentic-skills.json`), symlink it under `webapp/backend/repos/`, and run
   `python scripts/onboard_target.py <repo>`; (d) confirm it provisions the env,
   writes a valid verdict, the orchestrator's independent verification passes, and
   it ends `onboarding.done`. THAT promotes the Onboarder to `[x]`. Watch for the
   honest failure mode: it tries to fix a pre-existing source bug (it must NOT —
   doctrine #7); if the skill lets it, tighten the skill.

2. **The A66 live-proof (STILL PENDING from the prior session).** A66 (acceptance-
   followup Janitor+remerge) is `[~]` — re-dispatch the pending
   `periodic-habit-goals` badge finding on beaverhabits
   (`dispatch_state=not_merged`) and confirm `merge_retry_post_janitor(ok=true)` +
   `janitor.resolved`. (Carried over; not done this session.)

3. **Stage 3 — cross-target / "community" memory** (the literal mission "cumulative
   across targets"). We now HAVE a 2nd real target (ecommerce, C#) — but it hasn't
   been run through a sprint yet. The cleanest first cross-target signal: run a
   small feature sprint on ecommerce (validates the whole C# crew loop end-to-end,
   incl. the untraced acceptance app-boot), THEN build global lessons graduation.

Smaller standing crew-hardening candidates (all GENERAL):
- **`auto_onboard` flag** in `run_brief` — auto-onboard an un-onboarded repo then
  sprint (the full "point at a repo, walk away"). Deferred deliberately; ship after
  the Onboarder is live-proven.
- **Acceptance app-boot for a non-Python target is UNTRACED** — the acceptance
  phase boots the app for API tests; for ecommerce that needs Postgres + a
  materialized (gitignored) appsettings in the agent worktree. How our acceptance
  flow boots a non-Python app is unverified. Trace it before/with frontier #3.
- Onboarding's independent verification is structural (config/branch/gitignore);
  consider having it actually RUN `test_cmd` to prove execution.
- Host-contention resilience; A56 warm-up telemetry on cold targets;
  `_extract_evidence_summary` prose fallback; gate diff-on-quiet `collected N`.

## Honest caveats / open (do not pretend these are closed)
- **The Onboarder is NOT live-proven.** Wired + 7 unit tests (verifier + task
  builder, mocked — no live agent run). Say "wired + unit-tested, live-proof
  pending," never "the crew onboards repos," until a live `/onboard` succeeds.
- **The ecommerce baseline was HAND-greened** (21→0 red) — a one-off remediation
  the operator approved, NOT onboarding doctrine (onboarding never fixes source).
- **A67 enables the per-BL gate on C#; the acceptance app-boot is untraced.** The
  full C# crew loop has NOT been run.
- **n=2 targets, only 1 (beaverhabits) sprint-proven.** ecommerce is onboarded but
  unproven under a sprint. Stage 3 needs ≥2 sprint-proven real targets.
- **Harness is stale** (PID 14484) — nothing this session is live in it.

## Where to start the new session (concrete first moves)
1. Read `CLAUDE.md`, `THESIS.md`, `ARCHITECTURE_INVARIANTS.md`, then this file.
2. Re-verify: `git log --oneline -1` (expect `ada209a`), dev≡main, **`ada209a` is
   UNPUSHED (4 ahead)**. Skim memory `arch_onboarder_capability` + `arch_target_ecommerce`
   + ledger A67. Read `ONBOARDING.md`.
3. **Run pre-flight** (`PREFLIGHT.md`) — Milvus standalone has died before; verify
   :19530 + Ollama + indexer.
4. Take **Frontier #1 (live-prove the Onboarder)**: restart the harness on
   `ada209a`, re-verify `/onboard` is live, then onboard a fresh un-onboarded repo
   end-to-end and confirm `onboarding.done` with the orchestrator's independent
   verification passing. Promote to `[x]` only after that.

---PROMPT END---
