# Proposal — Codify native-boot acceptance for non-compose targets

> Authored 2026-06-11 (architect). Status: **PROPOSED — awaiting operator approval.**
> Grounded in `run-20260610T215031Z-05f865` (first C# sprint) — see
> `EXPERIMENT_ecommerce_wishlist.md` §9. Calibrated per `CLAUDE.md` architect
> responsibility #6 (explicit risk · named proof · named rollback).

## 1. What the crew gains

A **reliable** whole-feature integration checkpoint on *any* stack — not one that
works by luck. Acceptance is THE single integration checkpoint (post-A55): the one
place whole-feature E2E and collateral regressions are caught. Today it only boots
reliably on **docker-compose** targets. This makes it work, by configuration, on
native/non-compose targets too (C#/.NET, Go, plain-Python, anything) — so the next
non-Python sprint's acceptance is trustworthy, not improvised.

## 2. Problem (grounded, re-openable)

- The acceptance flow is **compose-centric.** `_build_acceptance_task`
  (`webapp/backend/app/services/orchestrator.py:1624`) threads a `compose_project`
  and the prompt instructs the agent to "boot any docker compose stack"
  (`orchestrator.py:1728-1729`); the skill
  (`skills/brownfield/brownfield-acceptance-agent/SKILLS.md`) lists `compose.gate.yml`
  + `scripts/regression_gate.sh` as inputs and `docker compose up` as the boot step.
- The orchestrator **does not materialize gitignored config** into the acceptance
  worktree (worktrees carry only tracked files).
- **fullstack-ecommerce-app has no compose stack at all** (native `dotnet run` +
  standalone Postgres + gitignored `appsettings.json`). In the C# sprint the
  acceptance agent **improvised** the boot — `dotnet run … --urls :5097` against
  `ecommerce-pg`, self-materializing `appsettings.json`, even dodging the stale
  baseline build on `:5096` — and passed **7/7 API journeys**. That proves native
  acceptance is *achievable*, **not** that it's *repeatable*: it depended on the
  agent guessing the boot command, the DB wiring, and the config file. A different
  feature, model run, or target could fail to.

## 3. Design — config-driven `app_boot`, agent-driven execution

Keep the harness language-agnostic: the per-target boot recipe lives in the
target's own `.agentic-skills.json` (same philosophy as `test_cmd`/`test_env`/
`test_file_globs`). The agent (a full Claude Code) still *drives* the boot, but
against an **explicit contract** instead of a compose assumption.

**(a) Config — extend `RepoConfig`** (`webapp/backend/app/services/repo_config.py:68`,
mirroring the A67 `test_file_globs` optional-field + `getattr` pattern). New optional
`app_boot` block:

```json
"app_boot": {
  "cmd": ["dotnet","run","--project","backend/Ecommerce.Infrastructure","--urls","http://localhost:${PORT}"],
  "env": {"ASPNETCORE_ENVIRONMENT": "Development"},
  "ready_url": "http://localhost:${PORT}/api/v1/products",
  "ready_timeout_s": 150,
  "materialize": [
    {"from": "backend/Ecommerce.Infrastructure/appsettings.example.json",
     "to":   "backend/Ecommerce.Infrastructure/appsettings.json"}
  ],
  "pre_cmd": [["dotnet","ef","database","update","--project","backend/Ecommerce.Infrastructure"]]
}
```
`${PORT}` is allocated free by the orchestrator and injected (kills the `:5096`-vs-
`:5097` stale-port class). Absent `app_boot` + present compose files → existing
compose path, unchanged.

**(b) Orchestrator** (`_acceptance_flow` + `_build_acceptance_task`): when `app_boot`
is set — (1) **materialize** the listed config files into the acceptance worktree
before spawn; (2) run any `pre_cmd` (migrations) against the shared dev services;
(3) pass `cmd`/`env`/`ready_url`/`ready_timeout_s` into the task prompt in place of
`compose_project`. The agent boots, polls `ready_url`, verifies the *feature route*
serves (not the stale baseline), runs journeys.

**(c) Skill** (`brownfield-acceptance-agent/SKILLS.md`): generalize Inputs +
Required-Completion-Step-6 from "bring up the compose gate stack" to "bring up the
app via the provided **boot contract** — compose stack OR native `app_boot` — poll
`ready_url`, then run **API journeys always, Playwright iff UI**." API-evidence
discipline (verbatim request/response `*.jsonl`) unchanged.

**(d) Honest fallback:** neither compose nor `app_boot` → best-effort native boot
(as the C# run did) with the report flagging `boot_method: inferred`. Never silently
skip the checkpoint.

## 4. Calibration triad

**RISK**
1. *Secret leakage* — `materialize` could copy a real secrets file into a worktree.
   *Mitigate:* convention restricts `from` to committed `*.example.*` templates;
   never log file contents; the worktree is reaped post-run.
2. *A wrong `app_boot.cmd` wedges acceptance.* *Mitigate:* acceptance is
   **advisory / non-aborting** (`orchestrator.py:3254` — exceptions → `acceptance.error`,
   never abort), bounded by `acceptance_timeout` + the R10.1 3-attempt loop. A boot
   failure can't fail the sprint; the per-BL gate is independent.
3. *Port collision with a stale build* (the `:5096`/`:5097` issue). *Mitigate:*
   orchestrator allocates a free `${PORT}`; the agent confirms the feature route
   serves before journeys.

**NAMED TEST that proves benefit**
- *Behavioral (live):* re-run the ecommerce wishlist acceptance with `app_boot`
  configured **and the compose-centric skill wording removed** → acceptance boots
  via the contract (not improvisation), polls `ready_url`, and passes the **same 7
  API journeys**. Before-state: with the wording removed and no `app_boot`, the agent
  is expected to flounder (proving the config is what carries it).
- *Unit (deterministic):* `_build_acceptance_task` emits the **native** boot prompt
  + materialize step when `app_boot` is set, and the **compose** prompt when it's
  absent + compose files present (regression guard for existing compose targets).

**NAMED ROLLBACK**
- `app_boot` is **opt-in per target**; the skill change is **additive** (compose path
  preserved verbatim). Rollback = delete the `app_boot` block from the target's
  `.agentic-skills.json` (reverts to compose / agent-improvised) and/or `git revert`
  the orchestrator+skill commit. Because acceptance is advisory, even a fully broken
  native-boot path cannot regress a sprint's merge outcome.

## 5. Scope / non-goals
- **In:** acceptance app-boot for non-compose targets; config materialization; free-
  port injection; skill generalization; the ecommerce `app_boot` block as the
  reference.
- **Out:** the per-BL gate (untouched — Moq/`dotnet test`, no boot); Playwright/UI
  acceptance semantics (still iff UI journeys); building a wishlist UI; gate-fidelity
  for non-Python test parsing (separate honorable-mention item).

## 6. Effort / files
Medium. `repo_config.py` (+`app_boot` field, ~A67-sized), `orchestrator.py`
(`_build_acceptance_task` + `_acceptance_flow`: materialize + free-port + prompt),
`brownfield-acceptance-agent/SKILLS.md` (generalize), tests
(`tests/test_acceptance_app_boot.py`), and the ecommerce `.agentic-skills.json`
`app_boot` block. The C# run + `dev-setup.sh` are a working reference to codify from.

## 7. Operator decisions — LOCKED 2026-06-11

1. **Materialize security policy → A (restrict to committed `*.example.*` templates).**
   `app_boot.materialize[].from` MUST resolve to a committed `*.example.*` template;
   the harness rejects/ignores any other source. Acceptance never needs production
   secrets — only local dev values, filled by the harness. Cannot touch a real
   secrets file by construction.
2. **Boot ownership → agent-driven, against an explicit contract.** The acceptance
   agent (a full Claude Code) runs the boot using the `app_boot` recipe
   (`cmd`/`env`/`ready_url`/`${PORT}`); it does NOT guess (the contract removes the
   improvisation), but it OWNS execution so it can adapt to surprises (stale-build
   port squat, missing migration, redirects) — as it did live this run. The
   orchestrator does NOT boot the subprocess directly.
3. **Validation depth → Level 3 (feature-route check).** Before declaring ready,
   acceptance MUST (a) poll `ready_url` until 200, AND (b) hit at least one route of
   the NEW feature and confirm it is served (not 404) — guaranteeing journeys
   exercise THIS sprint's build, not a stale baseline. Kills the false-pass-on-wrong-
   binary class (the `:5096`/`:5097` trap). Cheap: one extra HTTP call.

These three are binding for implementation. Rationale + alternatives considered are
in the git history of this file and the 2026-06-11 architect session.
