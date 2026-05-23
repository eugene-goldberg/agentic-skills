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
  const [brief, setBrief] = useState("");
  const [maxBls, setMaxBls] = useState("");
  const [skipPo, setSkipPo] = useState(false);
  const [running, setRunning] = useState(false);
  const [stages, setStages] = useState(initialStages());
  const [bls, setBls] = useState([]); // {id, title, deps, steps:{engineer, reindex_e, qa, reindex_q, scorer}, outcome}
  const [events, setEvents] = useState([]);
  const [detail, setDetail] = useState(null);
  const abortRef = useRef(null);
  const logEndRef = useRef(null);

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
        setStage("preflight", { status: "done" });
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
      if (key === "bl.done") { upsertBl(blId, { status: "done", outcome: evt.outcome }); return; }
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
        return;
      }
      if (key === "aborted") {
        setStage("sprint_complete", { status: "failed", detail: evt.reason });
        return;
      }
    }

    // per-role events carrying orchestrator_step + bl_id are reflected as detail
    if (step && blId) {
      // Surface short status from interesting per-role phases
      if (phase === "regression_gate") {
        setBlStep(blId, step === "qa" ? "qa" : "engineer",
                  { gate_kind: evt.kind, gate_ok: evt.ok });
      }
      if (phase === "merge_to_target" && evt.ok) {
        // already captured at done
      }
      if (phase === "awaiting_review") {
        setBlStep(blId, step, { awaiting: true, reason: evt.reason });
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
        project_name: null,
        max_bls: maxBls ? parseInt(maxBls, 10) : null,
        skip_po: skipPo,
        stop_on_failure: true,
        timeout_per_role: 2400,
      };
      for await (const evt of streamPost(`${API}/api/projects/${encodeURIComponent(repo)}/run-brief`, body, ctrl.signal)) {
        ingest(evt);
      }
    } catch (e) {
      ingest({ type: "_error", error: e.message || String(e), phase: "orchestrator.aborted" });
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
        </div>
        <textarea
          className="v2-brief"
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          placeholder="Describe the feature you want the team to deliver. Min 20 characters. E.g. 'Add multi-tenant collaboration with workspaces, invitations, and per-workspace task lists. Keep backwards-compat with existing single-user routes.'"
          rows={6}
          disabled={running}
        />
        <div className="v2-row">
          <button onClick={run} disabled={running || brief.length < 20 || !repo} className="v2-primary">
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
  return (
    <div className={`v2-bl v2-${b.status || "pending"}`}>
      <div className="v2-bl-head" onClick={() => onClick("")}>
        <strong>{b.id}</strong> <span className="v2-bl-title">{b.title}</span>
        <span className="v2-bl-outcome">{b.outcome || b.status || "pending"}</span>
      </div>
      <div className="v2-bl-steps">
        {steps.map((s) => {
          const st = b.steps[s] || {};
          return (
            <div key={s} className={`v2-sub v2-${st.status || "pending"}`} onClick={() => onClick(s)}>
              <span className="v2-dot v2-dot-sm" />
              <span>{s}</span>
              {st.gate_kind ? <span className="v2-tag-sm">{st.gate_kind}</span> : null}
              {st.no_op ? <span className="v2-tag-sm">no-op</span> : null}
              {st.awaiting ? <span className="v2-tag-sm">awaiting</span> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function shortDesc(e) {
  if (e.type === "_error") return e.error;
  if (e.phase === "orchestrator.backlog_parsed") return `${e.count} BLs`;
  if (e.phase === "regression_gate") return `gate=${e.kind} ok=${e.ok}`;
  if (e.phase === "merge_to_target") return `merged=${e.ok}`;
  if (e.phase === "doctrine_check") return `${e.kind} attempts=${e.attempts ?? e.attempt ?? "?"}`;
  if (e.phase === "worktree_ready") return e.role || "";
  if (e.summary) return typeof e.summary === "string" ? e.summary.slice(0, 80) : "";
  return "";
}
