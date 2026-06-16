# Continuation prompt — paste into the next Claude Code session

> Hand-off written 2026-06-16 (evening). Supersedes all prior hand-offs.
> **Headline: the Contract-First Decomposition program (Phases A–E + convention
> tightening + cross-layer DI) is COMPLETE and LIVE-PROVEN over 4 sprints on the C#
> ecommerce target. `contract_first` is now DEFAULT ON, gated to .NET targets. Nothing
> is in flight; harness idle; target pristine; dev≡main≡origin @ `b4e3885`.**

---PROMPT START---

You are the **architect** of agentic-skills. Read `CLAUDE.md` + `THESIS.md` first. Mission:
a fully autonomous AI crew that ships complex features into real brownfield repos with no
human — grounded, self-correcting, honest, cumulative, **and parallel like a real team**
(the Contract-First line, now shipped). Honor `.claude/memory/` (start with `MEMORY.md`).

## BINDING WORKFLOW DIRECTIVES (operator) — still in force
1. **REMOTE-FIRST.** ALL crew/harness code (`webapp/`, `langgraph_engine/`, `skills/`,
   `rubrics/`, tests) is edited AND tested on the remote `192.168.12.180`
   (`user@`, key `~/.ssh/id_ed25519_18012`), then synced **remote → GitHub → Mac**
   (Mac = read-only mirror: `git fetch && git reset --hard origin/development`). Your
   Edit/Write target the Mac FS, so remote code edits go over SSH. See
   `.claude/memory/feedback_remote_first_dev.md`.
2. **95% verified confidence before ANY claim.** Verify against a re-openable artifact.
   Unit-green is NOT enough for live behavior — LIVE-prove (this session's proofs caught
   4 real bugs unit tests could not).
3. **SSH gotchas (each bit me):**
   - Apostrophes/`{}`/unicode in a payload break a single-quoted `ssh '...'` heredoc →
     **write the edit/payload to a LOCAL file, `base64 | ssh 'base64 -d > f'`, verify byte
     count, then run it.** This is the reliable remote-edit pattern used all session.
   - Engineer/PO prompt blocks that are **f-strings** need C# `{`/`}` doubled to `{{`/`}}`.
   - **Restart the remote harness with a LOGIN shell** so `claude`/`dotnet` resolve on PATH:
     `setsid bash -lc ".venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > ~/harness.log 2>&1" < /dev/null & disown`. A non-login `bash -c` drops
     `~/.local/bin` → `claude` FileNotFoundError → run aborts. uvicorn has **no hot-reload**:
     after deploying code edits you MUST restart the harness to load them.
   - Long loops over SSH get auto-backgrounded by the tool; use `run_in_background` for the
     run-monitor and read its output file.

## VERIFIED CURRENT STATE (checked 2026-06-16 ~22:00 UTC)
- **Git, Mac ≡ remote ≡ origin/GitHub:** `development` = `main` = **`b4e3885`** (clean).
- **Remote harness:** uvicorn `127.0.0.1:8000`, **pid 4059072** (DRIFTS on restart — re-check
  `lsof -tnP -iTCP:8000 -sTCP:LISTEN`), login-shell PATH, openapi 200, code at `b4e3885`.
  **NO run in flight — idle.**
- **Services:** Ollama (bge-m3, :11434, 200). Milvus (:19530) + `ecommerce-pg` (:5433) are up
  via Docker (host `lsof` won't show docker-proxy ports — don't be alarmed; all 4 proofs
  grounded + booted the DB fine).
- **Target `fullstack-ecommerce-app`:** branch `integration` = `main` = **`00635f3`** (PRISTINE
  — reset for handoff), 0 agent branches, baseline index marker present (fast incremental
  `index_initial`). `.agentic-skills.json`: agent_branch=integration, main_ref=main, full
  `app_boot` (backend :5096 + frontend :5173), `test_cmd`=`dotnet test backend/Ecommerce.sln`.

