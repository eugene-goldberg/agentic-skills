# Agentic Skills Progress Tracker

## Current Status

Project initialized and scaffolded. First Product Owner cycle `PO-001` is complete and scored. Engineering candidate `ENG-001` has completed and passed backlog items `BL-0001`, `BL-0002`, `BL-0003`, `BL-0005`, `BL-0006`, and `BL-0007`.

QA evaluation protocol authored (`docs/qa_evaluation_protocol.md`), journey catalogue authored (`docs/qa_journey_catalogue.md`), QA work-packet template authored (`templates/qa_work_packet_template.md`). QA is a per-BL gate that fires after each engineering BL closes. `QA-001` (`addyosmani/agent-skills`) catches up the six closed engineering BL increments before becoming a forward gate.

Primary goal: systematically evaluate `SKILLS.md` role variants across target repositories to identify the most reliable Product Owner, Engineer, and QA skills for production-grade output.

## Milestones

| Milestone | Status | Notes |
|---|---|---|
| Create project directory | Done | `/Users/eugenegoldberg/dev/ai-projects/agentic-skills` |
| Create project scaffold directories | Done | `briefs/`, `reports/`, `rubrics/`, `runs/`, `skills/`, `target-repos/`, `templates/` |
| Document evaluation plan | Done | See `docs/skill_evaluation_plan.md` |
| Document full-cycle protocol | Done | See `docs/full_cycle_execution_protocol.md` |
| Create progress tracker | Done | This file |
| Define scoring rubric | Done | See `rubrics/production_grade_scorecard.md` |
| Define run metadata schema | Done | See `templates/run_metadata_template.yaml` |
| Define scorecard template | Done | See `templates/scorecard_template.md` |
| Adopt one-candidate full-cycle protocol | Done | Evaluate one candidate source + one role + one skill at a time |
| Select initial target repos | In Progress | First target selected: `project-tracker-v1-po-baseline` |
| Select initial briefs | In Progress | First brief selected: `project_tracker_v1_po_planning` |
| Build candidate-source queue | Done | Initial queue based on `docs/agentic-skills-repos.md` |
| Collect first PO skill variant | Done | `agile-v-product-owner/SKILL.md` snapshotted from `Agile-V/agile_v_skills` |
| Collect first Engineer skill variant | Done | `incremental-implementation/SKILL.md` snapshotted from `addyosmani/agent-skills` |
| Collect first QA skill variant | In Progress | `QA-001` catch-up cycle: BL-0001 through BL-0007 (six engineering closures) in order |
| Author QA evaluation protocol | Done | `docs/qa_evaluation_protocol.md` |
| Author QA journey catalogue | Done | `docs/qa_journey_catalogue.md` |
| Author QA work-packet template | Done | `templates/qa_work_packet_template.md` |
| Run first controlled experiment | Done | `PO-001` completed with decision `Pass` and score `66/75` |
| Produce first comparison report | Pending | Store under `reports/` |

## Run Log

