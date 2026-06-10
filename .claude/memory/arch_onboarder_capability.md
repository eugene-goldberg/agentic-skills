---
name: arch_onboarder_capability
description: "2026-06-09 — the Onboarder crew capability: the Janitor/Ops-Steward in ONBOARDING MODE provisions a new repo's ENVIRONMENT prerequisites before brownfield work. Skill + /onboard endpoint + launcher; wired+unit-tested, NOT live-proven"
metadata: 
  node_type: memory
  type: project
  originSessionId: e0df5d9d-765b-436e-a657-5217d5cb77bd
---

**New crew capability — the Onboarder (the Janitor/Ops-Steward in ONBOARDING MODE).**
Turns the manual onboarding of the 2nd target ([[arch_target_ecommerce]]) into a
reusable crew member. When the crew is pointed at a brand-new repo, the onboarder
fulfils the **environment prerequisites a `git clone` doesn't bring** so the crew
can begin: install/restore deps + runtime, provision services (DB container),
materialise gitignored config from a template, generate missing migrations/schema,
derive the gate config, add `.gitignore` hygiene, fork `integration`, verify it
builds/boots and `test_cmd` EXECUTES.

**BINDING SCOPE (operator correction 2026-06-09):** onboarding = ENVIRONMENT
PROVISIONING ONLY. The onboarder **NEVER edits the target's committed source/tests
to fix a pre-existing defect** — a red baseline from a SOURCE defect is FLAGGED in
the verdict (`baseline_red_source_defects`), not rectified. (My first draft of the
skill wrongly included "edit code to green the baseline"; rewrote to v2.0.) This
re-aligns the onboarder with the reactive Janitor's "never change what the software
does" boundary. The baseline-greening I did for the ecommerce target was a separate
one-off remediation the operator approved — NOT onboarding doctrine.

**What shipped (dev≡main, commits 76312b3 → e256c7c → ada209a):**
- Skill `skills/brownfield/brownfield-production-incremental-onboarder/SKILLS.md`
  (registered as role `onboarder` in `prompts_brownfield.SKILL_PATHS`). 9-step
  protocol + the hard-won gotchas (devDeps under NODE_ENV=production, secrets-as-
  template, migrations wrongly gitignored, http-only boot vs HTTPS 307, root-
  relative test_cmd, unit-vs-integration scoping) + the JSON verdict contract.
- `orchestrator._onboarding_flow` / `run_onboarding`: spawns the onboarder on the
  REAL checkout, reads the verdict sidecar (`_brownfield/_onboarding/ONBOARDING-<run_id>.json`),
  then INDEPENDENTLY verifies postconditions (`_verify_onboarding_postconditions`:
  config valid + integration branch + gitignore hygiene). `status=onboarded` only
  when BOTH the agent verdict AND the orchestrator check pass (no-overclaim gate).
- `POST /api/projects/{repo}/onboard` (SSE) + `scripts/onboard_target.py` launcher.
- `ONBOARDING.md` = how to invoke. `tests/test_onboarding_flow.py` (+7).

**HOW TO INVOKE:** harness server up + repo symlinked under
`webapp/backend/repos/<repo>` + repo not yet onboarded → `python
scripts/onboard_target.py <repo>` (or `POST .../onboard`). Ends `onboarding.done`
(status=onboarded → `/run-brief`-ready) or `onboarding.escalated` (with `missing`).

**HONEST STATUS:** **wired + unit-tested, NOT live-proven** (`[~]`). No real repo
has been run through `/onboard` end-to-end. Operator-invoked only — NO
`auto_onboard` trigger in run_brief yet. The independent verification is structural
(config/branch/gitignore); proving `test_cmd` runs green is left to the first gate.
See [[feedback_no_scope_overclaim]], [[feedback_improve_crew_not_accommodate]].
Next: restart the STALE harness (PID 14484 predates this) on `ada209a`, then live-
prove `/onboard` on an un-onboarded repo.
