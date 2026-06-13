# Live-Acceptance Loop — the customer-acceptance standard (BINDING)

> Operator directive 2026-06-13. The acceptance phase must behave like the
> **paying customer who just received the app and sits down to use it** — boot
> the *whole real application*, exercise *100% of every acceptance criterion*
> through the running UI/API (including persistence re-checks), and **loop
> fix→re-test until every criterion is accepted against the live booted app**.
> No mocks, no build-only proxies, no self-reported "verified" without evidence,
> no routine give-up.

This supersedes the "acceptance improvises frontend boot / UI E2E is a follow-up
capability" posture (the honesty gap in [[arch_acceptance_honesty_gap]] /
`arch_zero_escape_chain` line 48). It is the real implementation of what R17/R20
only gated on paper.

---

## 1. What "accepted" means (the standard)

For EVERY acceptance criterion `AC-<BL>-<n>` in the feature's BACKLOG:

1. The **whole app is booted for real** — backend (real DB, real auth) + frontend
   (the actual served UI), wired together exactly as a user receives it.
2. A **real journey exercises that criterion against the running app**:
   - UI criterion → a **Playwright** journey navigates the real UI, clicks the
     real controls, fills the real forms.
   - API/auth criterion → a **real-HTTP** journey crosses the real auth boundary
     against the booted backend.
3. **Persistence is re-verified** where the criterion implies state change:
   save → reload/re-fetch → assert it persisted; edit → confirm it stuck;
   delete → confirm it's gone; reject-paths actually rejected in the live app.
4. The journey emits **re-openable evidence** tied to the AC id: a screenshot
   (UI) and/or a recorded request/response (API), plus the persistence re-check
   result.

A criterion is `verified` ONLY when (2)+(3)+(4) exist for it. Self-report without
the artifact = `unverified`.

## 2. The convergence loop (fix → re-test → re-accept)

```
boot whole app  →  exercise every AC live
        │
        ├─ all ACs verified, zero open failures ──────────────► integrity_ok = ACCEPTED
        │
        └─ any AC failed / unverified / defect found
                 │ classify (product_bug | test_bug | data_bug | infra_bug)
                 ▼
           dispatch follow-up engineer (no-abort: root-cause → fix → unit-verify)
                 │  merge fix (janitor re-merge on conflict — A66)
                 ▼
           RE-BOOT the app  →  RE-EXERCISE (≥ the failed ACs; full set on final pass)
                 │
                 └────────────────► loop  (until ACCEPTED or genuine escalation)
```

- Loop bound: `ACCEPTANCE_LOOP_MAX_ROUNDS` (generous backstop, not a routine
  give-up — no-abort doctrine). Exhaustion → terminal `escalated` + dossier
  ("a senior engineer would also be blocked"), never silent clean.
- Every dispatched fix must clear the full doctrine+gate+merge bar (zero-false-merge
  preserved: product_bug + confidence≥0.90 + idempotency R15).
- The sprint **cannot** read `sprint_complete`/clean while any AC is unverified or
  any classified failure is open.

## 3. Full-app boot contract (`app_boot` v2)

Extend `app_boot` in `.agentic-skills.json` from backend-only to a two-tier
contract. Schema (`repo_config._normalize_app_boot`):

```jsonc
"app_boot": {
  // BACKEND (existing fields; cmd/env/ready_url/ready_timeout_s/materialize/pre_cmd)
  "cmd": ["dotnet","run","--project","backend/Ecommerce.Presentation","--urls","http://localhost:5096"],
  "ready_url": "http://localhost:5096/api/v1/Products",
  "ready_timeout_s": 180,
  "materialize": [{"from":"backend/Ecommerce.Infrastructure/appsettings.example.json",
                   "to":"backend/Ecommerce.Infrastructure/appsettings.json"}],
  "pre_cmd": [["dotnet","ef","database","update","--project","backend/Ecommerce.Infrastructure","--startup-project","backend/Ecommerce.Presentation"]],
  // FRONTEND (new sub-block) — present ⇒ acceptance boots the UI and Playwright drives it
  "frontend": {
    "dir": "frontend",
    "pre_cmd": [["npm","ci"]],
    "cmd": ["npm","run","dev","--","--host","--port","${FE_PORT}"],
    "ready_url": "http://localhost:${FE_PORT}/",
    "ready_timeout_s": 180,
    "base_url_env": null   // null ⇒ frontend has a hardcoded API URL; backend MUST boot on the matching port
  }
}
```

ecommerce specifics: frontend hardcodes `http://localhost:5096/api/v1`
(`frontend/src/types/Auth.ts`) and the brief forbids editing `frontend/src`, so
the **backend boots on the fixed port 5096** (harness frees stragglers first);
the frontend gets a free port (`${FE_PORT}`). When `base_url_env` is a string
(other targets), the harness instead reserves a free backend port and materializes
that env var so the frontend points at it.

Harness-owned boot steps (`_acceptance_flow`): free/confirm ports → materialize
templates (committed `*.example.*` only, must resolve inside repo) → run pre_cmds
→ start backend, await ready_url → start frontend, await ready_url → hand the
**live frontend URL** to the acceptance agent → reap BOTH processes (+ any child)
on every exit path (I-1).

## 4. R20 becomes evidence-enforcing

`_unverified_criteria` no longer trusts the `ac_coverage` self-report. An entry
counts as `verified` only if it cites a journey artifact that exists on disk:
a Playwright spec that ran + a screenshot file (UI), or a recorded result file
(API), under the acceptance output dir, AND a persistence-recheck marker where
the AC implies state change. Missing/danging citation → `unverified` → non-clean.

## 5. Acceptance SKILL rewrite (`brownfield-acceptance-agent`)

- Drive the harness-provided full-app boot (backend+frontend URLs supplied).
- ONE journey per AC, mapped by `AC-<BL>-<n>`, exercising it against the live app
  with the persistence re-check + evidence.
- One honest pass per round; classify each failure; emit `ac_coverage[]` with the
  evidence path per AC + the `report.json` failure findings.
- Read-only against source; never merges.

## 6. Build order (this is the work)

A. `repo_config`: `app_boot` v2 schema (`frontend` sub-block) + tests.
B. ecommerce `.agentic-skills.json`: the full-app `app_boot` contract (on `main`).
C. `_acceptance_flow`: boot backend+frontend, port/materialize, ready-waits, reap.
D. Acceptance SKILL: per-AC live journeys + persistence + evidence.
E. R20 evidence-enforcement in `_unverified_criteria`.
F. Convergence loop: acceptance→dispatch→re-boot→re-accept until integrity_ok.
G. doctrine_spec + CLAUDE.md R-rule updates (R17/R20 amended; consistency test).
H. Deploy to remote; prove on a throwaway run BEFORE relaunching the reviews proof.

Evidence of done (shown to operator, not claimed): booted backend+frontend URLs,
the per-AC Playwright journeys that ran, screenshots, persistence re-checks, the
fix→re-test loop rounds, and the run refusing to go clean until every AC passed
live.