| Run ID | Date | Repo | Role | Skill Variant | Brief | Result | Score | Failure Modes | Notes |
|---|---|---|---|---|---|---|---:|---|---|
| `po-001-agile-v-product-owner` | 2026-05-14 | `project-tracker-v1-po-baseline` | PO | `agile-v-product-owner` | `project_tracker_v1_po_planning` | Pass | 66/75 | None | Objective verifier passed; see `runs/po-001-agile-v-product-owner/scorecard.md` |
| `eng-001-incremental-implementation-bl-0001` | 2026-05-14 | `project-tracker-v1-engineering-baseline` | Engineer | `incremental-implementation` | `bl-0001-authenticated-account-foundation` | Pass | 64/75 | None | Auth feature live-smoke verified; latest commit `b30c568`; see `runs/eng-001-incremental-implementation/scorecard.md` |
| `eng-001-incremental-implementation-bl-0002` | 2026-05-14 | `project-tracker-v1-engineering-baseline` | Engineer | `incremental-implementation` | `bl-0002-workspace-privacy-boundary` | Pass | 66/75 | None | Workspace privacy feature live-smoke verified; latest commit `c5e89e3`; see `runs/eng-001-incremental-implementation-bl-0002/scorecard.md` |
| `eng-001-incremental-implementation-bl-0003` | 2026-05-14 | `project-tracker-v1-engineering-baseline` | Engineer | `incremental-implementation` | `bl-0003-workspace-member-management-and-role-matrix` | Pass | 72/75 | None | Member management + role matrix live-smoke verified; latest commit `a898011` (docstring fix on top of `a10ed95`); zero human rescue; see `runs/eng-001-incremental-implementation-bl-0003/scorecard.md` |
| `eng-001-incremental-implementation-bl-0005` | 2026-05-14 | `project-tracker-v1-engineering-baseline` | Engineer | `incremental-implementation` | `bl-0005-project-crud-within-a-workspace` | Pass | 72/75 | None | Project CRUD + full role x HTTP matrix live-smoke verified (31 checks); latest commit `f600039`; zero human rescue; defensive cascade hook in place for BL-0006/0007; see `runs/eng-001-incremental-implementation-bl-0005/scorecard.md` |
| `eng-001-incremental-implementation-bl-0006` | 2026-05-14 | `project-tracker-v1-engineering-baseline` | Engineer | `incremental-implementation` | `bl-0006-task-crud-status-and-assignment-rules` | Pass | 74/75 | None | Task CRUD + status enum + assignee-is-member + `app.py` split + behavior-based verifier rewrite + activation of BL-0003 AC 6/7/8 and BL-0005 AC 7 (task portion); 73 pytest, 45 smoke checks; latest commit `7f6d104`; zero human rescue; see `runs/eng-001-incremental-implementation-bl-0006/scorecard.md` |
| `eng-001-incremental-implementation-bl-0007` | 2026-05-14 | `project-tracker-v1-engineering-baseline` | Engineer | `incremental-implementation` | `bl-0007-task-comments-for-all-workspace-members` | Pass | 74/75 | None | Task comments + viewer-mutation exception via helper omission + typed ORM cascade replacing BL-0005 defensive scaffolding + finalized BL-0005 AC 7 (comments + tasks); 88 pytest; latest commit `87939ad`; zero human rescue; see `runs/eng-001-incremental-implementation-bl-0007/scorecard.md` |
| `qa-001-test-engineer-bl-0001` | 2026-05-14 | `project-tracker-v1-engineering-baseline` @ `5baf798` | QA | `test-engineer` | `qa-001-test-engineer-bl-0001` | Pass | 74/75 (+ protocol axes 29/30) | None | First QA cycle. Engineer stack 4/4 pass. Journey suite 11/11 pass (7 required + 4 added) via subprocess Uvicorn + real HTTP. Zero application defects; 8 verification-stack gap findings (5 medium / 3 low). Highest finding: `verify_bl0001.py` is a behavior-blind token-grep. See `runs/qa-001-test-engineer-bl-0001/scorecard.md`. |
| `qa-001-test-engineer-bl-0002` | 2026-05-14 | `project-tracker-v1-engineering-baseline` @ `c5e89e3` | QA | `test-engineer` | `qa-001-test-engineer-bl-0002` | Pass | 74/75 (+ protocol axes 40/40) | None | Second QA cycle. Engineer stack 5/5 pass. 20-scenario suite (11 BL-0001 carry-forward + 9 BL-0002 added); all 11 carry-forward still pass against `c5e89e3` (continuity preserved). **First real engineering defect surfaced by QA-001**: `BUG-QA001-BL2-001` High — uncaught `OverflowError` → 500 on `GET /workspaces/{2**63}`, violates REQ-0020 existence-leak invariant, invisible to engineer stack. Total findings: 1 high / 6 medium / 3 low. See `runs/qa-001-test-engineer-bl-0002/scorecard.md`. |
| `qa-001-test-engineer-bl-0003` | 2026-05-14 | `project-tracker-v1-engineering-baseline` @ `a898011` | QA | `test-engineer` | `qa-001-test-engineer-bl-0003` | Pass | 74/75 (+ protocol axes 40/40) | None | Third QA cycle. Engineer stack 6/6 pass. 33-scenario suite (20 BL-0002 carry-forward + 13 BL-0003 added); all 19 non-known-bug carry-forward scenarios pass against `a898011`; carried huge-ID bug (`BUG-QA001-BL2-001`) still failing as expected. **Second real engineering defect surfaced — `BUG-QA001-BL3-001` CRITICAL**: concurrent dual-admin `DELETE` both return 204; non-transactional read-then-delete at `app.py:429-444` violates BL-0003 AC 5 / REQ-0006; deterministic via `threading.Barrier(2)`; invisible to engineer's single-threaded `TestClient` stack. New findings: 1 critical / 3 medium / 4 low. KNOWN_BUGS registry pattern introduced for carry-forward handling. See `runs/qa-001-test-engineer-bl-0003/scorecard.md`. |
| `qa-001-test-engineer-bl-0005` | 2026-05-14 | `project-tracker-v1-engineering-baseline` @ `f600039` | QA | `test-engineer` | `qa-001-test-engineer-bl-0005` | Pass | 74/75 (+ protocol axes 40/40) | None | Fourth QA cycle. Engineer stack 7/7 pass. 46-scenario suite (33 BL-0003 carry-forward + 13 BL-0005 added); 42 pass / 4 known-bug fail / 0 unknown fail. **2 new High findings — both tier-extensions of prior defect classes**: `BUG-QA001-BL5-001` (huge-project-ID 500, parity with BL-0002 at project tier); `BUG-QA001-BL5-002` (concurrent admin project-delete race, parity with BL-0003 at project tier). Engineering has not centralized either fix. KNOWN_BUGS registry now tracks 4 entries. See `runs/qa-001-test-engineer-bl-0005/scorecard.md`. |
| `qa-001-test-engineer-bl-0006` | 2026-05-14 | `project-tracker-v1-engineering-baseline` @ `7f6d104` | QA | `test-engineer` | `qa-001-test-engineer-bl-0006` | Pass | 74/75 (+ protocol axes 40/40) | None | Fifth QA cycle. Engineer stack 8/8 pass. 62-scenario suite (49 carry-forward + 13 BL-0006 added); 56 pass / 5 known-bug fail / 1 new known-bug. **Refactor parity PASS** — zero regressions across all 45 non-known-bug carry-forward scenarios against the refactored codebase. **Both activations verified working** (BL-0003 AC 6/7/8 assignee clearing; BL-0005 AC 7 project-delete task cascade) with DB row inspection. **Class A recurred at task tier** (`BUG-QA001-BL6-001` High; now 3 tiers). **Class B did NOT recur at task tier** (`BUG-QA001-BL6-002` Low positive observation — but Class B remains active at member + project tiers; not evidence of centralized fix). New defect class `BUG-QA001-BL6-003` Medium: whitespace-only title stored as empty string after router strips post-Pydantic. See `runs/qa-001-test-engineer-bl-0006/scorecard.md`. |

