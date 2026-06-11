# Next-enhancement assessment — what moves the mission most

> Architect assessment, 2026-06-11 (written while the ecommerce-reviews sprint
> grinds). Grounded in THESIS.md, EVALUATION_2026-05-28.md, the Horizon capability-
> wall write-up, DESIGN_SHORTCOMINGS.md, and this session's live evidence. Stale
> claims in the source material reconciled against current state (see footnote).

---

## 1. The diagnosis (one paragraph)

The crew is a **proven autonomous worker loop with a hardcoded conductor — not yet
an autonomous team with judgment.** The worker loop (engineer → QA → merge, grounded
+ gated + honest) is genuinely solid: 23+ BLs delivered across 4 sprints, two
languages (Python + C#), additive *and* behavior-refactoring features, 0 mid-sprint
operator rescues on the last several. The gap is **engineering judgment at the hard
moments**: when a decomposition is risky, or when a BL's code can't pass its own gate,
the crew either plans blindly or stalls for a human. Every documented capability wall
(canonically the **Horizon run**) lives in that judgment gap, not the worker loop.

## 2. What is PROVEN (do not re-prove)

- Grounded worker loop (R5/Tier-1.5), honest failure reporting, doctrine enforcement.
- **Cross-language**: C# sprint end-to-end (wishlist 4/4).
- **Behavior-refactoring** features (not just additive): Kanban (reordering refactor +
  migration on populated DB), Dependencies (status-path refactor + invariant).
- **Self-resolution arc (A57–A61)**: env/merge failures → Janitor repair → remerge;
  acceptance findings → followup dispatch. This is triage for *environment* and
  *acceptance* — already built.
- **Native-boot acceptance (backend)**: live-proven API journeys on non-compose C#.
- Per-target cumulative learning (Stage 1/1.5/4). *(Cross-target Stage 3 = DORMANT by
  operator directive — excluded from candidates.)*

## 3. The honest gaps, reconciled (what's actually unbuilt)

| Gap | What's missing | Evidence |
|---|---|---|
| **Code-failure triage (judgment)** | When a BL exhausts gate/doctrine retries, it goes `awaiting_review` and **waits for a human**. The Janitor handles *env* failures, NOT *code* failures. No agent decides rewrite-deeper / split / defer / escalate on a code wall. | Horizon: engineer chased symptom specs on an auth regression, exhausted retries, stalled. EVALUATION: "biggest autonomy gap." |
| **Plan-review / dependency-hazard check** | The PO decomposes once; **no critic** reviews the backlog for foundation-BL risk or hidden cross-BL coupling before execution. A bad decomposition is first felt as an engineer failure mid-sprint. | No plan-critic in the flow. Horizon's wall was partly a too-risky foundation BL. |
| **Full-feature UI verification** | Acceptance `app_boot` boots **backend only**; UI E2E (Playwright) currently relies on the *agent improvising* a frontend boot. Not a hardened harness path. | Reviews sprint (live now) surfaced it; wishlist agent improvised it. |
| **Fresh-repo "walk away" (onboarding)** | Onboarder is `[~]` — wired + unit-tested, **never live-proven**, no `auto_onboard` trigger. Every target so far was hand-onboarded. The "never-seen repo" thesis bar has **zero** evidence. | arch_onboarder_capability; EVALUATION §7. |
| **Honesty: outcome truthfulness** | A2/A5: a BL can report `outcome=merged` when QA never landed. A real (small) honesty hole. | DESIGN_SHORTCOMINGS A2/A5. |
| **Non-Python gate fidelity** | `regression_checkpoint` on C# is exit-code-green only — can't name what regressed. Weaker collateral-regression detection off the pytest path. | A67 note; handoff. |
| **Throughput** | BLs run strictly sequentially; an 8-BL sprint = hours. Parallel waves could ~halve it. | B11 (deferred, high-risk, blocked). |

## 4. The candidates, ranked (impact × tractability × mission-alignment)

> Mission lens (THESIS): the goal is **complex features, walk-away autonomy** — not
> speed. "Operator-time is a symptom, not the goal." So capability/judgment > throughput.

### Tier 1 — highest mission impact: **Crew engineering judgment on failure**
The crew's #1 "walk-away" blocker. Two complementary halves:

- **(1a) Root-cause-first engineer + code-failure triage.** When a BL can't pass its
  gate after retries, (i) the engineer's fix loop is directed to *root-cause before it
  patches* (the Horizon doc's own prescription — stop chasing symptom specs), and (ii)
  at genuine exhaustion a **triage decision** fires — rewrite-deeper / **split** the BL /
  **defer** it (continue the sprint, report it) / **escalate** (real wall → dossier).
  This converts the one place a human is still needed mid-sprint into a crew judgment.
  - *Impact:* **Very high** — directly closes the most-cited autonomy gap and the only
    observed capability wall. It's the literal difference between "stalls" and "decides."
  - *Tractability:* **Medium-high** — reuses proven patterns (spawn agent at a seam,
    read trace, structured verdict — exactly how Janitor/acceptance/doctrine-meta work).
    The seam (`awaiting_review`) already exists. Start cheap: the root-cause directive
    (prompt-level), then the triage decision.
  - *Risk:* medium — judgment quality is the variable; provable by re-running a
    Horizon-class feature and watching the crew self-recover where it previously walled.

- **(1b) Plan-review / dependency-hazard critic** (companion, can follow 1a). A critic
  reviews the PO's backlog *before* execution: flags foundation BLs that change shared
  code everything depends on, recommends "add a characterization test first / split /
  resequence." Upstream *prevention* to pair with 1a's downstream *recovery*.
  - *Impact:* **High** — prevents a class of walls at the source.
  - *Tractability:* **Medium** — another review agent + a replan directive (mirrors the
    existing plan-checker pattern).

### Tier 2 — prove an untested mission pillar: **Onboarder live-proof → `auto_onboard`**
The literal "point at a fresh repo and walk away" entry, with **zero** evidence today.
- *Impact:* **High** — the "never-seen repo + large feature" bar (THESIS §7) is the
  mission's headline and has never been tested. Live-proving onboarding + adding the
  auto-trigger is the first real evidence.
- *Tractability:* **Medium** — onboarder is wired; live-proof = run a genuinely fresh
  repo through `/onboard` end-to-end (the first live run will surface real gaps — that's
  the point), then add the flag.
- *Risk:* medium — first-live-proofs always find things.

### Tier 3 — complete the feature-delivery promise: **Frontend-boot for acceptance**
Extend `app_boot` to a backend+frontend contract so UI E2E (Playwright) is a hardened
harness path, not agent improvisation. Directly completes "deliver an API **+ UI**
feature, verified" — exactly the shape of the sprint running now.
- *Impact:* **Medium-high** — robustness/completeness of UI delivery (the crew already
  *can* improvise it; this makes it reliable).
- *Tractability:* **Medium** — two-process boot + port wiring + frontend ready-check.

### Tier 4 — honesty + fidelity hygiene (cheap, worth doing, not the headline)
- **A2/A5 outcome truthfulness** (~20 LOC): a BL must not report `merged` when QA never
  landed. Small but it's a genuine *honest* -property hole.
- **Non-Python regression differential**: parse `dotnet test`/`go test`/junit so the C#
  regression checkpoint can name regressions, not just exit-code.

### Explicitly NOT recommended now
- **Parallel BL execution (B11):** throughput, not capability; high-risk; mission-low.
- **Cross-target / community learning:** dormant by operator directive.
- **Escalation Bridge (Slack/Linear):** convenience; dossiers already work.
- **Full brief auto-generation:** the human *should* supply product intent (THESIS).

## 5. Recommendation

**Build Tier 1 — crew engineering judgment on failure — starting with (1a).** It is the
highest-leverage move toward the mission's core unproven promise ("complex features,
walk away"): it closes the single most-cited autonomy gap, it directly targets the only
observed capability wall, and it's the one place a human is still required *mid-sprint*.
Sequence it cheaply: (i) the root-cause-first engineer directive, (ii) the code-failure
**triage decision** at gate-exhaustion (rewrite/split/defer/escalate), then (iii) the
**plan-review critic** (1b) as the upstream companion. Prove it by re-running a
Horizon-class hard feature and showing the crew self-recovers where it previously walled.

**Strong alternatives if you'd prefer a more concrete / lower-risk first step:** Tier 2
(onboarder live-proof — proves the untested "fresh repo" pillar) or Tier 3 (frontend-boot
— completes UI-feature verification, immediately relevant to the running sprint).

---

*Footnote — reconciliations against stale source material:* Stage 3 is DORMANT by
operator directive (not "pending flip"); A7 orchestrator-state persistence IS
implemented; native-boot acceptance IS shipped+live-proven for the backend (frontend is
the open part); the self-resolution arc already covers env/merge/acceptance triage, so
the triage gap is specifically *code-gate-exhaustion*, not triage wholesale.
