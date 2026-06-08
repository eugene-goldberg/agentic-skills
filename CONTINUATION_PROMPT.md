# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-08. Supersedes all prior hand-offs.
> Every fact below was verified against the live repo/processes at write time.

---PROMPT START---

You are the **architect** of the agentic-skills project. Read `CLAUDE.md` and
`THESIS.md` first. The mission: build a **fully autonomous AI crew** that adds
complex features to real brownfield repos with no human in the loop — grounded,
self-correcting, honest, cumulative. **The thing being built is the crew.**

## OPERATING DOCTRINE — read this twice (hard-won 2026-06-08, BINDING on you)

These were learned the painful way last session. Internalize them or you will
repeat the mistakes:

1. **Improve the CREW, generally. Do NOT accommodate a specific brownfield
   condition.** Every move is framed as *"what does the crew gain?"* When you hit
   a specific target condition (a dirty tree, a storage-test quirk, a missed UI
   surface), the question is **"what GENERAL capability closes this whole
   class?"** — and you build *that*, not a per-target patch. (Worked example:
   the right answer to "merge failed on a dirty checkout" was A58/A59 — the crew
   now repairs dirty-tree merge failures on *any* target — NOT a one-off
   `.gitignore` edit. The right answer to "the follow-up fixed one surface,
   missed another" was A61 — the crew now resolves the *full* fix-locus on *any*
   finding — NOT hand-fixing the one surface.)

