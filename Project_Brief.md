# Project Brief — agentic-skills

## 1. What This Project Is About

`agentic-skills` is a **controlled evaluation harness for role-specific AI agent skills** written in the `SKILLS.md` format. The goal is to measure — with reproducible, objective artifacts — how well different skill definitions guide an LLM agent through the work of a Product Owner, an Engineer, or a QA Engineer on a realistic software-delivery cycle.

### Core thesis

A `SKILLS.md` file is a system prompt expressing one specific operational doctrine for one role (e.g., "Agile-V Product Owner v1", "Incremental Implementation Engineer", "Test Engineer with journey-suite continuity"). The project asks: **given identical inputs (brief, repo, model) and changing only the skill file, what is the delta in deliverable quality?**

### Evaluation principle

```
one candidate source → one role → one skill file → one brief → one scorecard
```

Each run produces:
- A run directory under `runs/<role>-<skill>-<bl>/` containing raw logs, metadata, verification output, output artifacts, diffs, and a scorecard
- A scored rubric evaluation against `rubrics/production_grade_scorecard.md` (core dimensions 0–50, role-specific 0–25, QA protocol axes 0–40)
- A Pass / Pass-with-reservations / Fail decision with documented failure modes

### Two execution modes

1. **Manual orchestration** — A human runs each role in a fresh Claude Code session, following `docs/full_cycle_execution_protocol.md`. The original baseline (`po-001-agile-v-product-owner`, `eng-001-incremental-implementation`, `qa-001-test-engineer`) was scored this way.
2. **LangGraph automation engine** (`langgraph_engine/`) — A LangGraph state machine drives PO → Engineering → QA → loop entirely autonomously against an Azure OpenAI deployment, producing scorecards and artifacts in the same on-disk layout as the manual process. Used for A/B model comparison and large-scale skill evaluation.

### Workload under evaluation

The current evaluation target is **Project Tracker v1** — a FastAPI service for tracking projects and tasks across private team workspaces. The brief (`briefs/project_tracker_v1_po_planning.md`) hands the PO an approved `REQUIREMENTS.md` and asks for `BACKLOG.md` + `SPRINT_PLAN_C1.md`; the Engineer implements each backlog item (BL-0001 …); QA runs a real-deployment journey suite, executes the engineer's verification stack, audits coverage gaps, and tracks bugs with carry-forward continuity across cycles.

