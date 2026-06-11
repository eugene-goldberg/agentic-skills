# Experiment — Wishlist on fullstack-ecommerce-app (FIRST C#/.NET crew-loop shakedown)

> Authored 2026-06-09. **The first sprint ever run against a non-Python target.**
> Target: `fullstack-ecommerce-app` (C#/.NET 8 + EF Core + Postgres + React, MIT) —
> onboarded + baseline-green (75/75) + bootable, but **never run through a crew
> sprint.** This is the E12 shakedown referenced in `arch_target_ecommerce`.
>
> **This is explicitly a SHAKEDOWN, NOT a discovery stress test.** Exp 1/1b
> (Kanban, dependencies) already proved the crew discovers and delivers hard
> correctness — *on Python.* The open question here is narrower and prior:
> **does the language-agnostic crew loop actually drive a C# sprint end-to-end?**
> So the feature is chosen for *low ambiguity* (a near-mirror of an existing
> pattern), to isolate the harness/loop as the variable under test. The hard-
> correctness discovery test on C# comes *after* the loop is proven.

## 1. Why a shakedown first (the architect call)

The full C# crew loop has **never executed**. Two distinct unknowns sit on top of
each other:

- **U1 — Does the harness drive a C# sprint at all?** PO decomposition over a C#
  graph; engineer writing C#/xUnit; the **A67** language-agnostic per-BL gate
  (`dotnet test`, Moq, no DB) returning honest verdicts; auto-merge to
  `integration`; the regression checkpoint re-running `dotnet test`.
- **U2 — Can the crew do *hard* C# correctness unprompted?** (the Exp-1b-class
  question, on a new language).

Running a hard feature first **conflates U1 and U2**: if it wedges, we can't tell
whether the crew can't reason about the feature or the harness can't run C#. So
this sprint deliberately drives a feature with *almost no* feature-ambiguity and
treats **U1 as the thing under test**. U2 gets its own later experiment once U1 is
green. (Doctrine #1 — the crew *gains* a proven language-agnostic loop; that's the
general capability, not "we shipped a wishlist.")

## 2. The feature — Wishlist / Favorites (backend-only)

Grounded directly in the existing **Cart → CartItem** aggregate, which the crew
can mirror almost 1:1. Verified against source:

- Entities to mirror: `Domain/src/Entities/CartAggregate/Cart.cs`,
  `CartItem.cs` → new `WishlistAggregate/Wishlist.cs`, `WishlistItem.cs`.
- Service to mirror: `Service/src/CartService/` (`ICart*`, `Cart*.cs`,
  `*Dtos.cs`) → new `WishlistService/`.
- Repository to mirror: `Infrastructure/src/Repository/` Cart repo → Wishlist repo
  + `ApplicationDbContext.cs` DbSet + relationship config.
- Controller to mirror: `Presentation/src/Controllers/CartController.cs` +
  `CartItemController.cs` → `WishlistController.cs`.
- Tests to mirror: `Ecommerce.Tests/src/Service/CartItemServiceTests.cs`
  (xUnit + Moq, mock the repo) → `WishlistServiceTests.cs`.

User-facing surface (one user → one wishlist → many items → each item one product):

- `GET    /api/v1/wishlists/user/{userId}` — the user's wishlist with items
- `POST   /api/v1/wishlists/{wishlistId}/items` — add a product
- `DELETE /api/v1/wishlists/{wishlistId}/items/{itemId}` — remove a product
- `POST   /api/v1/wishlists/{wishlistId}/items/{itemId}/move-to-cart` — the one
  genuinely cross-aggregate operation (reads WishlistItem, calls the existing
  Cart service, removes from wishlist)

### 2a. The two non-obvious correctness requirements (kept, on purpose)

A pure copy of Cart would be trivial. Two requirements make it a *real* (if small)
test of grounding, stated like a normal ticket — not telegraphed how to implement:

