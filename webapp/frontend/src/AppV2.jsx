import React, { useEffect, useRef, useState } from "react";
import { streamPost } from "./sse.js";

const API = ""; // same-origin

/**
 * AppV2 — ABL-0001 Orchestrator UI.
 *
 * Operator submits a brief; backend's /run-brief drives the full pipeline
 * (index → PO → loop(engineer → reindex → QA → reindex → scorer)) and emits
 * SSE events. This UI renders a live vertical timeline of stages, with a
 * per-BL nested timeline once the backlog is parsed.
 */
export function AppV2() {
  const [repos, setRepos] = useState([]);
  const [repo, setRepo] = useState("full-stack-fastapi-template");
  const [featureName, setFeatureName] = useState("");
  const [brief, setBrief] = useState("");
  const [maxBls, setMaxBls] = useState("");
  const [skipPo, setSkipPo] = useState(false);
  // ABL-0014 — DEFAULT ON (2026-05-31, after 3 clean calibration smokes).
  const [runAcceptance, setRunAcceptance] = useState(true);
  // ABL-0014 §I.3 Batch E — inject classifier-accuracy priors from the
  // findings ledger into the acceptance agent's spawn prompt. Default OFF
  // until the 3-smoke calibration discipline (§I.1) clears the flip;
  // mirrors the run_acceptance default-OFF→ON history.
  const [injectAcceptancePriors, setInjectAcceptancePriors] = useState(false);
  // ABL-0015 — auto-dispatch a follow-up engineer INLINE during the sprint on
  // operator-pre-confirmed product_bug findings. Default OFF (highest-risk
  // action). The on-demand "Dispatch fix" button needs no flag; this only
  // matters when re-running a sprint whose findings are already confirmed.
  const [runAcceptanceFollowup, setRunAcceptanceFollowup] = useState(false);
  // ABL-0016 — surface prior operator-confirmed lessons to the brownfield
  // roles (advisory, target-scoped). Default OFF until calibration.
  const [injectLessons, setInjectLessons] = useState(false);
  // ABL-0014 — last acceptance.done/skipped/error event, surfaced as a tile.
  const [acceptance, setAcceptance] = useState(null);
  // ABL-0014 Item 2 (Batch C/D, 2026-06-01) — UI-coverage breakdown from
  // orchestrator.coverage_check event; surfaced as its own tile.
  const [coverage, setCoverage] = useState(null);
  // ABL-0014 Item 2 Batch D — operator-tunable UI-coverage floor. 0.0
  // (default) is informational-only; any positive value will surface
  // sprint_complete as "partial" when the actual ratio falls short.
  const [minUiCoverageRatio, setMinUiCoverageRatio] = useState("0.0");
  const [running, setRunning] = useState(false);
  const [endingSprint, setEndingSprint] = useState(false);
  const [stages, setStages] = useState(initialStages());
  const [bls, setBls] = useState([]); // {id, title, deps, steps:{engineer, reindex_e, qa, reindex_q, scorer}, outcome}
  const [events, setEvents] = useState([]);
  const [detail, setDetail] = useState(null);
  // ABL-0014 §I.3 Batch D — when an acceptance tile is open in the rail,
  // default the rail to the FindingsTriagePanel (operator-facing) and
  // let the user toggle to raw JSON for deep debugging.
  const [showRawDetail, setShowRawDetail] = useState(false);
  // Unmerged agent/* branches — the anomaly-resolution surface. A BL or a
  // follow-up dispatch whose gate did not auto-merge leaves its branch here;
  // the operator reviews & merges it without leaving the UI (GET /branches).
  const [branches, setBranches] = useState(null); // { agent_branch, unmerged:[{branch,sha,when}] }
  const abortRef = useRef(null);
  const logEndRef = useRef(null);
  // Init-feature bootstrap state
  const [initStatus, setInitStatus] = useState(null); // null | "pending" | "ok" | "error"
  const [initResult, setInitResult] = useState(null); // { slug, agent_branch, branch_sha, requirements_path }
  const [initError, setInitError] = useState(null);

  useEffect(() => {
    fetch(`${API}/api/projects`).then((r) => (r.ok ? r.json() : { items: [] }))
      .then((d) => {
        const items = (d.items || d.repos || []).map((x) => (typeof x === "string" ? x : x.name));
        setRepos(items);
        if (items.length && !repo) setRepo(items[0]);
      })
      .catch(() => {
        // fallback: probe the known target
        setRepos(["full-stack-fastapi-template"]);
        setRepo("full-stack-fastapi-template");
      });
  }, []);

  useEffect(() => {
    if (logEndRef.current) logEndRef.current.scrollIntoView({ block: "end" });
  }, [events.length]);

  // Refresh the unmerged-branch list (anomaly surface). Called on repo change
  // and after a run finishes — a gate that didn't auto-merge surfaces here.
  async function reloadBranches() {
    if (!repo) return;
    try {
      const r = await fetch(`${API}/api/projects/${encodeURIComponent(repo)}/branches`);
      if (!r.ok) return;
      setBranches(await r.json());
    } catch { /* non-fatal: the panel has its own refresh */ }
  }

  useEffect(() => {
    reloadBranches();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repo]);

  function initialStages() {
    return {
      preflight:        { label: "Preflight",                     status: "pending" },
      index_initial:    { label: "Initial index (claude-context + graphify)", status: "pending" },
      po:               { label: "PO — decompose brief",          status: "pending" },
      backlog_parsed:   { label: "Backlog parsed",                status: "pending" },
      // per-BL phases pushed into `bls`
      sprint_complete:  { label: "Sprint complete",               status: "pending" },
    };
  }

  function resetState() {
    setStages(initialStages());
    setBls([]);
    setEvents([]);
    setDetail(null);
    setAcceptance(null);
    setCoverage(null);
  }

  function setStage(key, patch) {
    setStages((s) => ({ ...s, [key]: { ...(s[key] || {}), ...patch } }));
  }

  function upsertBl(id, patch) {
    setBls((prev) => {
      const i = prev.findIndex((b) => b.id === id);
      if (i === -1) return [...prev, { id, title: "", steps: {}, ...patch }];
      const next = [...prev];
      next[i] = { ...next[i], ...patch, steps: { ...next[i].steps, ...(patch.steps || {}) } };
      return next;
    });
  }

  function setBlStep(id, step, patch) {
    setBls((prev) => {
      const i = prev.findIndex((b) => b.id === id);
      if (i === -1) return [...prev, { id, title: "", steps: { [step]: patch } }];
      const next = [...prev];
      next[i] = { ...next[i], steps: { ...next[i].steps, [step]: { ...(next[i].steps[step] || {}), ...patch } } };
      return next;
    });
  }

  function ingest(evt) {
    setEvents((es) => (es.length > 2000 ? [...es.slice(-2000), evt] : [...es, evt]));
    const phase = evt.phase || "";
    const blId = evt.bl_id;
    const step = evt.orchestrator_step;

    // top-level orchestrator phases
    if (phase.startsWith("orchestrator.")) {
      const key = phase.slice("orchestrator.".length);
      if (key === "start") {
        setStage("preflight", { status: "done", detail: { run_id: evt.run_id } });
        return;
      }
      if (key === "index_initial.start") { setStage("index_initial", { status: "running" }); return; }
      if (key === "index_initial.done") {
        setStage("index_initial", { status: "done", detail: { cc: evt.claude_context, gr: evt.graphify } });
        return;
      }
      if (key === "po.start") { setStage("po", { status: "running" }); return; }
      if (key === "po.done") { setStage("po", { status: evt.ok ? "done" : "failed" }); return; }
      if (key === "backlog_parsed") {
        setStage("backlog_parsed", { status: "done", detail: { count: evt.count } });
        setBls((evt.bls || []).map((b) => ({ id: b.id, title: b.title, deps: b.deps, steps: {}, status: "pending" })));
        return;
      }
      if (key === "bl.start") { upsertBl(blId, { status: "running", title: evt.title }); return; }
      // B4: bl.done outcome may be merged_full / merged_no_qa / merged_no_score /
      // no_op / engineer_unmerged / merged (legacy). All flow into b.outcome
      // for the badge; BlRow color-codes via outcomeClass below.
      if (key === "bl.done") {
        const failed = ["engineer_unmerged"].includes(evt.outcome);
        const warned = ["merged_no_qa", "merged_no_score"].includes(evt.outcome);
        upsertBl(blId, {
          status: failed ? "failed" : (warned ? "warned" : "done"),
          outcome: evt.outcome,
        });
        return;
      }
      // A4: backfill-mode skip — BL was passed-over because start_bl pointed elsewhere.
      if (key === "bl.skipped") {
        upsertBl(blId, { status: "skipped", outcome: "skipped", skip_reason: evt.reason });
        return;
      }
      // B12: partial_resume — engineer no_op but QA missing/uncommitted; record
      // the reason on the BL row so operator sees the resume path was taken.
      if (key === "partial_resume") {
        upsertBl(blId, { partial_resume: true, partial_resume_reason: evt.reason });
        return;
      }
      // A2: QA gave up on doctrine — distinct from "qa.done failed" because
      // the doctrine validator's `summary` carries diagnostic detail.
      if (key === "qa_doctrine_failed") {
        setBlStep(blId, "qa", {
          status: "failed",
          doctrine_failed: true,
          doctrine_summary: evt.summary,
        });
        return;
      }
      if (key.startsWith("engineer.")) {
        const sub = key.slice("engineer.".length);
        if (sub === "start") setBlStep(blId, "engineer", { status: "running" });
        else if (sub === "done") setBlStep(blId, "engineer", { status: evt.merged ? "done" : (evt.no_op ? "no_op" : "failed"), merged: evt.merged, no_op: evt.no_op });
        return;
      }
      if (key.startsWith("qa.")) {
        const sub = key.slice("qa.".length);
        if (sub === "start") setBlStep(blId, "qa", { status: "running" });
        else if (sub === "done") setBlStep(blId, "qa", { status: evt.merged ? "done" : "failed", merged: evt.merged });
        return;
      }
      if (key.startsWith("scorer.")) {
        const sub = key.slice("scorer.".length);
        if (sub === "start") setBlStep(blId, "scorer", { status: "running" });
        else if (sub === "done") setBlStep(blId, "scorer", { status: evt.doctrine_ok ? "done" : "failed" });
        return;
      }
      if (key.startsWith("reindex_after_engineer")) {
        const blFromKey = key.split(".")[1];
        const done = key.endsWith(".done");
        setBlStep(blFromKey, "reindex_e", { status: done ? "done" : "running" });
        return;
      }
      if (key.startsWith("reindex_after_qa")) {
        const blFromKey = key.split(".")[1];
        const done = key.endsWith(".done");
        setBlStep(blFromKey, "reindex_q", { status: done ? "done" : "running" });
        return;
      }
      if (key === "sprint_complete") {
        setStage("sprint_complete", { status: "done", detail: evt.summary });
        // Item 2 Batch C: capture the subtype + ratio on the terminal
        // sprint_complete event (the coverage_check fires just before).
        if (evt.coverage_subtype || typeof evt.ui_coverage_ratio === "number") {
          setCoverage((prev) => ({
            ...(prev || {}),
            subtype: evt.coverage_subtype,
            ratio: evt.ui_coverage_ratio,
            threshold: evt.ui_coverage_threshold,
            terminal: true,
          }));
        }
        return;
      }
      if (key === "coverage_check") {
        // Item 2 Batch C — informational event with the full breakdown.
        setCoverage({
          merged_total: evt.merged_total,
          ui_bls: evt.ui_bls || [],
          backend_only: evt.backend_only || [],
          ratio: evt.ratio,
          threshold: evt.threshold,
          subtype: evt.subtype,
        });
        return;
      }
      if (key === "aborted") {
        setStage("sprint_complete", { status: "failed", detail: evt.reason });
        return;
      }
      // ABL-0014 — acceptance.* event filter. Track the most recent
      // skipped/done/error event so the summary tile reflects terminal state.
      if (key.startsWith("acceptance.")) {
        const sub = key.slice("acceptance.".length);
        if (sub === "skipped" || sub === "done" || sub === "error") {
          setAcceptance((prev) => ({ ...(prev || {}), terminal: sub, ...evt }));
        } else if (sub === "start") {
          setAcceptance({ terminal: "running", ...evt });
        } else if (sub === "archived") {
          setAcceptance((prev) => ({ ...(prev || {}), archive: evt.archive }));
        }
        return;
      }
    }

    // per-role events carrying orchestrator_step + bl_id are reflected as detail
    if (step && blId) {
      const stepKey = step === "qa" ? "qa" : (step === "scorer" ? "scorer" : "engineer");
      // Surface short status from interesting per-role phases
      if (phase === "regression_gate") {
        // A1: regression_gate may carry post_rebase=true (gate re-ran on the
        // freshly-rebased SHA); show it as a distinct badge.
        setBlStep(blId, stepKey, {
          gate_kind: evt.kind,
          gate_ok: evt.ok,
          ...(evt.post_rebase ? { gate_post_rebase: true } : {}),
        });
      }
      // B4: surface merge_to_target failures with their kind + error so the
      // detail rail can show WHY a merge failed (non_ff, error, post-rebase
      // gate failure, etc.).
      if (phase === "merge_to_target" && !evt.ok) {
        setBlStep(blId, stepKey, {
          merge_failed: true,
          merge_kind: evt.kind,
          merge_error: evt.error,
        });
      }
      // A1: the three rebase-recovery phases — render as a small badge cluster
      // on the relevant step so the operator can see the auto-rebase ran.
      if (phase === "merge_rebase_attempt") {
        setBlStep(blId, stepKey, { rebase_attempt: true });
      }
      if (phase === "merge_rebase_succeeded") {
        setBlStep(blId, stepKey, { rebase_succeeded: true });
      }
      if (phase === "merge_rebase_failed") {
        setBlStep(blId, stepKey, { rebase_failed: true, rebase_error: evt.error });
      }
      if (phase === "awaiting_review") {
        setBlStep(blId, stepKey, { awaiting: true, reason: evt.reason });
      }
    }
  }

  async function run() {
    if (!repo || brief.length < 20) return;
    resetState();
    setRunning(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const body = {
        brief,
        project_name: featureName || null,
        max_bls: maxBls ? parseInt(maxBls, 10) : null,
        skip_po: skipPo,
        stop_on_failure: true,
        timeout_per_role: 2400,
        run_acceptance: runAcceptance,
        // ABL-0014 §I.3 Batch E — classifier priors injection (default OFF).
        inject_acceptance_priors: injectAcceptancePriors,
        // ABL-0015 — inline auto-dispatch on pre-confirmed findings (default OFF).
        run_acceptance_followup: runAcceptanceFollowup,
        // ABL-0016 — inject prior confirmed lessons into role prompts (default OFF).
        inject_lessons: injectLessons,
        // ABL-0014 Item 2 Batch D — operator-tunable UI-coverage floor.
        min_ui_coverage_ratio: parseFloat(minUiCoverageRatio) || 0.0,
        // A18: per-feature isolation — server creates
        // <target>/_brownfield/features/<slug>/ and tails events.jsonl there.
        feature_name: featureName || null,
      };
      for await (const evt of streamPost(`${API}/api/projects/${encodeURIComponent(repo)}/run-brief`, body, ctrl.signal)) {
        ingest(evt);
      }
    } catch (e) {
      // B2/B9/A7: the router returns HTTP 409 with structured detail for
      // run-in-progress, duplicate-brief, and orphaned-run-detected. Surface
      // the detail to the detail rail instead of just the bare string.
      const detail = e && e.body && e.body.detail;
      if (detail && typeof detail === "object") {
        ingest({
          type: "_meta",
          phase: "orchestrator.aborted",
          reason: detail.error || "409",
          detail,
        });
      } else {
        ingest({ type: "_error", error: e.message || String(e), phase: "orchestrator.aborted" });
      }
    } finally {
      setRunning(false);
      abortRef.current = null;
      // A BL that failed its gate (engineer_unmerged) leaves an unmerged
      // branch; surface it so the operator can review & merge from the UI.
      reloadBranches();
    }
  }

  function stop() {
    if (abortRef.current) abortRef.current.abort();
  }

  // "End current Sprint": kill the running run (abort the SSE — the orchestrator
  // treats the disconnect as a stop) AND run the backend cleanup sweep
  // (worktrees, docker stacks/volumes, run-scoped images, run-state, lock).
  async function endSprint() {
    if (!repo) return;
    if (!window.confirm(
      "End the current sprint?\n\nThis aborts the running run and reaps its " +
      "worktrees, docker stacks + volumes, run-scoped docker images, and the " +
      "per-repo run lock. The agent branch and merged work are NOT touched."
    )) return;
    if (abortRef.current) abortRef.current.abort();  // kill the run client-side
    setEndingSprint(true);
    try {
      const r = await fetch(`${API}/api/projects/${encodeURIComponent(repo)}/end-sprint`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ purge_images: true }),
      });
      const body = await r.json();
      setDetail({ end_sprint: true, ...body });
      ingest({
        type: "_meta", phase: "orchestrator.ended_by_operator",
        reason: `${(body.worktrees_removed || []).length} worktrees, ` +
                `${(body.stacks_reaped || []).length} stacks, ` +
                `${body.images_removed || 0} images reaped`,
      });
    } catch (e) {
      ingest({ type: "_error", error: `end-sprint failed: ${e.message || String(e)}`,
               phase: "orchestrator.ended_by_operator" });
    } finally {
      setEndingSprint(false);
      setRunning(false);
      reloadBranches();
    }
  }

  return (
    <div className="v2-root">
      <header className="v2-header">
        <h1>Agentic Skills <span className="v2-tag">v2 — Orchestrator</span></h1>
        <a href="?v=1" className="v2-link">switch to v1</a>
      </header>

      <section className="v2-controls">
        <div className="v2-row">
          <label>Target</label>
          <code className="v2-target">{repo}</code>
          {repos.length > 1 && (
            <select value={repo} onChange={(e) => setRepo(e.target.value)} disabled={running}>
              {repos.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          )}
          <label>Max BLs</label>
          <input value={maxBls} onChange={(e) => setMaxBls(e.target.value.replace(/[^0-9]/g, ""))}
                 placeholder="all" style={{ width: 60 }} disabled={running} />
          <label><input type="checkbox" checked={skipPo} onChange={(e) => setSkipPo(e.target.checked)} disabled={running} /> Skip PO (re-run on existing backlog)</label>
          <label title="ABL-0014 — runs the Acceptance Agent after sprint_complete to exercise end-to-end user journeys and produce a report. Default OFF for first 3 calibration sprints (§E.1 Q6)."><input type="checkbox" checked={runAcceptance} onChange={(e) => setRunAcceptance(e.target.checked)} disabled={running} /> Run acceptance pass</label>
          <label title="ABL-0014 §I.3 Batch E — inject classifier-accuracy priors from the findings ledger into the acceptance agent's spawn prompt. Default OFF until §I.1 3-smoke calibration clears the flip."><input type="checkbox" checked={injectAcceptancePriors} onChange={(e) => setInjectAcceptancePriors(e.target.checked)} disabled={running || !runAcceptance} /> Inject priors</label>
          <label title="ABL-0015 — auto-dispatch a follow-up engineer INLINE during the sprint on operator-pre-confirmed product_bug findings. Default OFF (highest-risk action). The on-demand 'Dispatch fix' button needs no flag; this mainly matters on a re-run whose findings are already confirmed."><input type="checkbox" checked={runAcceptanceFollowup} onChange={(e) => setRunAcceptanceFollowup(e.target.checked)} disabled={running || !runAcceptance} /> Auto-dispatch followups</label>
          <label title="ABL-0016 — surface prior operator-confirmed lessons to the brownfield roles (advisory, target-scoped). Default OFF until calibration."><input type="checkbox" checked={injectLessons} onChange={(e) => setInjectLessons(e.target.checked)} disabled={running} /> Inject lessons</label>
          <label title="ABL-0014 Item 2 (Batch C) — minimum fraction of merged BLs that must touch UI for sprint_complete to surface as 'full'. 0.0 = informational only (no partial flag ever); 0.5 = at least half the merged BLs must have UI surface; 1.0 = every merged BL must touch UI. Operator-visibility only — sprint still completes either way.">
            UI cov ≥
            <input
              value={minUiCoverageRatio}
              onChange={(e) => setMinUiCoverageRatio(e.target.value.replace(/[^0-9.]/g, ""))}
              placeholder="0.0"
              style={{ width: 50, marginLeft: 4 }}
              disabled={running}
            />
          </label>
        </div>
        <div className="v2-row">
          <label>Feature name</label>
          <input
            value={featureName}
            onChange={(e) => { setFeatureName(e.target.value); setInitStatus(null); setInitResult(null); setInitError(null); }}
            placeholder="audit-log, rbac, multi-tenant-workspaces …"
            style={{ flex: 1, minWidth: 240 }}
            disabled={running || initStatus === "pending"}
          />
          <button
            onClick={async () => {
              setInitStatus("pending"); setInitError(null); setInitResult(null);
              try {
                const r = await fetch(`${API}/api/projects/${encodeURIComponent(repo)}/init-feature`, {
                  method: "POST", headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ feature_name: featureName }),
                });
                const body = await r.json();
                if (!r.ok) { setInitStatus("error"); setInitError(body.detail || body); return; }
                setInitStatus("ok"); setInitResult(body);
              } catch (e) { setInitStatus("error"); setInitError({ error: e.message }); }
            }}
            disabled={running || initStatus === "pending" || featureName.trim().length < 2 || !repo}
            className="v2-secondary"
            title="Fork a clean-baseline branch from master and apply the harness (gitignore, regression_gate.sh, compose.gate.yml, .agentic-skills.json). Required only for an UNRELATED new feature."
          >
            {initStatus === "pending" ? "Initializing…" : "Start clean baseline"}
          </button>
        </div>
        {initStatus === "ok" && initResult && (
          <div className="v2-row" style={{ background: "#1f3b1f", padding: "8px 12px", borderRadius: 4, fontSize: 13 }}>
            ✅ Branch <code>{initResult.agent_branch}</code> forked from <code>{initResult.main_ref}</code> @ <code>{initResult.branch_sha.slice(0,8)}</code>.
            Drop REQUIREMENTS.md at <code>{initResult.requirements_path}</code> (optional — you can also just paste the brief below).
          </div>
        )}
        {initStatus === "error" && initError && (
          <div className="v2-row" style={{ background: "#3b1f1f", padding: "8px 12px", borderRadius: 4, fontSize: 13 }}>
            ❌ init-feature failed: <code>{initError.error || "unknown"}</code> {initError.message ? `— ${initError.message}` : ""}
          </div>
        )}
        <textarea
          className="v2-brief"
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          placeholder="Full description of the feature. Min 20 characters. E.g. 'Add multi-tenant collaboration with workspaces, invitations, and per-workspace task lists. Keep backwards-compat with existing single-user routes.'"
          rows={8}
          disabled={running}
        />
        <div className="v2-row">
          <button onClick={run}
                  disabled={running || brief.length < 20 || !repo || featureName.trim().length < 2}
                  className="v2-primary">
            {running ? "Running…" : "Run pipeline"}
          </button>
          <button onClick={stop} disabled={!running} className="v2-secondary">Stop</button>
          <button
            onClick={endSprint}
            disabled={endingSprint}
            className="v2-secondary"
            title="Kill the running sprint AND clean up: reap worktrees, docker stacks + volumes, purge run-scoped images, archive run-state, clear the run lock. Safe to click even when idle (cleanup-only)."
          >
            {endingSprint ? "Ending…" : "⛔ End current Sprint"}
          </button>
          <span className="v2-status">{running ? "● live" : "○ idle"}</span>
        </div>
      </section>

      <section className="v2-body">
        <div className="v2-timeline">
          <h2>Pipeline</h2>
          {Object.entries(stages).map(([key, st]) => (
            <StageRow key={key} k={key} st={st} onClick={() => setDetail({ stage: key, ...st })} />
          ))}
          {bls.length > 0 && (
            <div className="v2-bls">
              <h3>Backlog ({bls.length})</h3>
              {bls.map((b) => <BlRow key={b.id} b={b} onClick={(s) => setDetail({ bl: b.id, step: s, ...b })} />)}
            </div>
          )}
          {acceptance && (
            <div
              className="v2-acceptance-tile"
              style={{
                marginTop: 12, padding: 12, borderRadius: 6,
                background: acceptance.terminal === "done"
                  ? (acceptance.validator_ok ? "#1f3b1f" : "#3b2f1f")
                  : acceptance.terminal === "error" ? "#3b1f1f"
                  : acceptance.terminal === "skipped" ? "#2a2a2a"
                  : "#1f2a3b",
                cursor: "pointer", fontSize: 13,
              }}
              onClick={() => setDetail({ acceptance: true, ...acceptance })}
              title="ABL-0014 Acceptance pass — click for full event detail"
            >
              <strong>Acceptance ({acceptance.terminal})</strong>
              {acceptance.terminal === "done" && (
                <> · validator_ok={String(acceptance.validator_ok)} · attempts={acceptance.attempts}</>
              )}
              {acceptance.terminal === "skipped" && <> · reason={acceptance.reason}</>}
              {acceptance.terminal === "error" && <> · {acceptance.error}</>}
              {Array.isArray(acceptance.backend_bls) && acceptance.backend_bls.length > 0 && (
                <div style={{ marginTop: 4, opacity: 0.85, fontSize: 12 }}>
                  API coverage: {acceptance.backend_bls.length} backend BL{acceptance.backend_bls.length === 1 ? "" : "s"} ({acceptance.backend_bls.join(", ")})
                </div>
              )}
              {/* ABL-0014 §I.3 Batch B+D — findings count from the ledger. */}
              {typeof acceptance.findings_persisted === "number" && (
                <div style={{ marginTop: 4, opacity: 0.85, fontSize: 12 }}>
                  Findings: {acceptance.findings_persisted}
                  {acceptance.findings_persisted > 0 && " · click tile → triage panel"}
                </div>
              )}
              {acceptance.archive && (
                <div style={{ marginTop: 4, opacity: 0.8, fontFamily: "monospace", fontSize: 11 }}>
                  archive: {acceptance.archive}
                </div>
              )}
            </div>
          )}
          {coverage && typeof coverage.ratio === "number" && (
            <div
              className="v2-coverage-tile"
              style={{
                marginTop: 12, padding: 12, borderRadius: 6,
                background: coverage.subtype === "partial" ? "#3b2f1f" : "#1f3b3b",
                cursor: "pointer", fontSize: 13,
              }}
              onClick={() => setDetail({ coverage: true, ...coverage })}
              title="ABL-0014 Item 2 — UI-coverage breakdown. Click for full detail."
            >
              <strong>UI Coverage ({coverage.subtype || "full"})</strong>
              {" · ratio="}{(coverage.ratio).toFixed(2)}
              {typeof coverage.threshold === "number" && coverage.threshold > 0 && (
                <> · threshold={coverage.threshold.toFixed(2)}</>
              )}
              {typeof coverage.merged_total === "number" && (
                <> · {coverage.ui_bls ? coverage.ui_bls.length : 0}/{coverage.merged_total} BLs touch UI</>
              )}
              {Array.isArray(coverage.backend_only) && coverage.backend_only.length > 0 && (
                <div style={{ marginTop: 4, opacity: 0.85, fontSize: 12 }}>
                  Backend-only BLs ({coverage.backend_only.length}): {coverage.backend_only.join(", ")}
                </div>
              )}
            </div>
          )}
          {/* Anomaly surface: agent/* branches whose gate did not auto-merge
              (a failed-gate BL, or a follow-up dispatch that came back
              not_merged). Operator resolves them in-place via the rail. */}
          {branches && Array.isArray(branches.unmerged) && branches.unmerged.length > 0 && (
            <div
              className="v2-branches-tile"
              style={{
                marginTop: 12, padding: 12, borderRadius: 6,
                background: "#3b2f1f", cursor: "pointer", fontSize: 13,
              }}
              onClick={() => setDetail({ branches: true })}
              title="Agent branches not yet merged into the agent branch — review & merge here."
            >
              <strong>⚠ Unmerged branches ({branches.unmerged.length})</strong>
              <div style={{ marginTop: 4, opacity: 0.85, fontSize: 12 }}>
                into <code>{branches.agent_branch}</code> · click → review &amp; merge
              </div>
            </div>
          )}
        </div>

        <div className="v2-rail">
          <h2>
            Detail
            {/* ABL-0014 §I.3 Batch D — when the acceptance tile is open
                and has a feature_slug, default the rail to the
                FindingsTriagePanel; let the user toggle to raw JSON. */}
            {detail?.acceptance && detail?.feature_slug && (
              <button
                onClick={() => setShowRawDetail((v) => !v)}
                className="v2-secondary"
                style={{ marginLeft: 12, fontSize: 11, padding: "2px 8px" }}
                title="Toggle between the findings triage panel and the raw event JSON."
              >
                {showRawDetail ? "Show triage panel" : "Show raw JSON"}
              </button>
            )}
          </h2>
          {detail?.branches ? (
            <BranchesPanel repo={repo} onChanged={reloadBranches} />
          ) : detail?.acceptance && detail?.feature_slug && !showRawDetail ? (
            <FindingsTriagePanel repo={repo} featureSlug={detail.feature_slug} onMerged={reloadBranches} />
          ) : (
            <pre className="v2-detail">{detail ? JSON.stringify(detail, null, 2) : "Click a stage or BL step to inspect."}</pre>
          )}
        </div>
      </section>

      <details className="v2-log">
        <summary>Event log ({events.length})</summary>
        <div className="v2-log-body">
          {events.slice(-200).map((e, i) => (
            <div
              key={i}
              className="v2-log-line"
              style={{ cursor: "pointer" }}
              title="click → full event (all attributes) in the Detail rail"
              onClick={() => setDetail({ event: true, ...e })}
            >
              <span className="v2-log-phase">{eventLabel(e)}</span>
              {e.bl_id ? <span className="v2-log-bl">{e.bl_id}</span> : null}
              <span className="v2-log-text">{eventDetail(e)}</span>
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      </details>
    </div>
  );
}

function StageRow({ k, st, onClick }) {
  return (
    <div className={`v2-stage v2-${st.status || "pending"}`} onClick={onClick}>
      <span className="v2-dot" />
      <span className="v2-stage-label">{st.label || k}</span>
      <span className="v2-stage-status">{st.status || "pending"}</span>
    </div>
  );
}

function BlRow({ b, onClick }) {
  const steps = ["engineer", "reindex_e", "qa", "reindex_q", "scorer"];
  // B4: outcome→visual-class map for the truthful outcome labels from A5.
  const outcomeClass = (() => {
    switch (b.outcome) {
      case "merged_full":    return "v2-outcome-ok";
      case "merged":         return "v2-outcome-ok"; // legacy
      case "no_op":          return "v2-outcome-noop";
      case "merged_no_qa":   return "v2-outcome-warn";
      case "merged_no_score":return "v2-outcome-warn";
      case "engineer_unmerged": return "v2-outcome-fail";
      case "skipped":        return "v2-outcome-skipped";
      default:               return "";
    }
  })();
  return (
    <div className={`v2-bl v2-${b.status || "pending"}`}>
      <div className="v2-bl-head" onClick={() => onClick("")}>
        <strong>{b.id}</strong> <span className="v2-bl-title">{b.title}</span>
        <span className={`v2-bl-outcome ${outcomeClass}`}>{b.outcome || b.status || "pending"}</span>
        {b.partial_resume ? <span className="v2-tag-sm" title={b.partial_resume_reason}>resume</span> : null}
      </div>
      <div className="v2-bl-steps">
        {steps.map((s) => {
          const st = b.steps[s] || {};
          return (
            <div key={s} className={`v2-sub v2-${st.status || "pending"}`} onClick={() => onClick(s)}>
              <span className="v2-dot v2-dot-sm" />
              <span>{s}</span>
              {st.gate_kind ? <span className="v2-tag-sm">{st.gate_kind}</span> : null}
              {st.gate_post_rebase ? <span className="v2-tag-sm" title="gate re-ran after auto-rebase">post-rebase</span> : null}
              {st.no_op ? <span className="v2-tag-sm">no-op</span> : null}
              {st.awaiting ? <span className="v2-tag-sm">awaiting</span> : null}
              {st.doctrine_failed ? <span className="v2-tag-sm v2-tag-fail" title={st.doctrine_summary || ""}>doctrine-fail</span> : null}
              {st.rebase_attempt && !st.rebase_succeeded && !st.rebase_failed ? <span className="v2-tag-sm">rebasing</span> : null}
              {st.rebase_succeeded ? <span className="v2-tag-sm">rebased</span> : null}
              {st.rebase_failed ? <span className="v2-tag-sm v2-tag-fail" title={st.rebase_error || ""}>rebase-fail</span> : null}
              {st.merge_failed ? <span className="v2-tag-sm v2-tag-fail" title={st.merge_error || ""}>{st.merge_kind || "merge-fail"}</span> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function shortDesc(e) {
  if (e.type === "_error") return `${e.kind ? e.kind + ": " : ""}${e.error}`;
  if (e.phase === "orchestrator.start") return e.run_id || "";
  if (e.phase === "orchestrator.backlog_parsed") return `${e.count} BLs`;
  if (e.phase === "orchestrator.bl.done") return `outcome=${e.outcome}`;
  if (e.phase === "orchestrator.bl.skipped") return e.reason || "";
  if (e.phase === "orchestrator.partial_resume") return (e.reason || "").slice(0, 80);
  if (e.phase === "orchestrator.qa_doctrine_failed") return `${e.bl_id} — give up`;
  if (e.phase === "orchestrator.aborted") return e.reason || (e.detail && e.detail.error) || "";
  if (e.phase === "regression_gate") return `gate=${e.kind} ok=${e.ok}${e.post_rebase ? " (post-rebase)" : ""}`;
  if (e.phase === "merge_to_target") return `merged=${e.ok}${e.kind ? ` kind=${e.kind}` : ""}`;
  if (e.phase === "merge_rebase_attempt") return `→ ${e.target_ref}`;
  if (e.phase === "merge_rebase_succeeded") return "rebased ok";
  if (e.phase === "merge_rebase_failed") return (e.error || "").slice(0, 80);
  if (e.phase === "doctrine_check") return `${e.kind} attempts=${e.attempts ?? e.attempt ?? "?"}`;
  if (e.phase === "worktree_ready") return e.role || "";
  if (e.summary) return typeof e.summary === "string" ? e.summary.slice(0, 80) : "";
  return "";
}

// Richer one-line detail for the event log. shortDesc() covers orchestrator
// _meta/role phases; this also unpacks the agent stream-json events
// (assistant/user/system/result) the agent subprocess emits, so the log shows
// WHAT each agent did (tool calls, text, results) — not just the role.
function eventDetail(e) {
  const sd = shortDesc(e);
  if (sd) return sd;
  if (e.type === "assistant" && e.message?.content) {
    const parts = e.message.content.map((c) => {
      if (c.type === "text") return "💬 " + (c.text || "").trim().replace(/\s+/g, " ").slice(0, 110);
      if (c.type === "thinking") return "💭 thinking";
      if (c.type === "tool_use") {
        const inp = c.input || {};
        const arg = inp.command || inp.file_path || inp.path || inp.pattern
                  || inp.query || (inp.prompt ? String(inp.prompt).slice(0, 50) : "");
        return "🔧 " + (c.name || "?") + (arg ? " " + String(arg).slice(0, 80) : "");
      }
      return c.type;
    }).filter(Boolean);
    return parts.join(" · ");
  }
  if (e.type === "user" && e.message?.content) {
    const tr = e.message.content.find((c) => c.type === "tool_result");
    if (tr) {
      const body = typeof tr.content === "string" ? tr.content
                 : Array.isArray(tr.content) ? tr.content.map((x) => x.text || "").join(" ")
                 : JSON.stringify(tr.content);
      return (tr.is_error ? "⚠ " : "← ") + String(body).replace(/\s+/g, " ").slice(0, 90);
    }
  }
  if (e.type === "result") {
    return (e.is_error ? "✗" : "✓") + " result"
      + (e.duration_ms ? ` · ${Math.round(e.duration_ms / 1000)}s` : "")
      + (e.num_turns ? ` · ${e.num_turns} turns` : "");
  }
  if (e.type === "system") return "hook: " + (e.hook_name || e.subtype || "");
  return "";
}

// Field-name chip for the event-log label: orchestrator phase (stripped) when
// present, else the agent role, else the raw event type.
function eventLabel(e) {
  if (e.phase) return e.phase.replace(/^orchestrator\./, "");
  return e.orchestrator_step || e.type || "?";
}

// ─────────────────────────────────────────────────────────────────────
// Review & merge — resolve an unmerged agent branch from the UI.
//
// A BL that failed its gate (engineer_unmerged) or a follow-up dispatch
// that came back not_merged leaves its agent/* branch behind. This is the
// in-UI recovery path: re-run the gate and merge on green, or force-merge
// with an explicit skip_gate override (justified e.g. when A49 gate
// flakiness false-reds a fix the operator has independently verified).
//
// Backend: POST /api/projects/{repo}/merge-branch {branch, skip_gate}
//          → { gate:{kind,reason?}, merge:{ok,kind,merged_sha}|null }
// ─────────────────────────────────────────────────────────────────────

function ReviewMergeButton({ repo, branch, onDone }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const run = async (skip_gate) => {
    setBusy(true); setResult(null);
    try {
      const r = await fetch(`${API}/api/projects/${encodeURIComponent(repo)}/merge-branch`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ branch, skip_gate }),
      });
      const body = await r.json();
      setResult(body);
      if (body?.merge?.ok) onDone?.();
    } catch (err) {
      setResult({ error: String(err) });
    } finally {
      setBusy(false);
    }
  };
  if (result?.merge?.ok) {
    return (
      <span style={{ color: "var(--ok, #6abf69)", fontSize: 11 }}>
        ✓ merged{result.merge.merged_sha ? ` · ${String(result.merge.merged_sha).slice(0, 8)}` : ""}
        {result.gate?.kind === "skipped" ? " (gate skipped)" : ""}
      </span>
    );
  }
  return (
    <span className="v2-row" style={{ gap: 6, alignItems: "center" }}>
      <button className="v2-secondary" disabled={busy} onClick={() => run(false)}
              style={{ fontSize: 11, padding: "3px 8px" }}
              title="Re-run the regression gate against this branch; merge only if green.">
        {busy ? "Re-gating…" : "Review & merge (re-run gate)"}
      </button>
      <button className="v2-secondary" disabled={busy} onClick={() => run(true)}
              style={{ fontSize: 11, padding: "3px 8px" }}
              title="Skip the gate and merge now. Use only when you have independently verified the branch (e.g. A49 gate flakiness).">
        Force merge (skip gate)
      </button>
      {result?.gate && !result.merge && (
        <span style={{ fontSize: 11, color: "#d6a13a" }}>
          gate {result.gate.kind}{result.gate.reason ? `: ${String(result.gate.reason).slice(0, 80)}` : ""}
        </span>
      )}
      {result?.error && (
        <span style={{ fontSize: 11, color: "#d66" }}>❌ {result.error}</span>
      )}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Branches panel — lists agent/* branches not yet merged into the agent
// branch (GET /branches) and offers Review & merge per branch. This is the
// general "resolve any anomaly without leaving the UI" surface: failed-gate
// BLs and not_merged follow-up dispatches both land here.
// ─────────────────────────────────────────────────────────────────────

function BranchesPanel({ repo, onChanged }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function refetch() {
    setLoading(true); setError(null);
    try {
      const r = await fetch(`${API}/api/projects/${encodeURIComponent(repo)}/branches`);
      const body = await r.json();
      if (!r.ok) { setError(body.detail || JSON.stringify(body)); setData(null); }
      else { setData(body); }
    } catch (e) {
      setError(e.message || String(e)); setData(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (repo) refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repo]);

  const unmerged = data?.unmerged || [];

  return (
    <div className="v2-branches-panel">
      <div className="v2-row" style={{ marginBottom: 8, alignItems: "center", gap: 8 }}>
        <strong style={{ fontSize: 13 }}>Unmerged branches ({unmerged.length})</strong>
        {data?.agent_branch && (
          <span style={{ opacity: 0.65, fontSize: 11 }}>→ <code>{data.agent_branch}</code></span>
        )}
        <span style={{ flex: 1 }} />
        <button onClick={refetch} disabled={loading} className="v2-secondary"
                style={{ fontSize: 11, padding: "2px 8px" }}>
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {error && (
        <div style={{ background: "#3b1f1f", padding: "8px 12px", borderRadius: 4, fontSize: 12, marginBottom: 8 }}>
          ❌ {error}
        </div>
      )}

      {!loading && unmerged.length === 0 && !error && (
        <div style={{ opacity: 0.65, fontSize: 12, padding: 12 }}>
          No unmerged branches — all work landed on <code>{data?.agent_branch || "the agent branch"}</code>.
        </div>
      )}

      {unmerged.map((b) => (
        <div key={b.branch} className="v2-branch-card"
             style={{ border: "1px solid #333", borderRadius: 6, padding: 10, marginBottom: 8, fontSize: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
            <code style={{ fontSize: 11 }}>{b.branch}</code>
            <span style={{ flex: 1 }} />
            {b.sha && <span style={{ opacity: 0.6, fontSize: 11 }}>{String(b.sha).slice(0, 8)}</span>}
            {b.when && <span style={{ opacity: 0.5, fontSize: 10 }}>{String(b.when).replace("T", " ").slice(0, 19)}</span>}
          </div>
          <ReviewMergeButton repo={repo} branch={b.branch} onDone={() => { refetch(); onChanged?.(); }} />
        </div>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// ABL-0014 §I.3 Batch D — Findings Triage Panel
//
// Operator surface for the per-feature acceptance findings ledger.
// Lists pending (default) or all findings for the open feature, with
// color-coded classification badges and three verdict actions per row
// (confirmed / refuted / deferred). Optimistic disable during in-flight
// POST; auto-refetch on success; inline error div on failure (matches
// the init-feature error pattern at AppV2 line 397-401).
//
// Backend contract: GET /api/projects/{repo}/findings?feature_slug=…&status=…
//                   POST /api/projects/{repo}/verdict
//                   (shipped Batch C, sha 3994a12)
// ─────────────────────────────────────────────────────────────────────

const CLASSIFICATION_BG = {
  product_bug: "#3b1f1f",  // red — matches the acceptance.error tile
  test_bug:    "#1f2a3b",  // blue — matches the acceptance.running tile
  data_bug:    "#2a2a2a",  // gray — matches the acceptance.skipped tile
  infra_bug:   "#3b2f1f",  // orange — matches the acceptance.done-failed tile
  uncertain:   "#2a2a2a",  // gray
};

function FindingsTriagePanel({ repo, featureSlug, onMerged }) {
  const [findings, setFindings] = useState([]);
  const [statusFilter, setStatusFilter] = useState("pending");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [inflight, setInflight] = useState(() => new Set());
  const [noteByFid, setNoteByFid] = useState({});
  const [expanded, setExpanded] = useState(() => new Set());
  // ABL-0021: per-finding on-demand "Dispatch fix" state.
  const [dispatching, setDispatching] = useState(() => new Set());
  const [dispatchLog, setDispatchLog] = useState({}); // fid -> {phase, outcome, merged_sha, error}

  async function refetch() {
    setLoading(true); setError(null);
    try {
      const url = `${API}/api/projects/${encodeURIComponent(repo)}` +
                  `/findings?feature_slug=${encodeURIComponent(featureSlug)}` +
                  `&status=${statusFilter}`;
      const r = await fetch(url);
      const body = await r.json();
      if (!r.ok) { setError(body.detail || JSON.stringify(body)); setFindings([]); }
      else { setFindings(body.findings || []); }
    } catch (e) {
      setError(e.message || String(e));
      setFindings([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (repo && featureSlug) refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repo, featureSlug, statusFilter]);

  async function submitVerdict(finding_id, verdict) {
    setInflight((prev) => { const n = new Set(prev); n.add(finding_id); return n; });
    setError(null);
    try {
      const r = await fetch(`${API}/api/projects/${encodeURIComponent(repo)}/verdict`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          feature_slug: featureSlug,
          finding_id,
          verdict,
          note: (noteByFid[finding_id] || "").trim() || null,
        }),
      });
      const body = await r.json();
      if (!r.ok) {
        const detail = body.detail || JSON.stringify(body);
        setError(`Verdict POST failed (${r.status}): ${detail}`);
      } else {
        // Drop the just-submitted note from local state, then refetch
        // so the list reflects the new verdict (Pending tab will hide
        // the row; All tab will show it with verdict + ts).
        setNoteByFid((prev) => { const { [finding_id]: _, ...rest } = prev; return rest; });
        await refetch();
      }
    } catch (e) {
      setError(`Verdict POST failed: ${e.message || String(e)}`);
    } finally {
      setInflight((prev) => { const n = new Set(prev); n.delete(finding_id); return n; });
    }
  }

  // ABL-0021: spawn a follow-up engineer on-demand for a confirmed
  // product_bug. Reuses the ABL-0015 dispatch engine via POST
  // /dispatch-followup; streams acceptance.followup.* + engineer sub-events.
  async function dispatchFix(finding_id) {
    setDispatching((prev) => { const n = new Set(prev); n.add(finding_id); return n; });
    setDispatchLog((p) => ({ ...p, [finding_id]: { phase: "starting…" } }));
    setError(null);
    try {
      const url = `${API}/api/projects/${encodeURIComponent(repo)}/dispatch-followup`;
      for await (const ev of streamPost(url, { feature_slug: featureSlug, finding_id })) {
        if (ev.type === "_error") {
          setDispatchLog((p) => ({ ...p, [finding_id]: { ...(p[finding_id] || {}), error: ev.error } }));
          continue;
        }
        const phase = (ev.phase || ev.type || "").replace(/^orchestrator\./, "");
        const upd = { phase };
        if (phase === "acceptance.followup.done") {
          upd.outcome = ev.outcome;
          upd.merged_sha = ev.merged_sha;
        }
        setDispatchLog((p) => ({ ...p, [finding_id]: { ...(p[finding_id] || {}), ...upd } }));
      }
      await refetch(); // reflect the new dispatch_state in the ledger
    } catch (e) {
      setDispatchLog((p) => ({ ...p, [finding_id]: { ...(p[finding_id] || {}), error: e.message || String(e) } }));
    } finally {
      setDispatching((prev) => { const n = new Set(prev); n.delete(finding_id); return n; });
    }
  }

  function toggleExpand(fid) {
    setExpanded((prev) => {
      const n = new Set(prev);
      if (n.has(fid)) n.delete(fid); else n.add(fid);
      return n;
    });
  }

  return (
    <div className="v2-findings-panel">
      <div className="v2-row" style={{ marginBottom: 8, alignItems: "center", gap: 8 }}>
        <strong style={{ fontSize: 13 }}>Findings ({findings.length})</strong>
        <span style={{ flex: 1 }} />
        <button
          onClick={() => setStatusFilter("pending")}
          className={statusFilter === "pending" ? "v2-primary" : "v2-secondary"}
          style={{ fontSize: 11, padding: "2px 8px" }}
        >Pending</button>
        <button
          onClick={() => setStatusFilter("all")}
          className={statusFilter === "all" ? "v2-primary" : "v2-secondary"}
          style={{ fontSize: 11, padding: "2px 8px" }}
        >All</button>
        <button
          onClick={refetch} disabled={loading}
          className="v2-secondary"
          style={{ fontSize: 11, padding: "2px 8px" }}
        >{loading ? "Refreshing…" : "Refresh"}</button>
      </div>

      {error && (
        <div style={{ background: "#3b1f1f", padding: "8px 12px", borderRadius: 4, fontSize: 12, marginBottom: 8 }}>
          ❌ {error}
        </div>
      )}

      {!loading && findings.length === 0 && !error && (
        <div style={{ opacity: 0.65, fontSize: 12, padding: 12 }}>
          {statusFilter === "pending"
            ? "No pending findings — all acceptance signals are triaged."
            : "Ledger is empty for this feature."}
        </div>
      )}

      {findings.map((f) => {
        const isInflight = inflight.has(f.finding_id);
        const isExpanded = expanded.has(f.finding_id);
        const isDispatching = dispatching.has(f.finding_id);
        const dlog = dispatchLog[f.finding_id];
        const canDispatch = f.verdict === "confirmed"
                            && f.classification === "product_bug"
                            && !f.dispatch_state;
        const bg = CLASSIFICATION_BG[f.classification] || "#2a2a2a";
        const evidenceShort = (f.evidence_summary || "").slice(0, 200);
        const evidenceTrunc = (f.evidence_summary || "").length > 200;
        return (
          <div
            key={f.finding_id}
            className="v2-finding-card"
            style={{
              border: "1px solid #333", borderRadius: 6, padding: 10,
              marginBottom: 8, fontSize: 12,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <span style={{
                background: bg, padding: "2px 8px", borderRadius: 3,
                fontFamily: "monospace", fontSize: 11, fontWeight: 600,
              }}>{f.classification}</span>
              <span style={{ opacity: 0.7 }}>
                {f.journey_kind}:{f.journey_id}
              </span>
              <span style={{ flex: 1 }} />
              {f.verdict && (
                <span style={{
                  background: f.verdict === "confirmed" ? "#1f3b1f"
                            : f.verdict === "refuted"   ? "#3b1f1f"
                            : "#2a2a2a",
                  padding: "2px 8px", borderRadius: 3, fontSize: 11,
                }}>
                  {f.verdict} · {f.verdict_ts}
                </span>
              )}
              {f.dispatch_state && (
                <span style={{
                  background: f.dispatch_state === "merged" ? "#1f3b1f"
                            : f.dispatch_state === "dispatched" ? "#2a2a3b"
                            : "#3b2f1f",
                  padding: "2px 8px", borderRadius: 3, fontSize: 11,
                }} title="ABL-0015/0021 follow-up dispatch state">
                  fix: {f.dispatch_state}
                </span>
              )}
              {f.seen_count > 1 && (
                <span style={{ opacity: 0.6, fontSize: 11 }}>seen×{f.seen_count}</span>
              )}
            </div>

            <div style={{
              fontFamily: "monospace", fontSize: 11,
              background: "#181818", padding: 8, borderRadius: 3, marginBottom: 6,
              whiteSpace: "pre-wrap", wordBreak: "break-word",
            }}>
              {isExpanded || !evidenceTrunc ? f.evidence_summary : evidenceShort + "…"}
              {evidenceTrunc && (
                <button
                  onClick={() => toggleExpand(f.finding_id)}
                  className="v2-secondary"
                  style={{ marginLeft: 8, fontSize: 10, padding: "1px 6px" }}
                >
                  {isExpanded ? "less" : "more"}
                </button>
              )}
            </div>

            {f.verdict_note && (
              <div style={{ fontSize: 11, opacity: 0.85, marginBottom: 6 }}>
                <strong>Note:</strong> {f.verdict_note}
              </div>
            )}

            {!f.verdict && (
              <>
                <input
                  type="text"
                  placeholder="Optional note (one line) before recording verdict…"
                  value={noteByFid[f.finding_id] || ""}
                  onChange={(e) => setNoteByFid((p) => ({ ...p, [f.finding_id]: e.target.value }))}
                  disabled={isInflight}
                  style={{ width: "100%", fontSize: 11, padding: "4px 6px", marginBottom: 6 }}
                />
                <div className="v2-row" style={{ gap: 6 }}>
                  <button
                    onClick={() => submitVerdict(f.finding_id, "confirmed")}
                    disabled={isInflight}
                    className="v2-primary"
                    style={{ fontSize: 11, padding: "4px 10px" }}
                    title="Classifier was right; this is a real bug."
                  >Confirm</button>
                  <button
                    onClick={() => submitVerdict(f.finding_id, "refuted")}
                    disabled={isInflight}
                    className="v2-secondary"
                    style={{ fontSize: 11, padding: "4px 10px" }}
                    title="Classifier was wrong; not a real bug."
                  >Refute</button>
                  <button
                    onClick={() => submitVerdict(f.finding_id, "deferred")}
                    disabled={isInflight}
                    className="v2-secondary"
                    style={{ fontSize: 11, padding: "4px 10px" }}
                    title="Real but intentionally deferred (post-MVP, etc.)."
                  >Defer</button>
                  {isInflight && <span style={{ opacity: 0.7, fontSize: 11 }}>…submitting</span>}
                </div>
              </>
            )}

            {/* ABL-0021: on-demand "Dispatch fix" for a confirmed product_bug.
                Two-step per-finding: Confirm (above) then Dispatch fix here. */}
            {canDispatch && (
              <div className="v2-row" style={{ gap: 6, marginTop: 6, alignItems: "center" }}>
                <button
                  onClick={() => dispatchFix(f.finding_id)}
                  disabled={isDispatching}
                  className="v2-primary"
                  style={{ fontSize: 11, padding: "4px 10px" }}
                  title="Spawn a follow-up engineer to fix this confirmed bug. It clears the same regression gate + auto-merge bar as any BL (ABL-0015 engine)."
                >{isDispatching ? "Dispatching…" : "🛠 Dispatch fix"}</button>
                {dlog && dlog.phase && !dlog.outcome && !dlog.error && (
                  <span style={{ opacity: 0.7, fontSize: 11 }}>{dlog.phase}</span>
                )}
              </div>
            )}

            {dlog && dlog.outcome && (
              <div style={{
                fontSize: 11, marginTop: 6, padding: "4px 8px", borderRadius: 3,
                background: dlog.outcome === "merged" ? "#1f3b1f" : "#3b2f1f",
              }}>
                {dlog.outcome === "merged"
                  ? `✅ fix merged${dlog.merged_sha ? ` · ${String(dlog.merged_sha).slice(0, 8)}` : ""}`
                  : "⚠ follow-up did not merge — left for review"}
              </div>
            )}
            {dlog && dlog.error && (
              <div style={{ fontSize: 11, marginTop: 6, padding: "4px 8px", borderRadius: 3, background: "#3b1f1f" }}>
                ❌ dispatch failed: {dlog.error}
              </div>
            )}
            {f.dispatch_merged_sha && (
              <div style={{ fontSize: 11, marginTop: 4, opacity: 0.8 }}>
                merged sha: <code>{String(f.dispatch_merged_sha).slice(0, 12)}</code>
                {f.dispatch_bl_id ? ` · ${f.dispatch_bl_id}` : ""}
              </div>
            )}

            {/* In-place recovery: a dispatched fix whose gate did not merge.
                Review & merge the follow-up branch right here (the same action
                as the Unmerged-branches panel), without leaving the finding. */}
            {f.dispatch_state === "not_merged" && f.dispatch_run_id && (
              <div style={{ marginTop: 6, padding: "6px 8px", borderRadius: 3, background: "#2a2419" }}>
                <div style={{ fontSize: 11, marginBottom: 4, opacity: 0.85 }}>
                  ⚠ fix dispatched but the gate did not auto-merge — resolve in place:
                </div>
                <ReviewMergeButton
                  repo={repo}
                  branch={`agent/followup-${f.dispatch_run_id}-0`}
                  onDone={() => { refetch(); onMerged?.(); }}
                />
              </div>
            )}

            <div style={{ marginTop: 6, opacity: 0.5, fontSize: 10, fontFamily: "monospace" }}>
              {f.finding_id.slice(0, 20)}… · first={f.first_seen_ts} · run={f.run_id}
            </div>
          </div>
        );
      })}
    </div>
  );
}