## Candidate Evaluation Queue

Rule: process one queue item through a full evaluation cycle before starting the next queue item.

Cycle statuses:

- `Queued`: not started.
- `Selecting Skill`: candidate repo is being inspected and the specific `SKILLS.md` file is being chosen.
- `Ready`: skill file, brief, target repo, and rubric are selected.
- `Running`: evaluation is in progress.
- `Scored`: artifacts and scorecard are complete.
- `Blocked`: cannot proceed without a decision or missing dependency.
- `Skipped`: intentionally deferred.

| Queue ID | Role | Candidate Source | Priority | Status | Selected Skill Path | Run ID | Notes |
|---|---|---|---:|---|---|---|---|
| PO-001 | PO | `Agile-V/agile_v_skills` | 1 | Scored | `agile-v-product-owner/SKILL.md` | `po-001-agile-v-product-owner` | Decision `Pass`; score `66/75`; selected direct PO skill for backlog, story, sprint, and REQ-to-story work |
| PO-002 | PO | `deanpeters/Product-Manager-Skills` | 2 | Queued | TBD |  | Broad PM/PRD/backlog management collection |
| PO-003 | PO | `mattpocock/skills` | 3 | Queued | TBD |  | Evaluate PRD/issues/grilling skills for requirement decomposition |
| ENG-001 | Engineer | `addyosmani/agent-skills` | 1 | Scored | `skills/incremental-implementation/SKILL.md` | `eng-001-incremental-implementation-bl-0007` | Decisions `Pass` for `BL-0001`, `BL-0002`, `BL-0003`, `BL-0005`, `BL-0006`, and `BL-0007`; latest score `74/75` (tied with BL-0006 high) |
| ENG-002 | Engineer | `mattpocock/skills` | 2 | Queued | TBD |  | Strong TDD/debugging/architecture candidate |
| ENG-003 | Engineer | `anthropics/skills` | 3 | Queued | TBD |  | Official skill examples and reusable engineering patterns |
| QA-001 | QA | `addyosmani/agent-skills` | 1 | Running (5/6 scored) | `agents/test-engineer.md` | Five cycles Pass 74/75 + axes 40/40; **5 real engineering defects on forward-propagating chain** (Class A: 3 tiers; Class B: 2 tiers; plus whitespace title) + refactor parity verified; one cycle remains (BL-0007); see QA-001 Cycle Plan below |
| QA-002 | QA | `fugazi/test-automation-skills-agents` | 2 | Queued | TBD |  | Dedicated test automation candidate |
| QA-003 | QA | `jaktestowac/awesome-copilot-for-testers` | 3 | Queued | TBD |  | Discovery source; may require selecting a concrete linked skill |

