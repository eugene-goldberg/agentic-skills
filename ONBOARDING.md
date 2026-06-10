# Onboarding a brand-new brownfield target

> **How to invoke the onboarding process** — run this once when you point the
> crew at a repo it has never worked on, *before* any `/run-brief`.

## What onboarding is (and is not)

**Onboarding = fulfilling the environment prerequisites a `git clone` does not
bring**, so the crew *can* begin brownfield feature work. The Onboarder is the
**Janitor/Ops-Steward in onboarding mode** (skill:
`skills/brownfield/brownfield-production-incremental-onboarder/SKILLS.md`). It
autonomously:

- detects the stack (language, framework, test runner, database, frontend);
- **installs/restores dependencies** and the right runtime/toolchain;
- **provisions services** the app needs (e.g. a PostgreSQL **Docker container**);
- **materialises gitignored config/secrets** from a committed example template;
- **generates required-but-absent artifacts** (an initial DB migration/schema);
- derives the gate config (`test_cmd` / `test_env` / `test_file_globs`);
- adds harness `.gitignore` hygiene (so runtime artifacts never dirty the tree);
- writes `.agentic-skills.json` and forks the `integration` branch;
- verifies the target **builds**, **boots** (if it has a runtime), and that
  `test_cmd` **executes**.

**Onboarding is NOT** fixing pre-existing defects in the target's committed
source. A test that fails because of a real bug in the cloned code is **flagged**
in the verdict (`gate_readiness.baseline_red_source_defects`), **not** rectified —
that's the target's own code, not an environment prerequisite.

## Prerequisites

1. **The harness server is running** (uvicorn on `127.0.0.1:8000`):
   ```bash
   cd webapp/backend && .venv/bin/python -m uvicorn app.main:app \
       --host 127.0.0.1 --port 8000
   ```
2. **The target is symlinked** under `webapp/backend/repos/<repo>` (the same
   place `/run-brief` discovers targets):
   ```bash
   ln -s /abs/path/to/<repo> webapp/backend/repos/<repo>
   ```
3. The repo is **not already onboarded** (it has no `.agentic-skills.json` —
   onboarding is the step that creates it).
4. Docker is available if the target needs a database/service (the onboarder
   stands up its own container).

## Invoke it — two ways

### A) Launcher script (recommended)

```bash
# minimal:
python scripts/onboard_target.py <repo>

# with the upcoming feature brief as CONTEXT (helps the onboarder anticipate
# which services/deps the work needs — it still only prepares the environment):
python scripts/onboard_target.py <repo> --brief-file path/to/brief.txt

# longer per-agent budget (default 3600s) for heavy installs / DB boots:
python scripts/onboard_target.py <repo> --timeout 7200

# detached for a long onboarding:
nohup python scripts/onboard_target.py <repo> \
    > webapp/backend/logs/harness/onboard_<repo>.log 2>&1 &
```

### B) HTTP endpoint (for the UI / scripting / future auto-trigger)

```bash
curl -N -X POST http://127.0.0.1:8000/api/projects/<repo>/onboard \
  -H 'Content-Type: application/json' \
  -d '{"timeout": 3600}'          # optional: {"brief": "...", "timeout": 7200}
```
`POST /api/projects/{repo}/onboard` streams Server-Sent Events; the body is
`OnboardRequest { brief?: string, timeout?: int (300..14400, default 3600) }`.

## Reading the result

The stream ends in one of two terminal events:

- **`onboarding.done` (`status=onboarded`)** — the repo is ready. This fires only
  when **both** the Onboarder reported `onboarded` **and** the orchestrator's own
  independent postcondition check passed (the no-overclaim trust gate):
  `.agentic-skills.json` valid with a `test_cmd`, the `integration` branch exists,
  and the harness `.gitignore` rules are present. You can now `/run-brief`.
- **`onboarding.escalated`** — a prerequisite couldn't be satisfied. The event's
  `missing` list and the report say why.

Artifacts the onboarder writes into the target:
```
<repo>/_brownfield/_onboarding/ONBOARDING_REPORT-<run_id>.md    # human-readable
<repo>/_brownfield/_onboarding/ONBOARDING-<run_id>.json         # machine verdict
```
The JSON verdict carries the detected `stack`, what it `provisioned`, the derived
`config`, the `gate_readiness` result (including any `baseline_red_source_defects`
it flagged but did not fix), the `runtime` boot proof, and the `postconditions`
checklist.

## After onboarding

1. Skim the `ONBOARDING_REPORT` — confirm the derived `test_cmd`, the services it
   stood up, and any flagged `baseline_red_source_defects` (decide separately
   whether to address those; the crew/acceptance will encounter them otherwise).
2. Commit the onboarding artifacts the onboarder created on the target's `main`
   and `integration` branches (config, `.gitignore`, migrations, `dev-setup.sh`,
   example template) if it left them staged — keep real secrets gitignored.
3. Launch the feature work: `POST /api/projects/<repo>/run-brief`.

## Scope / current status (honest)

- **Operator-invoked only.** There is no `auto_onboard` trigger inside
  `run_brief` yet — you run onboarding deliberately as the step above. (An
  `auto_onboard` flag is a planned follow-up.)
- **Independent verification is structural.** The orchestrator verifies the
  config/branch/gitignore prerequisites itself. Proving `test_cmd` actually runs
  green is left to the first gate invocation; the onboarder reports the baseline
  result in its verdict.
- The skill encodes the hard-won gotchas (devDeps omitted under
  `NODE_ENV=production`, secrets-as-template, migrations wrongly gitignored,
  http-only boot to avoid HTTPS 307s, root-relative `test_cmd`, unit-vs-
  integration test scoping).
