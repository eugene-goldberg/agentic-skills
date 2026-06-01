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
  const [stages, setStages] = useState(initialStages());
  const [bls, setBls] = useState([]); // {id, title, deps, steps:{engineer, reindex_e, qa, reindex_q, scorer}, outcome}
  const [events, setEvents] = useState([]);
  const [detail, setDetail] = useState(null);
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
    }
  }

  function stop() {
    if (abortRef.current) abortRef.current.abort();
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
        </div>

        <div className="v2-rail">
          <h2>Detail</h2>
          <pre className="v2-detail">{detail ? JSON.stringify(detail, null, 2) : "Click a stage or BL step to inspect."}</pre>
        </div>
      </section>

      <details className="v2-log">
        <summary>Event log ({events.length})</summary>
        <div className="v2-log-body">
          {events.slice(-200).map((e, i) => (
            <div key={i} className="v2-log-line">
              <span className="v2-log-phase">{e.phase || e.type || "?"}</span>
              {e.bl_id ? <span className="v2-log-bl">{e.bl_id}</span> : null}
              <span className="v2-log-text">{shortDesc(e)}</span>
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