## QA-001 Cycle Plan

`QA-001` (`addyosmani/agent-skills`) runs six per-BL QA cycles against the engineering BL closing commits, in the order engineering closed them. Each cycle accumulates the journey suite. Each cycle is independently scored. No next cycle starts until the prior cycle is `Scored`.

| Cycle | Engineering BL | Target Commit | Status | QA Run ID | Notes |
|---|---|---|---|---|---|
| 1 | BL-0001 | `5baf798` | **Scored (Pass 74/75)** | `qa-001-test-engineer-bl-0001` | Engineer stack 4/4 pass; journey suite 11/11 pass via subprocess Uvicorn + real HTTP; zero application defects; 8 verification-stack gap findings (5 medium + 3 low); see `runs/qa-001-test-engineer-bl-0001/scorecard.md`. |
| 2 | BL-0002 | `c5e89e3` | **Scored (Pass 74/75 + axes 40/40)** | `qa-001-test-engineer-bl-0002` | Engineer stack 5/5 pass; 20-scenario suite (11 carry-forward + 9 added); suite continuity preserved; **first real engineering defect surfaced — `BUG-QA001-BL2-001` High: uncaught 500 on `GET /workspaces/{2**63}`**; 1 high / 6 medium / 3 low findings; see `runs/qa-001-test-engineer-bl-0002/scorecard.md`. |
| 3 | BL-0003 | `a898011` | **Scored (Pass 74/75 + axes 40/40)** | `qa-001-test-engineer-bl-0003` | Engineer stack 6/6 pass; 33-scenario suite (20 carry-forward + 13 added); continuity preserved; **second real engineering defect surfaced — `BUG-QA001-BL3-001` CRITICAL: concurrent dual-admin removal violates last-admin invariant (non-transactional read-then-delete at `app.py:429-444`)**; KNOWN_BUGS registry pattern introduced; new findings 1 critical / 3 medium / 4 low; carried huge-ID known bug still failing; see `runs/qa-001-test-engineer-bl-0003/scorecard.md`. |
| 4 | BL-0005 | `f600039` | **Scored (Pass 74/75 + axes 40/40)** | `qa-001-test-engineer-bl-0005` | Engineer stack 7/7 pass; 46-scenario suite (33 carry-forward + 13 added); 42 pass / 4 known-bug fail / 0 unknown fail; **2 new High findings, both tier-extensions of prior defect classes** (`BUG-QA001-BL5-001` huge-ID OverflowError at project tier; `BUG-QA001-BL5-002` concurrent admin project-delete race); KNOWN_BUGS registry now tracks 4 entries; see `runs/qa-001-test-engineer-bl-0005/scorecard.md`. |
| 5 | BL-0006 | `7f6d104` | **Scored (Pass 74/75 + axes 40/40)** | `qa-001-test-engineer-bl-0006` | Engineer stack 8/8 pass; 62-scenario suite (49 carry-forward + 13 added); **refactor parity PASS** (zero regressions across 45 non-known-bug scenarios); both activations verified (assignee clearing + project-delete task cascade); **Class A recurred at task tier** (`BUG-QA001-BL6-001` High, now 3 tiers); **Class B did NOT recur at task tier** (`BUG-QA001-BL6-002` positive observation — Class B remains active at member + project tiers); new defect class `BUG-QA001-BL6-003` Medium (whitespace title stored as empty); see `runs/qa-001-test-engineer-bl-0006/scorecard.md`. |
| 6 | BL-0007 | `87939ad` | Pending | `qa-001-addyosmani-bl-0007` | After this cycle, `QA-001` becomes a forward gate. |