1. **Uniqueness.** A product appears **at most once** in a user's wishlist
   (unlike CartItem, which carries a quantity). Adding a product already present
   must not create a duplicate (idempotent or 409 — crew's call), and this must be
   enforced **server-side in the service**, not only by a DB constraint. *(Probe:
   add product P twice → second call does not create a second row.)*
2. **Move-to-cart integrity.** `move-to-cart` must (a) add to the existing Cart
   via the existing Cart service/abstractions — **not** reimplement cart logic —
   and (b) remove the item from the wishlist, as one consistent operation. *(Probe:
   move item → it is in the cart AND gone from the wishlist; partial state is a
   bug.)*

### 2b. Scope: BACKEND ONLY (frontend explicitly excluded)

Owned decision. The per-BL gate's `test_cmd` is `dotnet test backend/Ecommerce.sln`
— backend only. Adding the React frontend pulls in a second toolchain (npm/vite)
**and** would push the acceptance phase toward Playwright, compounding the one big
unknown (§4). For a first language shakedown, minimize variables: API + service +
xUnit. The frontend wishlist UI is a clean follow-up once U1 is green.

## 3. Expected BL decomposition (PO owns this — sketch for calibration only)

~3–4 BLs, shaped so each BL's testable logic lands in the **service layer** where
Moq works (the gate is DB-free):

- **BL-0001 — Domain + persistence.** `Wishlist`/`WishlistItem` entities, EF
  config + DbSet in `ApplicationDbContext`, `IWishlistRepository` + impl, EF
  migration. *(Watch item: entity/migration code is light on unit-testable logic;
  how the crew satisfies the per-BL "own tests" requirement here is itself a
  signal — see §4.)*
- **BL-0002 — Wishlist service.** `IWishlistManagement` + `WishlistManagement` +
  `WishlistDtos`, with xUnit+Moq tests. Carries requirement #1 (uniqueness).
- **BL-0003 — Controller + read API.** `WishlistController` CRUD + `GET .../user/{userId}`.
- **BL-0004 — move-to-cart.** The cross-aggregate op (requirement #2), touching the
  Cart service. (PO may fold this into BL-0003.)

## 4. THE key risk — acceptance app-boot on a non-Python target (TRACED 2026-06-09)

Traced against raw source before launch. Findings (file:line cited):

- **Per-BL gate: app-boot-free, low-risk.** A67 + xUnit/Moq, no DB, no app boot.
  If it fails, U1 fails early and cheaply — a clean datapoint.
- **`regression_checkpoint`: app-boot-free, language-agnostic — and it IS the U1
  proof.** `orchestrator.py:3273-3290` calls `regression_gate.run_gate`, which at
  `regression_gate.py:481` sets `use_compose = compose.yml ∧ compose.gate.yml
  exist`. This target has **neither** (verified: `ls` shows no compose/Docker/gate
  files) → `use_compose=False` → it runs `test_cmd` (`dotnet test`) natively in two
  disposable worktrees (baseline vs merged) and diffs pass/fail. No app boot, no
  Postgres, no compose.
- **CAVEAT — the checkpoint is coupled to the acceptance flag.** It is nested
  *inside* `if run_acceptance:` (`orchestrator.py:3256`→`3273`). **Disabling
  acceptance also disables the regression checkpoint** — so the named-benefit test
  requires `run_acceptance=True`.
- **Acceptance app-boot is AGENT-DRIVEN and compose-centric.** The orchestrator
  (`_acceptance_flow`, `orchestrator.py:2110+`) creates a worktree, loads the
  `acceptance` skill, and spawns a Claude Code agent; it does **not** boot the app
  itself and does **not** materialize the gitignored `appsettings.json`. The skill
  (`skills/brownfield/brownfield-acceptance-agent/SKILLS.md`) is built around
  `<target>/compose.gate.yml` + `docker compose up` + Playwright. **This target has
  no compose stack at all** → the acceptance skill's central boot assumption does
  not hold here.
- **Acceptance is ADVISORY / NON-ABORTING.** `orchestrator.py:3254` — exceptions
  are surfaced as `acceptance.error` and **never abort the sprint**. The sprint is
  already `sprint_complete` and the checkpoint has already run before the acceptance
  agent starts.

**Decision (architect, owned):** run **`run_acceptance=True`**.
- The app-boot-free `regression_checkpoint` runs → delivers the TIER-1 named
  benefit (the U1 proof), independent of any app boot.
- The compose-centric acceptance *agent* will find no compose stack and
  flail/error. Because acceptance is advisory it **cannot fail the sprint** — that
  flail is the **expected TIER-3 gap signal**, the precise data to scope the
  general follow-up: **generalize the acceptance skill to native app-boot** (a
  crew capability needed for ANY non-compose target — doctrine #1). Per the
  no-overclaim doctrine we observe the real failure before building the fix.
- Minor watch item: `dotnet test` in a fresh worktree triggers an implicit
  `restore` (NuGet) — should resolve from the local `~/.nuget` cache (the baseline
  greened via `dotnet test`, so packages resolve), but watch for a restore-network
  stumble in the first gate.

## 5. Preconditions (verify before launch)

1. **Harness on this session's code.** Restarted 2026-06-09 → **PID 67831**,
   `127.0.0.1:8000`, HEAD `9eeec9c`. Verified A67 + `/onboard` live. (Re-verify
   `lsof -nP -iTCP:8000`.)
2. **Pre-flight (`PREFLIGHT.md`)** green — Milvus `:19530`, Ollama `bge-m3`,
   indexer end-to-end. graphify already grounds C# (915 nodes, 747 symbol-level).
3. **Target on `integration` @ `9e98e86`** (≡ `main`, baseline 75/75 green). The
   feature forks from there; agent worktrees + auto-merge sink = `integration`.
4. **Postgres `ecommerce-pg` :5433 up** (only needed if/when acceptance boots the
   app; not needed for the per-BL gate). Boot with the target's `./dev-setup.sh`.
5. `.agentic-skills.json` confirmed: `test_cmd=["dotnet","test","backend/Ecommerce.sln","--nologo"]`,
   agent_branch=`integration`, doctrine=`brownfield`.

## 6. Measurement / success criteria (graded — partial proof is real proof)

Record: BLs merged/escalated (which BL), per-BL gate verdicts, regression
checkpoint verdict, acceptance verdict + findings, doctrine violations, janitor
spawns, suite delta (start 75 → end N). Then the manual probes:

- **Uniqueness (req #1):** `POST` the same product twice → one wishlist row. (§2a.1)
- **Move-to-cart (req #2):** move an item → present in cart AND absent from
  wishlist; no partial state. (§2a.2)
- **No regression:** the pre-existing 75 tests still green in the checkpoint.

**Grading (what each tier proves about U1, the language-agnostic loop):**

- **TIER 1 — loop proven.** ≥1 BL `merged_full` via the A67 C# gate **and** the
  regression checkpoint re-runs `dotnet test` green. → The harness drives a C#
  sprint. *Minimum bar to call U1 proven; promotes the C# loop `[~]`→`[x]`.*
- **TIER 2 — full per-BL loop.** All BLs `merged_full`, 0 escalations,
  `integration` consistent, requirements #1/#2 hold under live probes. → The crew
  delivers a clean small C# feature end-to-end.
- **TIER 3 — acceptance proven on C#.** Acceptance boots the C# app and runs API
  E2E with a real verdict. → Closes the untraced non-Python acceptance-boot gap;
  the *whole* C# loop is proven. (May not happen this run — see §4.)
- **Escalation = a clean capability/harness-wall datapoint** (no abort; dossier).
  An acceptance-boot wedge is the *expected* §4 finding, not a failure.

## 7. Risk / named-test / rollback (architect calibration triad)

- **Risk.** Primary: acceptance app-boot for a non-Python target is untraced
  (§4) — most likely wedge. Secondary: BL-0001 (entity/migration) is light on
  unit-testable logic, so the per-BL "own tests" gate may behave oddly there
  (false `no_tests` despite A67, or thin tests). Both are *informative* — they map
  the next crew-hardening targets, not show-stoppers.
- **Named test that proves benefit.** TIER 1: a traced run reaching
  `sprint_complete` with ≥1 C# BL `merged_full` through the A67 `dotnet test` gate
  + a green `regression_checkpoint` re-running `dotnet test`. That single artifact
  promotes the C# crew loop from `[~]` to `[x]` — the first cross-language proof.
- **Rollback.** The target is a **separate repo we never push.** All agent work
  lands on `integration`; discard with `git -C <target> reset --hard 9e98e86` (≡
  `main`). Harness state/traces archive per `run_id`. **Zero impact on
  agentic-skills.** Blast radius = one branch on one external toy repo.

## 8. How to launch (after operator approval + §4 pre-flight)

1. ~~Trace the acceptance boot path~~ **DONE (§4)** — decision: `run_acceptance=True`
   (the checkpoint is the U1 proof; the acceptance agent's compose-flail is the
   advisory TIER-3 gap signal).
2. Run pre-flight (`PREFLIGHT.md`) — Milvus/Ollama/indexer + target tree clean on
   `integration` @ `9e98e86` + index the C# target.
3. Crew-facing brief: `briefs/ecommerce_wishlist_brief.md` (the §2 requirements as
   a normal ticket — NOT the §1/§4 meta). Launcher:
   `scripts/launch_ecommerce_wishlist.py` (mirrors `launch_periodic_goals.py`)
   POSTs to `POST /api/projects/fullstack-ecommerce-app/run-brief` with
   `run_acceptance=True`, `run_doctrine_meta=True`, `run_acceptance_followup=False`
   (don't auto-dispatch on a target whose acceptance can't boot yet).
4. Launch detached, watch with `scripts/watch_run.sh`.
5. Record results in §9 (mirror the Exp-1b RESULTS section). Expect: per-BL merges +
   `regression_checkpoint` green = TIER 1/2; `acceptance.error`/compose-flail =
   the expected TIER-3 gap (NOT a crew defect) → feeds the native-boot follow-up.

## 9. RESULTS — `run-20260610T215031Z-05f865` (2026-06-10/11)

**Verdict: the C# crew loop is PROVEN end-to-end (TIER-1/2/3 all achieved).** First
sprint ever on a non-Python target ran clean: **4/4 BLs `merged_full`, 0 escalations,
0 janitor spawns, 0 Milvus deaths**, ~2h40m (21:50→00:31Z). `integration` @ `3e98fe1`
(13 commits ahead of baseline); `main` of agentic-skills untouched.

Scorecards (all Pass W/R): BL-0001 **93** · BL-0002 **94** · BL-0003 **92** ·
BL-0004 **95**. Each BL: engineer (C# + xUnit) → A67 `dotnet test` gate →
QA `PASS-W/R, 0 regressions` → scorer → auto-merge to `integration`.

| Tier | Result |
|---|---|
| **TIER-1** (loop proven) | ✅ all 4 BLs merged via the A67 `dotnet test` gate + `regression_checkpoint` **green** (exit-code-authoritative, A55 fallback — dotnet output isn't pytest-parseable). **Promotes the C# crew loop `[~]`→`[x]`.** |
| **TIER-2** (full per-BL + correctness) | ✅ all BLs merged; both correctness reqs verified by live acceptance journeys — uniqueness (api_02 duplicate-add → no dup) and move-to-cart atomicity (api_05 before/move/after, product in cart AND gone from wishlist). |
| **TIER-3** (acceptance on C#) | ✅ **EXCEEDED the prediction.** The acceptance agent **booted the C# app natively** — `dotnet run … --urls http://localhost:5097` against PostgreSQL 16 (`ecommerce-pg`) with the `AddWishlist` migration + seed — and ran **7/7 API journeys PASS**. It even detected that the stale baseline build held `:5096` (404s for `/Wishlists`) and booted *its* build on `:5097`, verifying the routes serve 200 so journeys hit *this sprint's* code. It also surfaced a **real pre-existing defect (FIND-01):** `POST /api/v1/Carts` → 500 (`ICartManagement` DI unregistered), correctly attributed to pre-existing cart code, not the wishlist feature. |

`doctrine_meta`: 0 proposals (clean run); efficacy `run_count=10, never_fired=[]` (no
false retirements — Stage-2 healthy). `closure_check`: **0 violations**.

**It took THREE launches — two infra failures, both architect-owned, both fixed:**
1. **run-…-21a088** (BL-0001 merged, then escalated): A68 — the harness Milvus
   auto-restart waited only 30s, far short of Milvus standalone's ~3.5-min segment
   reload → premature escalation. **Fixed (A68):** `docker restart` + poll-until-serving
   (300s) + cooldown spanning the reload window. +4 tests.
2. **run-…-27d128** (killed mid-BL-0002): Milvus standalone **self-terminated on etcd
   session-lease loss** under host contention (16 GB Mac, Docker over-allocated at
   12 GB → host swap → goroutine starvation → keepalive miss). **Fixed:** `ops/milvus/`
   hardened deploy — `common.session.ttl 30→180`, `retryTimes 30→60`,
   `etcd.requestTimeout 10000→30000` + `restart: unless-stopped`; Docker memory 12→8 GB.
3. **run-…-05f865** (this one): clean 4/4. Milvus `RestartCount: 0` across the whole
   sprint — the root-cause fix held, not just the recovery path.

**Honest caveats (no-overclaim):**
1. **`regression_checkpoint` was exit-code-green, not a parsed differential** — `run_gate`
   can't parse `dotnet test` per-test output, so it trusts exit 0 (documented A67/A55
   behavior). It proves the merged suite passes, not a name-level pre-vs-post diff.
2. **Acceptance native-boot was AGENT-IMPROVISED, not a codified harness path.** The
   acceptance *skill* is still compose-centric; the agent (a full Claude Code) figured
   out `dotnet run` + Postgres + a materialized gitignored `appsettings.json` on its
   own. So this proves native-boot acceptance is *achievable on C#* (the agent is
   capable) — NOT that a hardened harness native-boot path exists. Codifying it is the
   logical follow-up; the agent cleared the bar I expected it to trip on.
3. **n=2 sprint-proven real targets now** (beaverhabits Python + ecommerce C#) — the
   Stage-3 cross-target cumulative-learning substrate is finally in place.
4. FIND-01 (pre-existing cart DI bug) was flagged, not dispatched (`findings_persisted=0`)
   — correct: it's pre-existing, outside the feature scope.

**Net:** the crew delivers complex features on a non-Python (C#/.NET) brownfield target
end-to-end — PO grounding, engineering, A67 gating, QA, scoring, auto-merge, full
regression checkpoint, AND live API acceptance — with the architect resolving the two
infra blockers (A68 + Milvus stability) that the run surfaced. The language-agnostic
crew loop is real.

## 10. Relationship to the experiment program

- Exp 1 (Kanban) / 1b (dependencies): hard-correctness, **on Python** → PASSED.
- **This (Wishlist): the first NON-PYTHON loop shakedown** → proves U1, the
  language-agnostic crew loop.
- Next on C#: a hard-correctness *discovery* feature (the Exp-1b-class test, on
  C#) once U1 is green — e.g. Inventory reservation (race conditions) or Returns
  (multi-step state machine + refund + restock).
- Stage 3 (cross-target cumulative learning) needs **≥2 sprint-proven real
  targets**; this run makes ecommerce the 2nd (beaverhabits is the 1st).