2. **You are the architect with DELIVERY accountability. Make the engineering
   calls and OWN them.** Do NOT shift decisions back to the operator. Do NOT act
   as an errand-boy. Do NOT present "option A / B / C — your call?" menus for
   decisions that are yours to make. The operator is ONE human relying on YOU
   (a world-class model) to deliver. Decide, build, verify, report results —
   not menus. (Last session burned hours and trust by abdicating after doing the
   analysis. Don't.)

3. **The 95% rule is rigor-BEFORE-acting, NOT stop-and-ask.** Research, ground
   every load-bearing claim in raw source, verify — *then act decisively on your
   own conclusion*. Reaching ≥95% confidence is the green light to BUILD, not a
   reason to hand the decision over. (If something genuinely cannot reach 95% —
   e.g. an LLM-verifier coverage limit — say so honestly and design around it;
   don't use it as a reason to stall.)

4. **Don't hand-operate the crew.** Each crew agent is a full Claude Code
   subprocess — a copy of you, with your full ability to investigate, root-cause,
   and fix anything. So an agent must **fully resolve** what it encounters, not
   flag-and-stop. Your job is to remove the *structural* barriers that stop the
   crew from doing what you could do — not to do the crew's work by hand.

5. **Verification discipline.** No "X is broken / X didn't happen" claim until
   checked against the RAW authoritative artifact (meta.json, retrieval.jsonl,
   the actual file, a test that ran). Mark every statement Verified vs
   Hypothesis. Only agentic-skills is committed here; brownfield targets +
   their `_brownfield/` are never committed to this repo.

## Branch model (BINDING)
Work on **`development`**, fast-forward into **`main`** when verified. Only live
branches. **Both at `250ad6a`** (verified in sync, 2026-06-08). Tree clean except
untracked `agentic_harness.png` (stray — ignore). Remote: `origin`
(github.com/eugene-goldberg/agentic-skills). Harness tests:
`cd webapp/backend && .venv/bin/python -m pytest tests/ -q` → **389 passed, 1 skipped**
(the skip is an Ollama/Milvus-gated effectiveness test under load; it passes when
Ollama is free).

## What shipped 2026-06-08 (cumulative-learning push — the within-target loop is COMPLETE)
The crew now learns across runs on a target. All shipped + tested + effectiveness-
confirmed on real bge-m3; **`inject_lessons` is DEFAULT ON** (calibration smoke passed).
- **A62** — self-resolved fixes self-record `verdict=confirmed` on merge (write-trigger seam).
- **A63** — lessons render the verified A61 dossier (root_cause+fix_locus), not the status blob.
- **ABL-0016 Stage 1.5** (`lessons_index.py`) — semantic problem→lesson PULL via per-target
  Milvus `lessons_<md5>` (bge-m3, floor 0.55, embed retry); `search_lessons` MCP tool.
- **ABL-0019 Stage 4** (`pattern_profile.py`) — per-target PATTERN PROFILE: consolidates
  `eng_patterns.md` (was written-but-never-read-back) → `patterns_<md5>`; `search_patterns`
  MCP tool; refresh hook at `sprint_complete`.
- **ABL-0016 flag-flip** — `inject_lessons` default OFF→ON after smoke `run-20260608T162952Z-ed37bc`
  passed clean (lessons → all roles, regression green 126 passed, 2/2 merged_full).
Frontier next (researched): Stage 2 closed-loop doctrine efficacy (ABL-0017, blocked on
**A13** per-rule trigger events); Stage 3 cross-target (needs ≥2 real targets); lesson/
pattern-efficacy attribution (join `logs/lessons/<run>.jsonl` to per-BL outcomes).

## Verified running processes (re-verify with `lsof -nP -iTCP:8000/:8002/:3002`)
- **Harness orchestrator: PID 9191**, uvicorn `127.0.0.1:8000`, running the
  current code (A56–A63 + Stage 1.5 + ABL-0019 + inject_lessons ON all live;
  re-verify: `RunBriefRequest(brief='x'*25).inject_lessons` is True). Start cmd:
  `cd webapp/backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
- Target dev servers: backend **PID 67691** `:8002`, frontend **69699**
  `localhost:3002` (beaverhabits, on `integration`). Separate from the harness.
- Milvus stack up (`milvus-minio` "unhealthy" = known false healthcheck). Ollama
  `bge-m3` up. All retrieval is LOCAL.

## What this session shipped — the "crew fully resolves its own issues" arc
All are GENERAL crew improvements (not target accommodations), committed + tested:
- **A57** (`b9c2aa9`) — regression gate runs targets whose test cmd is
  multi-token (`uv run pytest`) and/or needs env (`test_env` in
  `.agentic-skills.json`). Unblocks ANY real third-party target whose suite
  isn't a bare `pytest`. (Structural enabler for real brownfield.)
- **A58** (`8e1d0cc`) — engineer-path merge failures now route to the Janitor
  (closed the asymmetry vs the QA path).
- **A59** (`5d9a9e8`) — the Janitor *fully resolves* a merge failure in-loop:
  repair the environment AND re-attempt the merge; on success the BL proceeds
  through QA/scorer; only a genuinely unrepairable failure escalates.
- **A60** (`a4e23e8`) — the crew auto-resolves high-confidence acceptance
  `product_bug` findings (confidence ≥0.90 self-confirms; the dispatched fix
  still clears its full gate before merge; operator rejection always wins).
- **A61** (`b7ab0b9`) — follow-up fixes resolve the **full fix-locus**: the
  engineer gets the verified root-cause dossier and is bound to fix EVERY named
  surface with a deterministic test; its existing no-abort gate loop then *is*
  the re-verify-and-iterate mechanism (can't merge until all surfaces green).
  Design + the rejected alternative (Lever B) recorded in
  `PLAN_acceptance_resolve_loop.md`.

(A56 retrieval warm-up shipped the prior session and is live.)

## Exp-2 (first REAL third-party brownfield: `daya0576/beaverhabits`) — outcome
A real FastAPI+aiosqlite habit-tracker (~8k LOC, BSD-3), wired as a target
(`webapp/backend/repos/beaverhabits` → `~/dev/ai-projects/brownfield-targets/beaverhabits`,
agent_branch `integration`, gate `uv run pytest` + `test_env`). The crew
delivered the **"Rest Days"** feature (3 BLs, all `merged_full`, regression
checkpoint green). Acceptance caught a real half-wired bug (streak rest-aware in
the API but not the UI). After A60+A61, the crew **autonomously resolved the full
locus** — badge AND "Best Streaks" echart both rest-aware via a shared
`core.streak` bridge predicate; feature fully correct (target `integration` @
`72aa22b`, **99 tests green**). This validated A61 live (clean attribution: same
crew + finding; the only change was the A61 capability). See
`EXPERIMENT_beaverhabits_rest_days.md` (its §Results is still a stub — optional
to fill).

## THE FRONTIER — your next meaningful CREW improvement (decide + build, don't ask)
The worker-loop and **self-resolution** are now well-built (this session capped
them: the crew resolves merge failures and acceptance findings autonomously). Per
the project evaluation, that is ~the "right 40%". **The mission's unbuilt
majority is the CUMULATIVE property — the crew learning across runs/targets (the
"crew brain").** Recommended next move, framed as crew gain:

- **PRIMARY (highest leverage): advance cumulative learning.** ABL-0016 Stage 1
  (lessons-as-context) is shipped **flag-OFF** and needs a calibration smoke to
  flip ON; then ABL-0017 Stage 2 (closed-loop doctrine efficacy). See
  `CUMULATIVE_LEARNING_ROADMAP.md`, `ABL-0016_LESSONS_AS_CONTEXT.md`,
  `ABL-0017_DOCTRINE_EFFICACY.md`. This is the crew getting *cumulative* — the
  last unbuilt mission property.

Concrete smaller general crew-hardening candidates (if you want a bounded win
first):
- **A56 warm-up is non-adaptive on cold targets.** Every Exp-2 run logged
  `retrieval_warmup.timeout` (3×25s) on a freshly-indexed target — the PO still
  grounds (the failed probes warm the stack as a side effect) but the telemetry
  lies and a slower host could still race. General gain: reliable first-agent
  grounding on ANY fresh target (adaptive/longer cold-start probe).
- **Gate diff-on-quiet output.** The regression checkpoint goes green-by-exit-
  code (not by-diff) on `-q` suites — a general gate-honesty gap (prior-session
  candidate; doctrine-meta already proposed a `collected N` assertion).

Whatever you pick: it must be a GENERAL crew capability. If you find yourself
patching beaverhabits specifically, stop and ask "what class does this represent,
and what general capability closes it?"

## Honest caveats / open
- **Irreducible limit (documented, not closable by code):** A61 binds the crew to
  every surface the acceptance agent *names* in its dossier. A surface it never
  identifies still won't be caught — bounded by LLM verifier coverage. Mitigated
  by the acceptance SKILLS' verified-dossier mandate + the full-suite regression
  checkpoint; do not pretend it's a guarantee.
- Exp-2 is **n=1** for substrate realism; strong signal, not proof across targets.
- `PLAN_acceptance_resolve_loop.md` records why Lever B (acceptance re-run loop)
  was rejected (defeated by the `finding_id` collapse). Don't rebuild it.

---PROMPT END---