## Candidate Target Repos

| Repo | Type | Status | Notes |
|---|---|---|---|
| `project-tracker-v1-po-baseline` | Local PO planning benchmark | Ready | Baseline commit `16298e98f1a9006ec91168e4bb9220addd098e92`; verifier: `python3 verify_po_artifacts.py` |
| `project-tracker-v1-engineering-baseline` | Local engineering implementation benchmark | Ready | Baseline commit `f71c498014a368fc54a4465f773846939e6d518f`; first verifier: `python verify_bl0001.py` |

## Candidate Briefs

| Brief ID | Type | Status | Notes |
|---|---|---|---|
| `project_tracker_v1_po_planning` | Greenfield PO planning | Ready | Path `briefs/project_tracker_v1_po_planning.md`; SHA-256 `112df0086c09bc56f715e20e8d305cd4ef0f09ef7cd23f969f5e798cb654d866` |
| `bl-0001-authenticated-account-foundation` | Engineering work packet | Ready | Path `briefs/engineering-work-packets/bl-0001-authenticated-account-foundation.md`; SHA-256 `6f4bfbcd3711c04b8c22520c0e155a1582d954b5c454be2d2f9b811b10d139d5` |
| `bl-0002-workspace-privacy-boundary` | Engineering work packet | Ready | Path `briefs/engineering-work-packets/bl-0002-workspace-privacy-boundary.md`; SHA-256 `c76ee3cc3c74ba7a7de54afcffd75c44c288edcd0834328f95f43316993d5645` |
| `bl-0003-workspace-member-management-and-role-matrix` | Engineering work packet | Ready | Path `briefs/engineering-work-packets/bl-0003-workspace-member-management-and-role-matrix.md`; SHA-256 `8eb0eb5ffd155ada7ef171b5b6acc58ab1eb51c08382720f22a2bc659b6f015b` |
| `bl-0005-project-crud-within-a-workspace` | Engineering work packet | Ready | Path `briefs/engineering-work-packets/bl-0005-project-crud-within-a-workspace.md`; SHA-256 `229901a02f740818bb9e104f10d3b6a02a6655263abd4afa968867624b5a5c01` |
| `bl-0006-task-crud-status-and-assignment-rules` | Engineering work packet | Ready | Path `briefs/engineering-work-packets/bl-0006-task-crud-status-and-assignment-rules.md`; SHA-256 `bd9fb5603901ba7d43ca264186b75b11f26fb107b869bb9ea765a4101117f28d`; bundles required `app.py` split + verifier decoupling + activation of BL-0003 AC 6/7/8 and BL-0005 AC 7 (task path) |
| `bl-0007-task-comments-for-all-workspace-members` | Engineering work packet | Ready | Path `briefs/engineering-work-packets/bl-0007-task-comments-for-all-workspace-members.md`; SHA-256 `6f59879d4c841e0f9275384481870a48fdf2ff60b61b41cde30beeaae3872b44`; viewer-mutation exception, comment retention after author removal, full activation of BL-0005 AC 7 cascade |
| TBD | Brownfield | Pending | Should exercise repo-reading and integration |