Critical product invariants under test:
- 404 vs 403 privacy semantics (don't leak resource existence to non-members)
- Cascade behavior (workspace delete → projects → tasks → comments)
- Assignee-clearing when a member is removed from a workspace
- `/me/tasks` is strictly "my assigned tasks", not "tasks I can see"
- Cross-tenant isolation

---

## 2. Tech Stack

### Harness / evaluation engine

| Layer | Choice |
|---|---|
| Orchestration | **LangGraph** state machine (`langgraph_engine/graph.py`) |
| LLM client | `langchain-openai` `AzureChatOpenAI` |
| Model provider | **Azure OpenAI** — endpoint `aif-eus2-intplatformsvc-dev-001.cognitiveservices.azure.com` |
| Active deployment | **`gpt-5.4`** (full), API version `2024-12-01-preview` |
| Prior deployment | `md-gpt-5.4-mini` (used in Run #2 baseline for A/B comparison) |
| Python | 3.12 |
| Engine venv | `.venv-lg` at workspace root (separate from target-repo venvs) |
| Agent loop | Custom tool-dispatch loop (`agent_loop.py`), 300-iteration cap per agent, `recursion_limit=1000` on the graph |

### Graph nodes (`langgraph_engine/nodes/`)

```
initialize → po_cycle → parse_backlog → advance_index
                                          │
                                          ├── (ready BLs) → author_eng_packet → run_eng_agent
                                          │                  → score_eng
                                          │                  → author_qa_packet → run_qa_agent
                                          │                  → score_qa → advance_index ↺
                                          │
                                          └── (no ready BLs) → finalize → END
```

### Workspace-sandboxed agent tool set (`langgraph_engine/tools.py`)

- `read_file`, `write_file`, `edit_file`, `list_dir`, `bash`, `copy_path`, `sha256_file`
- Bash is unsandboxed inside the workspace (deliberate parity with Claude Code)

### Engineering target stack (project_tracker_v1)

| Layer | Choice |
|---|---|
| Web framework | **FastAPI ≥ 0.136.1** |
| ORM | **SQLAlchemy ≥ 2.0.49** |
| Data validation | **Pydantic ≥ 2.13.4** |
| ASGI server | **uvicorn** (subprocess-launched for QA journey tests) |
| HTTP client (testing) | **httpx** |
| Test runner | **pytest** |
| Persistence | In-memory (current BL-0001/0002 implementations); SQLite intended per QA work packet |
| Target venv | `target-repos/lg-graph-test/.venv` |

### Scoring / rubrics

- `rubrics/production_grade_scorecard.md` — core (0–50) + role-specific (0–25); QA adds protocol axes (0–40)
- Score node uses the LLM with the rubric and emits both `scorecard.md` and an `outcome` block patched into `metadata.yaml`

### Artifact layout (per skill)

```
skills/<role>/lg-<skill>/SKILLS.md           # snapshotted source skill + hash
briefs/engineering-work-packets/bl-XXXX-*.md
briefs/qa-work-packets/qa-lg-<skill>-bl-XXXX.md
runs/po-lg-<skill>/                          # PO cycle artifacts
runs/eng-lg-<skill>-bl-XXXX/                 # per-BL engineering run
runs/qa-lg-<skill>-bl-XXXX/                  # per-BL QA run with journey suite
runs/_summary-po-lg-<skill>.md
target-repos/<repo>/                         # the product being built
```

---

## 3. Current Status (2026-05-14 → 2026-05-15)

### Four-Model Cross-Provider Comparison

**Per-cycle Eng/QA scores across all comparable runs:**

| BL | Qwen3 Coder-Next | Claude Opus 4-7 | gpt-5.4 R#5 | gpt-5.4 R#6 | gpt-5.1 |
|---|---|---|---|---|---|
| BL-0001 | 73 P / 73 P | 74 P / 73 P | 61 P / 61 F | 58 P / 51 F | 71 P / **36 F** |
| BL-0002 | 73 P / **75 P** ⭐ | 73 P / — | 65 P / 59 F | 62 P / 51 F | 68 P / 54 W |
| BL-0003 | 69 P / **75 P** ⭐ | — | 64 P / 59 W | 63 P / 60 F | 73 P / **29 F** |
| BL-0004 | 74 P / 70 P | — | 65 P / 61 W | 62 P / 59 F | 63 P / **39 F** |
| BL-0005 | 73 P / — (killed) | — | 68 P / 59 W | 63 P / 57 F | 67 P / **29 F** |
| BL-0006 | — | — | 65 P / 59 W | 62 P / 53 F | 69 P / **23 F** (worst) |
| BL-0007 | — | — | — | — | 66 P / malformed |

Legend: `P` = Pass · `W` = Pass-W/R · `F` = Fail · ⭐ perfect 75/75 · — not run

**Aggregate by model:**

| Provider/Model | Cycles | Eng avg | Eng range | QA avg | QA Pass / W/R / Fail | Notes |
|---|---|---|---|---|---|---|
| **Qwen3 Coder-Next** (HF→Novita) | 4 full + 1 eng | **72.4** | 69–74 | **73.25** | **4 / 0 / 0** | Two perfect 75/75 QA scorecards. BL-0006 eng thrashed; manually killed |
| Claude Opus 4-7 (Anthropic) | 1 full + 1 eng | 73.5 | 73–74 | 73.0 | 1 / 0 / 0 | Credit-exhaustion crash at BL-0002 QA |
| gpt-5.4 Run #5 (Azure) | 6 | 64.3 | 61–68 | 59.7 | 0 / 4 / 2 | Stable full run |
| gpt-5.4 Run #6 (Azure) | 6 | 61.6 | 58–63 | 55.2 | 0 / 0 / **6** | Full Fail on QA |
| **gpt-5.1** (OpenAI direct) | 7 | 68.1 | 63–73 | **35.0** | **0 / 1 / 6** | Worst QA across all runs |

### Headline findings (four-model)

1. **Provider quality dominates within-provider variance.** Range across providers (35–73 QA avg) is 38 points. Range within gpt-5.4 (Run #5 vs Run #6 identical config) is 4 points. The signal is real, not noise.

2. **Qwen3 Coder-Next is the surprise winner.** 4/4 Pass QA, two perfect 75/75 scorecards, no Fail on any dimension. Slightly behind Claude on core scores but ties/exceeds it on protocol axes and QA-rubric. Beat all OpenAI variants on every cycle.

3. **gpt-5.1 has the inverse-pattern collapse.** Engineering is mid-tier (68.1 avg, better than gpt-5.4) but QA is catastrophic — 35.0 avg, worse than every other model including gpt-5.4. Root cause inspection (BL-0001 QA rationale) shows gpt-5.1's journey runner couldn't bring subprocess Uvicorn up within its 10s readiness window; agent correctly diagnosed harness brittleness but **did not autonomously debug or extend the timeout**. Same harness conditions; other models handled startup correctly. This is a model-specific autonomy failure on test-infrastructure work, not a "skipped QA" issue.

4. **First Pass-grade QA verdicts in project history** all came from Qwen and Claude. gpt-5.4 produced 0/12 Pass QA. gpt-5.1 produced 0/7 Pass QA.

5. **Engineering scores compress; QA scores spread.** Eng range across all 4 providers: 58–74 (16-pt spread). QA range: 23–75 (52-pt spread). QA work discriminates models far more than engineering work — which makes sense: engineering passes if code compiles + verifier passes; QA passes only if you can also build, gate, and reason adversarially about your own work.

6. **Speed ordering** (rough wall-clock to 5 cycles): gpt-5.1 ~30 min · gpt-5.4 ~13 min for 6 · Claude Opus ~30 min for 1.5 (extrapolates >120 min) · Qwen ~110 min for 5. Qwen is slow because of single-tool-per-iter; gpt-5.1 is fast because of aggressive multi-tool batching.

7. **Both alternative providers (Claude, HF) crashed on billing**, not code. Two harness extensions to non-Azure providers, two billing-related terminations. Azure OpenAI was reliable for full runs but produced the worst QA quality.

### Run History (complete record)

| Run | Provider | Model | BL Cycles | Outcome |
|---|---|---|---|---|
| #1 (manual) | Claude Code | Claude (interactive) | 6 manual cycles | Baseline `eng-001/qa-001/po-001` scorecards |
| #2 | Azure OpenAI | `md-gpt-5.4-mini` | 3 of 9 | Eng 41–67, QA 28–65, 2 Fail / 1 Pass-W/R |
| #3 | Azure OpenAI | `gpt-5.4` | 0 | Aborted — backlog parser bug (status-label format mismatch) |
| #4 | Azure OpenAI | `gpt-5.4` + parser fix | 2 of 6 | Validation of parser fix; superseded by Run #5 |
| **#5** | Azure OpenAI | `gpt-5.4` | **6 of 6** | Eng 61–68 (100% Pass), QA 59–61 (2 Fail / 4 Pass-W/R / 0 Pass) |
| **#6** | Azure OpenAI | `gpt-5.4` (identical config) | **6 of 6** | Eng 58–63 (100% Pass), QA 51–60 (**6 Fail / 0 Pass-W/R / 0 Pass**) — variance discovery |
| **#7** | Anthropic | `claude-opus-4-7` | **1.5 of 6** | BL-0001 Eng 74 Pass / QA 73 Pass; BL-0002 Eng 73 Pass; crashed at BL-0002 QA — **credit exhaustion** |
| **#8** | HF router → Novita | `Qwen/Qwen3-Coder-Next:novita` | **1 of 6** | BL-0001 Eng 72 Pass / QA 69 Pass; crashed at BL-0002 Eng — **HF monthly free credits exhausted** |
| **#9** | HF router → Novita | `Qwen/Qwen3-Coder-Next:novita` (relaunched after credit top-up) | **5 of 6** (killed) | All 5 cycles Pass/Pass; two perfect 75/75 QA scorecards. BL-0006 eng thrashed at iter 135, killed manually |
| **#10** | OpenAI (direct) | `gpt-5.1` | **7 of 7** | All eng Pass (63–73); QA collapse: 6 Fail / 1 Pass-W/R / 0 Pass; root cause = brittle journey runner, not skipped work |

(Also: one HF run with `Qwen3-Next-80B-A3B-Instruct` crashed at BL-0001 Eng with opaque HTTP 400; replaced with Coder-Next:novita.)

### Cross-cutting observations

1. **Provider quality > within-provider variance.** Run #5 vs Run #6 on identical config: 7-pt Eng band, 8-pt QA band, full verdict flip on 4 of 6 QA cycles. Provider switch (gpt-5.4 → Claude/Qwen): consistent 12–22 pt jump, never observed below 69 across 5 measured cycles.
2. **First Pass-grade QA verdicts of the whole project** came from Claude and Qwen. gpt-5.4 never produced a Pass QA across 12 cycles.
3. **Both alternative-provider runs crashed on billing**, not on code. Claude crashed at BL-0002 QA (Anthropic credits). Qwen crashed at BL-0002 Eng (HF monthly free credits). To get full 6-cycle data, either provider needs pre-paid credits.
4. **Iteration-style differences:**
   - gpt-5.4: aggressive multi-tool batching (5–10 calls/iter), 16–19 iters per Eng cycle
   - Claude Opus: mostly sequential (1 tool/iter), 19 iters per Eng, slow per-iter (~1 min)
   - Qwen Coder-Next: extreme single-tool loops, **55–82 iters per cycle**, fast per-iter (~5s)
5. **Harness extensibility validated.** Three providers (Azure OpenAI, Anthropic, HF router) work through the same `LLMConfig`/`build_llm` dispatch with no per-provider node code. New providers add by extending `from_env` and `build_llm` branches only.

### Outstanding open items

- **Full 6-cycle data for Claude and Qwen** — both need pre-paid credits to complete. Currently only have 1–1.5 BLs each.
- **Why does Qwen iterate 4× more than Claude/gpt-5.4?** Worth inspecting whether it's verification-heavy (good) or churn (bad). Could be addressed with skill-prompt tuning or by adding an iteration-efficiency rubric dimension.
- **Investigate Qwen3-Next-80B HTTP 400 root cause** — separate from credits, that model+backend combo had a real protocol incompatibility. Coder-Next:novita worked; Next-80B:default did not.
- **Score-stability question still open** — scoring is itself LLM-generated (currently with the same model that did the work). Independent scorer would test whether Claude-and-Qwen's high marks are partially self-rating bias.

### Original Run #5 detail (preserved below for completeness)

### Run #5 — **COMPLETE**

- PID 71272 exited cleanly; 6 BL cycles delivered
- Log: `/tmp/lg-run.log`
- Target repo: `target-repos/lg-graph-test/` (bootstrapped venv + prod deps)
- Brief: `briefs/project_tracker_v1_po_planning.md`
- Skills under test: `po-001-agile-v-product-owner`, `eng-001-incremental-implementation`, `qa-001-test-engineer`
- Model: **gpt-5.4** (full)

### Final scoreboard

| BL | Engineering | QA | Notes |
|---|---|---|---|
| **BL-0001** | Pass **61/75** | **Fail 61/75** | Eng: FastAPI skeleton + bearer auth scaffolds. QA gating defect `QA-BL-0001-001` (High) — packet-required real `/signup`/`/login` missing; Eng used hard-coded bearer tokens |
| **BL-0002** | Pass **65/75** | **Fail 59/75** | Eng: workspace create + private 404-on-non-member, in-memory store. QA: carried `QA-BL-0001-001` forward as still-gating |
| **BL-0003** | Pass **64/75** | Pass W/R **59/75** | Inflection point: QA shifts Fail→Pass-W/R, indicating Eng addressed the real-auth blocker |
| **BL-0004** | Pass **65/75** | Pass W/R **61/75** | QA peaks at 61 |
| **BL-0005** | Pass **68/75** | Pass W/R **59/75** | Eng peaks at 68 — highest in run |
| **BL-0006** | Pass **65/75** | Pass W/R **59/75** | Final cycle; remaining backlog items not marked Ready by PO |

**Aggregate:** 6 engineering Pass / 0 Fail · 2 QA Fail / 4 QA Pass-W/R / 0 QA Pass · Eng range 61–68 (band 7) · QA range 59–61 (band 2)

### Key observations

- **Engineering perfectly consistent** — every BL passed, narrow 7-pt scoring band, peak at BL-0005
- **QA inflection at BL-0003** — Fail → Pass-W/R transition strongly suggests Eng began honoring the real `/signup`/`/login` requirement starting BL-0003. Carried high-severity blocker cleared
- **QA ceiling stuck at 61** — even after auth blocker cleared, no QA cycle reached full Pass. Persistent gating factors remain (likely persistence durability, journey depth, or new defects each cycle)
- **No Critical defects surfaced** across the run; QA bug discovery shifted from "carry-forward known bug" to incremental new findings after BL-0003

### Run history (A/B context across runs)

| Run | Model | Outcome |
|---|---|---|
| Run #1 (manual baseline) | Claude Code | Original baseline scorecards (eng-001 / qa-001 / po-001 series in `runs/`) |
| Run #2 | `md-gpt-5.4-mini` | 3/9 BL items processed (mini gated to 3-item Ready cohort); eng 41–67, QA 28–65 (2 Fails, 1 Pass-with-Reservations) |
| Run #3 | `gpt-5.4` (aborted) | PO emitted 10 backlog items with status labels in a format the parser didn't recognize → parser fix required |
| Run #4 | `gpt-5.4` + parser fix | BL-0001 Eng 60 / QA 60 W-R; BL-0002 Eng 63 / QA scoring (last observed before this run) |
| **Run #5 (complete)** | `gpt-5.4` + parser fix | 6 BLs; Eng 100% Pass (61–68); QA 2 Fail / 4 Pass-W/R (59–61); inflection at BL-0003 |

### Quality findings observed so far

- **Engineering passes, QA fails** — consistent pattern across BL-0001 and BL-0002. Engineer deliberately skips real `/signup`/`/login` and persistence (in-memory); QA treats that as a packet-required gate violation. This is by-design surfacing of doctrine mismatch between skills.
- **Carry-forward continuity working** — QA-BL-0001-001 visible in BL-0002 QA bug report as a still-blocking known bug.
- **gpt-5.4 vs mini quality delta unresolved** — gpt-5.4 scores cluster slightly below mini on BL-0001 engineering (61 vs 67) despite superior tool parallelization (8-call batches, `copy_path` use absent in mini). Need BL-0003–BL-0007 data to draw conclusions.
- **Systemic defect patterns previously logged** (from prior manual cycles): integer overflow on huge IDs returning 500, concurrent DELETE races, whitespace-only validation gaps (`BUG-QA001-BL6-003`). Watch for recurrence in current run.

### Known historical issues fixed before current run

- **Skill snapshot path collision** — passing `lg-SKILLS` as source caused `shutil.SameFileError` in initialize node. Fixed by pointing to original skill directories.
- **Backlog status-label parser** — gpt-5.4 emitted Ready/Backlog labels in a format the grep didn't match. Fixed in Run #4.
- **Missing target-repo venv** — early Run #4 attempt had no venv in `lg-graph-test`, causing engineer verification to fail with `environment-missing-dependency`. Now bootstrapped before launch.

### Outstanding open items

- **A/B verdict gpt-5.4 vs md-gpt-5.4-mini** — Run #5 gives 6 complete cycles vs Run #2's 3; full comparison still pending head-to-head BL alignment
- **QA Pass-W/R ceiling investigation** — why no full Pass after BL-0003 auth fix? Need to inspect bug reports for residual gating factors
- **PO Ready-cohort sizing** — PO marked 6 BLs Ready (out of 10 total emitted); remaining 4 backlog items unprocessed. Open question whether to re-run with broader Ready cohort
- **Eng skill doctrine** — original eng-001 skill deferred real auth until BL-0003; QA flagged this as a gating violation in BL-0001/0002. Decision: update skill to honor packet-required auth from BL-0001, or treat the gap as a feature of the comparison