## ★ WHAT SHIPPED THIS SESSION — Contract-First Decomposition Phases A–E + hardening
The parallel executor (`wave_execution`+`wave_concurrency`) existed but was STARVED (PO
decomposed serial layer-chains → width-1 waves). This session built + LIVE-PROVED the full
contract-first program so slices fan out and build concurrently against the contract + mocks.
Plan: `CONTRACT_FIRST_PHASE2_4_PLAN.md`. Memory: `arch_contract_first_phase2_4.md`.
- **`[x]` Phase A** (`f0315ca`) keystone — `backlog.contract_report(contract_first=)`: a
  contract-satisfied `Consumes` no longer forces a producer `Dependency` edge → DAG fans out.
- **`[x]` Phase B** (`8bbcefe`) — `backlog.dag_width` fan-out metric + `fanout_advisory` +
  PO contract-first decomposition doctrine (`po_contract_instruction`).
- **`[x]` Phase C** (`e868f54`) — per-BL engineer builds against stubs, MOCKS unmerged
  collaborators (`_engineer_contract_block`); threaded through `_engineer_flow`.
- **`[x]` Phase D** (`03b07e8`) — barrier BINDING (`contract_bind.py` pure core +
  `orchestrator._contract_bind`): compose real DI modules, drop stubs, regen aggregator,
  `dotnet build`, no-abort escalate.
- **`[x]` Phase E** (`72db4cb`) live proof #1 (catalog-extras-cf, single-interface) — full
  pipeline + acceptance self-heal → integrity_ok. (Found+fixed: login-shell PATH; missing
  `import subprocess` in `_contract_bind`.)
- **`[x]` Convention tightening** (`084dd8b`) — proof #2 (analytics-stats-cf, dual-interface)
  surfaced both slices editing shared `Program.cs` → `escalated_assembly_conflict`. Fix:
  slices OVERWRITE own `<X>Module.cs` in place, MUST NOT touch Program.cs/aggregator/.sln;
  materializer owns the single `AddFeatureModules()`; PO forbids shared composition root.
- **`[x]` Proof #3** (`df7e63`) dual-interface — clean: 0 conflict, 2 real modules bound,
  integrity_ok. Surfaced cross-layer residual (a slice still added 1 repo line to Program.cs).
- **`[x]` Cross-layer fix** (`77edfcf`) — materializer places modules + aggregator in the
  composition-root/host project (refs every layer) so a slice registers its FULL chain
  (service + Infra repos) in its OWN module.
- **`[x]` Proof #4** (`71e4bf`, catalog-insights-cf, two cross-layer slices) — CLEAN:
  dag_width=2, both merged_full, 0 conflict, **contract_bind 2 real**, **Program.cs touched
  by exactly 1 commit (materializer only)**, integrity_ok first pass. Residual CLOSED.
- **`[x]` Flag flipped DEFAULT ON** (`b4e3885`) — router + `run_brief` defaults True, **gated
  to .NET targets** via `orchestrator._is_dotnet_target` (forces OFF on non-.NET so those runs
  stay byte-identical; the materializer/binder are C#/`dotnet`-specific). 624 tests pass.

## OPEN FOLLOW-UPS (non-blocking)
1. **Generalize the contract materializer + binder beyond C#/`dotnet`** so contract-first can
   default-ON for non-.NET targets too (today it's gated OFF on them). This is the main
   extension to make "parallel like a real team" universal.
2. Calibration: contract-first is proven on ONE target (C# ecommerce, 4 runs). Exercise on a
   harder feature / second .NET target before trusting it broadly.
3. R21 PO-markdown parser hardening (backticks / inline `**Field:**` / `·`,`/`,`+` joins) — cuts
   PO doctrine retries (`backlog._contract_tokens`).
4. Optional: a `wave_concurrency=1` byte-identical regression test; disk-preflight scaling by k.

## HONEST LEDGER
`[x]` Contract-First A–E + tightening + cross-layer COMPLETE + LIVE-PROVEN (4 sprints) ·
`[x]` `contract_first` DEFAULT ON gated to .NET (`_is_dotnet_target`) · `[x]` 624 tests green
on remote · `[x]` dev≡main≡origin @ `b4e3885`, target pristine, harness idle ·
`[ ]` generalize materializer/binder to non-C# (open) · `[ ]` 2nd-target calibration (open).

---PROMPT END---