## Skill Inventory

### Product Owner Skills

| Skill ID | Source Repo | Path | Hash | Status | Notes |
|---|---|---|---|---|---|
| `po-001-agile-v-product-owner` | `Agile-V/agile_v_skills` | `agile-v-product-owner/SKILL.md` | `f1ad9fff24c8630ac0ae32eedbb72b7bf3fbac459d736d8251434d8a696c5eea` | Snapshotted | Source commit `3e59bfb4bdf5f317b659e2852d0ced3369cd2c07`; local snapshot `skills/po/po-001-agile-v-product-owner/SKILLS.md` |

### Engineer Skills

| Skill ID | Source Repo | Path | Hash | Status | Notes |
|---|---|---|---|---|---|
| `eng-001-incremental-implementation` | `addyosmani/agent-skills` | `skills/incremental-implementation/SKILL.md` | `5f16adf542330dfadb8b9a9c6d7ec45e4196bd1db9a67d4407e9dc07e6e29e41` | Snapshotted | Source commit `5b4c6dade5e6b5a48067d08861a11732d8e3a2bf`; local snapshot `skills/engineer/eng-001-incremental-implementation/SKILLS.md` |

### QA Skills

| Skill ID | Source Repo | Path | Hash | Status | Notes |
|---|---|---|---|---|---|
| `qa-001-test-engineer` | `addyosmani/agent-skills` | `agents/test-engineer.md` | `1e6d69462066eac39c7f19f8ad13b527dc8db6c2266dc551b4002e99b8096745` | Snapshotted | Source commit `5b4c6dade5e6b5a48067d08861a11732d8e3a2bf`; explicit QA-engineer framing for test strategy + writing + coverage analysis; local snapshot `skills/qa/qa-001-test-engineer/SKILLS.md` |

## Open Questions

- Which target repos should form the first benchmark set?
- Should the first benchmark use only greenfield briefs, or mix greenfield and brownfield from the start?
- What is the minimum acceptable objective rubric before running comparisons?
- Should each skill variant be run once first, then repeated only for finalists?
- How should we separate skill failures from model failures and tool/runtime failures?

## Next Actions

