# langgraph_engine

LangGraph implementation of the agentic-skills evaluation process. Mirrors the manual orchestration we ran for `PO-001` and the `ENG-001` / `QA-001` cycles: PO decomposes the brief, then for every `Ready` backlog item the graph authors an engineering work packet, runs the engineering agent, scores it, authors a QA work packet (with the prior cycle's journey suite carried forward), runs the QA agent, scores it, and loops.

## Runtime

The graph drives the role agents with **Azure OpenAI** via `langchain-openai`'s `AzureChatOpenAI`. The deployment, endpoint, API version, and key are read from `.env` at the workspace root.

Active deployment in this repo's `.env` is `md-gpt-5.4-mini` (API version `2024-12-01-preview`). The graph's behavior is shaped by:

1. The role's `SKILLS.md` (system prompt).
2. The work packet (system prompt addendum).
3. A user prompt that frames the task, names input files, and lists deliverables.
4. A tool set scoped to the workspace: `read_file`, `write_file`, `edit_file`, `list_dir`, `bash`, `copy_path`, `sha256_file`.

## Install

```bash
cd /Users/eugenegoldberg/dev/ai-projects/agentic-skills
python3 -m venv .venv-lg
source .venv-lg/bin/activate
pip install -r langgraph_engine/requirements.txt
```

Use a separate venv from the engineering target repo's `.venv` so dependencies don't collide.

## Usage

```bash
python -m langgraph_engine run \
    --project-name "my-project" \
    --workspace /Users/eugenegoldberg/dev/ai-projects/agentic-skills \
    --target-repo /path/to/empty-target-repo \
    --brief /path/to/project-brief.md \
    --po-skill /path/to/po-SKILLS.md \
    --eng-skill /path/to/eng-SKILLS.md \
    --qa-skill /path/to/qa-SKILLS.md
```

`--workspace` is the agentic-skills root where `runs/`, `briefs/`, `skills/`, and `docs/progress_tracker.md` live. The graph writes there exactly like the manual process.

`--target-repo` is the project under construction. PO writes planning artifacts here. Engineer implements code here. QA tests here. Should be either a fresh empty directory or a directory the PO can initialize as a git repo on its first cycle.

`--po-skill`, `--eng-skill`, `--qa-skill` point at the SKILLS.md files for each role. They get snapshotted under `skills/<role>/lg-<filename>/SKILLS.md` and hashed.

## On-disk layout written by the graph

```
<workspace>/
  skills/
    po/lg-<skill>/SKILLS.md
    eng/lg-<skill>/SKILLS.md
    qa/lg-<skill>/SKILLS.md
  briefs/
    engineering-work-packets/bl-XXXX-<slug>.md
    qa-work-packets/qa-lg-<skill>-bl-XXXX.md
  runs/
    po-lg-<skill>/
      metadata.yaml
      raw_logs/invocation.md
    eng-lg-<skill>-bl-XXXX/
      metadata.yaml
      verification.txt
      diff.patch
      output_artifacts/
      raw_logs/invocation.md
      scorecard.md
    qa-lg-<skill>-bl-XXXX/
      metadata.yaml
      engineer_stack_results.txt
      gap_audit.md
      journey_suite/run.py
      journey_results.json
      bug_report.md
      raw_logs/invocation.md
      scorecard.md
    _summary-po-lg-<skill>.md
```

## Graph shape

```
initialize
  └── po_cycle
        └── parse_backlog
              └── advance_index ── (more ready BLs?) ──► author_eng_packet
                                                              └── run_eng_agent
                                                                    └── score_eng
                                                                          └── author_qa_packet
                                                                                └── run_qa_agent
                                                                                      └── score_qa
                                                                                            └── advance_index ◄┘
                                  ── (no ready BLs) ───► finalize ── END
```

Each cycle through `advance_index → ... → score_qa → advance_index` adds one `CycleResult` to `state["completed_cycles"]`.

## Behavior parity vs. the manual process

The graph mirrors the **shape** of the manual process: per-BL work packets, per-BL run directories, carry-forward journey suites, behavior-based scoring against the rubric. It does **not** mirror Claude Code's exact tool semantics — the underlying model is `md-gpt-5.4-mini` rather than Claude, so output quality and decisions will differ. The orchestration template is faithful; the agents inside it are model-bound.

## Notes / caveats

- The PO node is heavy. The PO agent has to author multiple artifacts in one cycle. If your brief is large, expect a long single call.
- The engineering and QA agents are bounded at 300 iterations each. A failing cycle should surface as a `Fail` decision rather than runaway.
- `recursion_limit` on the LangGraph invocation is set to 1000 to handle backlogs with many BLs.
- Scoring uses the LLM with the existing `rubrics/production_grade_scorecard.md`. It writes both `scorecard.md` and patches the `outcome` block in `metadata.yaml`. The decision and score are then carried into `state["completed_cycles"]`.
- Bash, file edit, and write are unsandboxed inside the workspace. The graph deliberately does not restrict bash verbs (per the "mirror Claude Code" choice).