1. **Author QA-001 BL-0007 work packet** at target commit `87939ad` — the final catch-up cycle. Carry-forward the 62-scenario suite from `qa-001-test-engineer-bl-0006/journey_suite/`. Add J-COM-001..007 plus probes for the viewer-mutation exception (only viewer-can-mutate surface in v1), comment retention after author removal, full project-delete cascade (comments + tasks both cleared), and next-tier systemic-defect probes (Class A at comment tier; Class B at comment delete). Submit to the QA agent.
2. **After BL-0007 cycle scores Pass**: `QA-001` becomes a forward gate on the engineering pipeline. The next engineering BL (BL-0004 workspace-deletion-cascade or BL-0008/0009 read-only surfaces) opens with QA gating built in from the start.
3. **After QA-001 BL-0007 cycle scores Pass**, QA-001 becomes a forward gate. The next engineering BL (likely BL-0004 or BL-0008) opens with QA gating built-in from the start.
4. **First cross-skill comparison opportunity** still pending. Engineering surface at `87939ad` is large enough that `ENG-002` (`mattpocock/skills`) on an equivalent baseline would produce a legible comparison. Defer launching until QA-001 catch-up completes — focus is currently on closing the QA gate, not opening a second engineering thread.
5. **Optional maintenance commit.** Rename `HTTP_422_UNPROCESSABLE_ENTITY` to `HTTP_422_UNPROCESSABLE_CONTENT` to silence the deprecation warning (informational, not blocking).
3. **Outstanding QA-001 findings to track separately** (live on every commit until engineering remediates):
   - BL-0001 cycle: 5 medium + 3 low verification-stack gap findings. Engineering's systemic version addressed at BL-0006. No action on historical commits.
   - **Two systemic defect classes confirmed by tier-repetition; refactor at BL-0006 did NOT centralize fixes**:
     - **Class A — Huge-ID `OverflowError` → 500 existence-leak**. Confirmed at 3 tiers: `BUG-QA001-BL2-001` (workspace, High), `BUG-QA001-BL5-001` (project, High), `BUG-QA001-BL6-001` (task, High). Comment tier untested until BL-0007 cycle. **Centralized fix**: Pydantic `Field(le=2**63 - 1)` constraint on all path-parameter IDs, OR a global `OverflowError` exception handler mapping to 404.
     - **Class B — Read-then-mutate concurrency race**. Confirmed at 2 tiers: `BUG-QA001-BL3-001` (member removal, Critical), `BUG-QA001-BL5-002` (project delete, High). Did **not** recur at task tier (`BUG-QA001-BL6-002` Low positive observation — path-specific behavior, not centralized fix). Comment-delete tier untested until BL-0007 cycle. **Centralized fix**: `BEGIN IMMEDIATE` around read+mutate, OR app-level lock, OR recount-after-mutate inside the same transaction.
   - **New defect class** (BL-0006 cycle): `BUG-QA001-BL6-003` Medium — whitespace-only title stored as empty string. Router strips after Pydantic validation, bypassing `Field(min_length=1)`. Class C: post-validation mutation hole. Likely to recur on every string-typed body field that gets stripped server-side. Centralized fix: strip BEFORE Pydantic validation, OR use a `field_validator` to enforce post-strip non-emptiness.
   - **Remediation routing**: a single maintenance commit on `main` (`87939ad`+N) fixing all three defect classes centrally is the highest-leverage engineering work the project can do before v1 release. Per protocol, findings do not auto-reopen the engineering scorecard — remediation is a deliberate decision routed through whatever process the user prefers.
   - **`KNOWN_BUGS` registry handles propagation**: 5 entries currently (4 carried + 1 added at BL-0006). All continue to execute on every subsequent QA cycle and report as known-bug failures until engineering fixes them.


<!-- langgraph_engine run po-lg-lg-SKILLS -->
See `runs/_summary-po-lg-lg-SKILLS.md` for run summary.


<!-- langgraph_engine run po-lg-lg-SKILLS -->
See `runs/_summary-po-lg-lg-SKILLS.md` for run summary.


<!-- langgraph_engine run po-lg-lg-SKILLS -->
See `runs/_summary-po-lg-lg-SKILLS.md` for run summary.


<!-- langgraph_engine run po-lg-lg-SKILLS -->
See `runs/_summary-po-lg-lg-SKILLS.md` for run summary.


<!-- langgraph_engine run po-lg-lg-SKILLS -->
See `runs/_summary-po-lg-lg-SKILLS.md` for run summary.


<!-- langgraph_engine run po-lg-lg-SKILLS -->
See `runs/_summary-po-lg-lg-SKILLS.md` for run summary.


<!-- langgraph_engine run po-lg-lg-SKILLS -->
See `runs/_summary-po-lg-lg-SKILLS.md` for run summary.
