import { useCallback, useEffect, useRef, useState } from "react";
import { streamPost } from "./sse.js";

const EXAMPLE_BRIEF = `# Project: Personal Note Taker

Build a small FastAPI service that lets a single user store and search markdown notes.

## Requirements
- Notes have a title, body (markdown), created_at, updated_at.
- POST /notes creates a note.
- GET /notes lists all notes.
- GET /notes/{id} returns one note.
- PATCH /notes/{id} updates title/body.
- DELETE /notes/{id} removes it.
- GET /notes/search?q=... returns notes whose title or body contains the query (case-insensitive).
- SQLite persistence, auto-create tables on startup.
- pytest tests covering CRUD + search.`;

export function AppV1() {
  const [repos, setRepos] = useState([]);
  const [repo, setRepo] = useState("");
  const [brief, setBrief] = useState(EXAMPLE_BRIEF);
  const [projectName, setProjectName] = useState("");
  const [backlog, setBacklog] = useState([]);
  const [selectedBL, setSelectedBL] = useState(null);
  const [extraNotes, setExtraNotes] = useState("");

  const [phase, setPhase] = useState("idle"); // idle | po | engineer | qa | scorer
  const [events, setEvents] = useState([]);
  const [summary, setSummary] = useState(null);
  const [indexStatus, setIndexStatus] = useState({ ctx: null, graph: null });
  const [indexRunning, setIndexRunning] = useState({ ctx: false, graph: false });
  const [traces, setTraces] = useState([]);
  const [selectedTraceId, setSelectedTraceId] = useState(null);
  const [traceDetail, setTraceDetail] = useState(null);
  const [traceDetailLoading, setTraceDetailLoading] = useState(false);
  const abortRef = useRef(null);
  const logBottomRef = useRef(null);

  // ---------- load repos ----------
  useEffect(() => {
    fetch("/api/tasks/repos")
      .then((r) => r.json())
      .then((d) => {
        setRepos(d.repos || []);
        if (d.repos?.length) setRepo(d.repos[0].name);
      });
  }, []);

  // ---------- load backlog whenever repo changes ----------
  const reloadBacklog = useCallback(async (r) => {
    if (!r) return;
    const d = await fetch(`/api/projects/${encodeURIComponent(r)}/backlog`).then((x) => x.json());
    setBacklog(d.items || []);
  }, []);
  useEffect(() => {
    reloadBacklog(repo);
  }, [repo, reloadBacklog]);

  // ---------- traces ----------
  const traceIdFromDir = (dir) => (dir ? dir.split("/").pop() : null);
  const reloadTraces = useCallback(async (r) => {
    if (!r) {
      setTraces([]);
      return;
    }
    try {
      const d = await fetch(`/api/projects/${encodeURIComponent(r)}/traces?limit=100`).then((x) => x.json());
      setTraces(d.traces || []);
    } catch {
      setTraces([]);
    }
  }, []);
  useEffect(() => {
    reloadTraces(repo);
    setSelectedTraceId(null);
    setTraceDetail(null);
  }, [repo, reloadTraces]);

  const openTrace = async (id) => {
    if (!repo || !id) return;
    setSelectedTraceId(id);
    setTraceDetail(null);
    setTraceDetailLoading(true);
    try {
      const d = await fetch(`/api/projects/${encodeURIComponent(repo)}/traces/${encodeURIComponent(id)}`).then((x) => x.json());
      setTraceDetail(d);
    } catch (err) {
      setTraceDetail({ _error: String(err) });
    } finally {
      setTraceDetailLoading(false);
    }
  };

  // ---------- autoscroll ----------
  useEffect(() => {
    logBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  const startStream = async (url, body, role) => {
    setEvents([]);
    setSummary(null);
    setPhase(role);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      for await (const evt of streamPost(url, body, controller.signal)) {
        setEvents((prev) => [...prev, evt]);
        if (evt.type === "done") setSummary(evt);
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        setEvents((prev) => [...prev, { type: "_error", error: String(err) }]);
      }
    } finally {
      setPhase("idle");
      abortRef.current = null;
      // Refresh backlog after either flow (PO may have just written it)
      reloadBacklog(repo);
      reloadTraces(repo);
    }
  };

  const decompose = () =>
    startStream(
      `/api/projects/${encodeURIComponent(repo)}/decompose-brief`,
      { brief, project_name: projectName || null },
      "po",
    );

  const executeBL = () =>
    startStream(
      `/api/projects/${encodeURIComponent(repo)}/execute-bl`,
      { bl_id: selectedBL, extra_notes: extraNotes || null },
      "engineer",
    );

  const runQA = () =>
    startStream(
      `/api/projects/${encodeURIComponent(repo)}/qa-bl`,
      { bl_id: selectedBL },
      "qa",
    );

  const scoreBL = () =>
    startStream(
      `/api/projects/${encodeURIComponent(repo)}/score-bl`,
      { bl_id: selectedBL },
      "scorer",
    );

  const cancel = () => abortRef.current?.abort();
  const running = phase !== "idle";

  const runIndex = async (kind) => {
    if (!repo) return;
    const key = kind === "graphify" ? "graph" : "ctx";
    setIndexRunning((s) => ({ ...s, [key]: true }));
    setIndexStatus((s) => ({ ...s, [key]: null }));
    try {
      const res = await fetch(
        `/api/projects/${encodeURIComponent(repo)}/index/${kind}`,
        { method: "POST" },
      );
      const data = await res.json();
      setIndexStatus((s) => ({ ...s, [key]: { ...data, http: res.status } }));
    } catch (err) {
      setIndexStatus((s) => ({ ...s, [key]: { ok: false, error: String(err) } }));
    } finally {
      setIndexRunning((s) => ({ ...s, [key]: false }));
    }
  };

  return (
    <div className="page">
      <header>
        <h1>Claude Code Agent Runner</h1>
        <p className="sub">
          PO decomposes a brief → backlog list → click any item to run the engineer agent on
          just that BL.
        </p>
      </header>

      <section className="repo-row">
        <label>
          Repo
          <select value={repo} onChange={(e) => setRepo(e.target.value)} disabled={running}>
            {repos.length === 0 && <option value="">— no repos in backend/repos —</option>}
            {repos.map((r) => (
              <option key={r.name} value={r.name}>
                {r.name}
              </option>
            ))}
          </select>
        </label>
        <div className="index-buttons">
          <button
            className="secondary"
            disabled={!repo || running || indexRunning.ctx}
            onClick={() => runIndex("claude-context")}
            title="Index the selected repo into Milvus via @zilliz/claude-context-core (Azure embeddings)."
          >
            {indexRunning.ctx ? "indexing…" : "Run claude-context index"}
          </button>
          <IndexBadge status={indexStatus.ctx} kind="ctx" />
          <button
            className="secondary"
            disabled={!repo || running || indexRunning.graph}
            onClick={() => runIndex("graphify")}
            title="Run `graphify update` to (re)build graphify-out/graph.json."
          >
            {indexRunning.graph ? "indexing…" : "Run graphify"}
          </button>
          <IndexBadge status={indexStatus.graph} kind="graph" />
          <div className="bl-action-buttons">
            <button
              className="secondary"
              disabled={!repo || !selectedBL || running}
              onClick={runQA}
              title={selectedBL ? `Run the QA agent against ${selectedBL}` : "Select a BL first"}
            >
              {phase === "qa" ? `QA running ${selectedBL}…` : `Run QA${selectedBL ? ` (${selectedBL})` : ""}`}
            </button>
            <button
              className="secondary"
              disabled={!repo || !selectedBL || running}
              onClick={scoreBL}
              title={selectedBL ? `Score ${selectedBL} against the rubric` : "Select a BL first"}
            >
              {phase === "scorer" ? `Scoring ${selectedBL}…` : `Score${selectedBL ? ` ${selectedBL}` : " Current BL"}`}
            </button>
          </div>
        </div>
      </section>

      <section className={`progress-bar-section ${indexRunning.ctx || indexRunning.graph ? "active" : "inactive"}`}>
        <div className="progress-label">
          {indexRunning.ctx && indexRunning.graph
            ? "Indexing claude-context + graphify…"
            : indexRunning.ctx
            ? "Indexing claude-context…"
            : indexRunning.graph
            ? "Refreshing graphify graph…"
            : "Idle"}
        </div>
        <div className="progress-track" aria-hidden={!(indexRunning.ctx || indexRunning.graph)}>
          <div className="progress-bar" />
        </div>
      </section>

      <div className="two-pane">
        <section className="brief">
          <h2>1 · Brief → PO agent</h2>
          <input
            className="project-name"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            placeholder="(optional) Project name override"
            disabled={running}
          />
          <textarea
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
            rows={14}
            disabled={running}
            placeholder="Paste the full project brief here..."
          />
          <div className="actions">
            <button onClick={decompose} disabled={running || !repo || brief.length < 20}>
              {phase === "po" ? "PO decomposing…" : "Decompose brief"}
            </button>
            {phase === "po" && (
              <button onClick={cancel} className="secondary">Cancel</button>
            )}
          </div>
        </section>

        <section className="backlog">
          <h2>
            2 · Backlog <span className="count">({backlog.length})</span>
          </h2>
          {backlog.length === 0 && (
            <p className="empty">No backlog yet — decompose a brief first.</p>
          )}
          <ul className="bl-list">
            {backlog.map((b) => (
              <li
                key={b.id}
                className={`bl-row ${selectedBL === b.id ? "selected" : ""}`}
                onClick={() => !running && setSelectedBL(b.id)}
              >
                <div className="bl-head">
                  <input
                    type="radio"
                    name="bl"
                    checked={selectedBL === b.id}
                    onChange={() => setSelectedBL(b.id)}
                    disabled={running}
                  />
                  <code className="bl-id">{b.id}</code>
                  <span className="bl-title">{b.title}</span>
                  {b.priority && <span className={`pill prio-${b.priority.toLowerCase()}`}>{b.priority}</span>}
                </div>
                {b.story && <p className="bl-story">{b.story}</p>}
                {b.dependencies && b.dependencies !== "none" && (
                  <p className="bl-deps">deps: <code>{b.dependencies}</code></p>
                )}
              </li>
            ))}
          </ul>

          {backlog.length > 0 && (
            <>
              <textarea
                className="extra"
                value={extraNotes}
                onChange={(e) => setExtraNotes(e.target.value)}
                rows={2}
                disabled={running}
                placeholder="(optional) Extra notes the engineer should consider for this BL..."
              />
              <div className="actions">
                <button
                  onClick={executeBL}
                  disabled={running || !selectedBL}
                >
                  {phase === "engineer" ? `Engineer running ${selectedBL}…` : `Execute ${selectedBL || "…"}`}
                </button>
                {phase === "engineer" && (
                  <button onClick={cancel} className="secondary">Cancel</button>
                )}
              </div>
            </>
          )}
        </section>
      </div>

      {summary && (
        <section className="summary">
          <h2>✓ {summary.role === "po" ? "PO decomposition complete" : `${summary.bl_id} done`}</h2>
          <dl>
            {summary.bl_id && (<><dt>BL</dt><dd><code>{summary.bl_id}</code></dd></>)}
            <dt>Branch</dt><dd><code>{summary.branch}</code></dd>
            <dt>Commit</dt><dd><code>{summary.commit_sha?.slice(0, 12) || "(none)"}</code></dd>
            <dt>New commits</dt><dd>{summary.new_commits}</dd>
            {summary.imported_backlog_path && (
              <><dt>Backlog imported</dt><dd><code>{summary.imported_backlog_path}</code></dd></>
            )}
            {summary.agent_branch && (
              <><dt>Agent branch</dt><dd><code>{summary.agent_branch}</code></dd></>
            )}
            {summary.gate_kind && (
              <>
                <dt>Regression gate</dt>
                <dd>
                  {summary.gate_kind === "green" && <span style={{color: "var(--ok)"}}>✓ green — no regressions</span>}
                  {summary.gate_kind === "regressed" && (
                    <span style={{color: "var(--error)"}}>✗ regressions: {(summary.regressions || []).slice(0, 3).join(", ")}{(summary.regressions || []).length > 3 ? ` (+${(summary.regressions || []).length - 3} more)` : ""}</span>
                  )}
                  {summary.gate_kind === "skipped" && <span className="dim">— (greenfield)</span>}
                  {summary.gate_kind === "error" && <span style={{color: "var(--warn)"}}>! gate error</span>}
                </dd>
              </>
            )}
            {summary.merged_to_target !== undefined && (
              <>
                <dt>Merged to target</dt>
                <dd>
                  {summary.merged_to_target
                    ? <span style={{color: "var(--ok)"}}>✓ yes</span>
                    : (summary.gate_kind === "regressed" || summary.gate_kind === "error")
                      ? <ReviewMergeButton repo={repo} branch={summary.branch} onDone={() => { reloadBacklog(repo); reloadTraces(repo); }} />
                      : <span className="dim">— (no new commits)</span>}
                </dd>
              </>
            )}
            {summary.merged_to_main !== undefined && summary.merged_to_target === undefined && (
              <>
                <dt>Merged to main</dt>
                <dd>
                  {summary.merged_to_main
                    ? <span style={{color: "var(--ok)"}}>✓ yes</span>
                    : <span style={{color: "var(--warn)"}}>✗ {summary.merge_error || "no"}</span>}
                </dd>
              </>
            )}
          </dl>
        </section>
      )}

      <section className="traces">
        <h2>
          Traces <span className="count">({traces.length})</span>
          <button
            className="secondary inline-refresh"
            onClick={() => reloadTraces(repo)}
            disabled={!repo}
            title="Reload trace list"
          >↻</button>
        </h2>
        {traces.length === 0 && <p className="empty">No traces yet — every agent run records one.</p>}
        {traces.length > 0 && (
          <div className="trace-grid">
            <ul className="trace-list">
              {traces.map((t) => {
                const id = traceIdFromDir(t.trace_dir || t._dir);
                const dur = t.duration_s != null ? `${t.duration_s.toFixed(1)}s` : "…";
                const started = t.started_at?.replace("T", " ").slice(0, 19);
                return (
                  <li
                    key={id}
                    className={`trace-row ${selectedTraceId === id ? "selected" : ""}`}
                    onClick={() => openTrace(id)}
                  >
                    <div className="trace-head">
                      <span className={`pill role-${t.role}`}>{t.role}</span>
                      {t.bl_id && <code className="bl-id">{t.bl_id}</code>}
                      <span className="trace-time">{started}</span>
                      <span className="trace-dur">{dur}</span>
                    </div>
                    <div className="trace-meta">
                      <span>events {t.n_events ?? "?"}</span>
                      <span>tools {t.n_tool_use ?? "?"}</span>
                      <span>retrieval {t.n_retrieval_calls ?? 0}</span>
                      {t.done?.commit_sha && (
                        <span>commit <code>{t.done.commit_sha.slice(0, 8)}</code></span>
                      )}
                      {t.done?.verdict && (
                        <span className={`pill verdict-${String(t.done.verdict).toLowerCase().replace(/[^a-z]/g, "_")}`}>
                          {t.done.verdict}
                        </span>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
            <div className="trace-detail">
              {!selectedTraceId && <p className="empty">Select a trace to see details.</p>}
              {selectedTraceId && traceDetailLoading && <p className="empty">Loading…</p>}
              {selectedTraceId && traceDetail?._error && (
                <p className="error">[error] {traceDetail._error}</p>
              )}
              {selectedTraceId && traceDetail && !traceDetail._error && (
                <TraceDetailView detail={traceDetail} />
              )}
            </div>
          </div>
        )}
      </section>

      <section className="log">
        <h2>
          Stream <span className="count">({events.length})</span>
          {phase !== "idle" && <span className="phase-tag">{phase}</span>}
        </h2>
        {events.length === 0 && phase === "idle" && <p className="empty">No events yet.</p>}
        <ul>
          {events.map((evt, i) => (
            <li key={i} className={`evt evt-${(evt.type || "unknown").replace(/[^a-z0-9_-]/gi, "_")}`}>
              <EventLine evt={evt} />
            </li>
          ))}
        </ul>
        <div ref={logBottomRef} />
      </section>
    </div>
  );
}

function IndexBadge({ status, kind }) {
  if (!status) return null;
  if (!status.ok) {
    return <span className="idx-badge idx-bad" title={JSON.stringify(status)}>✗ {status.error || `HTTP ${status.http}`}</span>;
  }
  if (kind === "ctx") {
    const n = status.indexed_files ?? status.raw?.result?.indexedFiles;
    const c = status.total_chunks ?? status.raw?.result?.totalChunks;
    return <span className="idx-badge idx-ok">✓ {n ?? "?"} files, {c ?? "?"} chunks</span>;
  }
  return <span className="idx-badge idx-ok">✓ {status.nodes ?? "?"} nodes, {status.edges ?? "?"} edges</span>;
}


function ReviewMergeButton({ repo, branch, onDone }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const run = async (skip_gate) => {
    setBusy(true);
    try {
      const r = await fetch(`/api/projects/${encodeURIComponent(repo)}/merge-branch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ branch, skip_gate }),
      }).then((x) => x.json());
      setResult(r);
      if (r?.merge?.ok) onDone?.();
    } catch (err) {
      setResult({ error: String(err) });
    } finally {
      setBusy(false);
    }
  };
  if (result?.merge?.ok) {
    return <span style={{ color: "var(--ok)" }}>✓ merged after review ({result.merge.merged_sha?.slice(0, 8)})</span>;
  }
  return (
    <span>
      <button className="secondary tiny" disabled={busy} onClick={() => run(false)}>
        {busy ? "Re-gating…" : "Review & merge (re-run gate)"}
      </button>
      <button className="secondary tiny" style={{ marginLeft: 6 }} disabled={busy} onClick={() => run(true)}>
        Force merge (skip gate)
      </button>
      {result?.gate && !result.merge && (
        <div style={{ fontSize: 11, color: "var(--warn)", marginTop: 4 }}>
          gate {result.gate.kind}: {result.gate.reason}
        </div>
      )}
    </span>
  );
}


function TraceDetailView({ detail }) {
  const { meta, stream, retrieval } = detail;
  const [tab, setTab] = useState("stream");
  const [promptOpen, setPromptOpen] = useState(false);
  return (
    <div className="trace-detail-view">
      <div className="trace-detail-meta">
        <div className="row">
          <span className={`pill role-${meta.role}`}>{meta.role}</span>
          {meta.bl_id && <code className="bl-id">{meta.bl_id}</code>}
          <span>task <code>{meta.task_id}</code></span>
          <span>started {meta.started_at?.replace("T", " ").slice(0, 19)}</span>
          <span>{meta.duration_s != null ? `${meta.duration_s.toFixed(2)}s` : "…"}</span>
        </div>
        <div className="row dim">
          <span>events {meta.n_events}</span>
          <span>tool_use {meta.n_tool_use}</span>
          <span>tool_result {meta.n_tool_result}</span>
          <span>retrieval {meta.n_retrieval_calls ?? 0}</span>
          {meta.done?.commit_sha && <span>commit <code>{meta.done.commit_sha.slice(0, 12)}</code></span>}
          {meta.done?.branch && <span>branch <code>{meta.done.branch}</code></span>}
          {meta.final_result_frame?.total_cost_usd != null && (
            <span>cost ${Number(meta.final_result_frame.total_cost_usd).toFixed(4)}</span>
          )}
        </div>
        <button className="secondary tiny" onClick={() => setPromptOpen((v) => !v)}>
          {promptOpen ? "Hide prompt" : "Show prompt"}
        </button>
        {promptOpen && (
          <pre className="prompt-pre">{meta.prompt || "(no prompt captured)"}</pre>
        )}
      </div>
      <div className="trace-tabs">
        <button
          className={tab === "stream" ? "tab active" : "tab"}
          onClick={() => setTab("stream")}
        >Stream ({stream?.length ?? 0})</button>
        <button
          className={tab === "retrieval" ? "tab active" : "tab"}
          onClick={() => setTab("retrieval")}
        >Retrieval ({retrieval?.length ?? 0})</button>
        <button
          className={tab === "raw" ? "tab active" : "tab"}
          onClick={() => setTab("raw")}
        >Raw meta</button>
      </div>
      {tab === "stream" && (
        <ul className="trace-stream">
          {(stream || []).map((evt, i) => (
            <li key={i} className={`evt evt-${(evt.type || "unknown").replace(/[^a-z0-9_-]/gi, "_")}`}>
              {evt._ts && <span className="ts dim">{evt._ts.slice(11, 19)} </span>}
              <EventLine evt={evt} />
            </li>
          ))}
        </ul>
      )}
      {tab === "retrieval" && (
        <ul className="trace-retrieval">
          {(retrieval || []).length === 0 && <li className="empty">No retrieval calls in this run.</li>}
          {(retrieval || []).map((r, i) => (
            <li key={i} className="evt">
              <span className="ts dim">{r.ts?.slice(11, 19)} </span>
              <b>{r.tool}</b>
              {r.query && <> · query=<code>{String(r.query).slice(0, 80)}</code></>}
              {r.symbol && <> · symbol=<code>{r.symbol}</code></>}
              {r.path && <> · path=<code>{r.path}</code></>}
              {r.source && <> · source={r.source}</>}
              {r.n_hits != null && <> · hits={r.n_hits}</>}
              {r.n != null && <> · n={r.n}</>}
              {r.error && <span className="error"> · error: {r.error}</span>}
            </li>
          ))}
        </ul>
      )}
      {tab === "raw" && (
        <pre className="trace-raw">{JSON.stringify(meta, null, 2)}</pre>
      )}
    </div>
  );
}


function EventLine({ evt }) {
  const type = evt.type || "unknown";
  if (type === "_meta") {
    if (evt.phase === "regression_gate") {
      const cls = evt.kind === "green" ? "ok"
                : evt.kind === "regressed" ? "bad"
                : evt.kind === "skipped" ? "dim"
                : "warn";
      const pre = evt.pre ? `pre ${evt.pre.n_passed}p/${evt.pre.n_failed}f` : "";
      const post = evt.post ? `post ${evt.post.n_passed}p/${evt.post.n_failed}f` : "";
      const regs = evt.regressions?.length ? ` regressions=${evt.regressions.length}` : "";
      return (
        <code className={`meta gate-${cls}`}>
          [gate] {evt.kind} · {pre} → {post}{regs} · {evt.reason || ""}
        </code>
      );
    }
    if (evt.phase === "awaiting_review") {
      return <code className="meta gate-warn">[gate] awaiting review — {evt.reason}</code>;
    }
    if (evt.phase === "merge_to_target") {
      return <code className={`meta gate-${evt.ok ? "ok" : "warn"}`}>[merge] {evt.kind} → {evt.target_ref} · {evt.merged_sha?.slice(0, 8) || evt.error}</code>;
    }
    const bits = [];
    if (evt.phase) bits.push(`phase=${evt.phase}`);
    if (evt.task_id) bits.push(`task=${evt.task_id}`);
    if (evt.branch) bits.push(`branch=${evt.branch}`);
    if (evt.bl_id) bits.push(`bl=${evt.bl_id}`);
    if (evt.role) bits.push(`role=${evt.role}`);
    if (evt.exit_code != null) bits.push(`exit=${evt.exit_code}`);
    if (evt.duration_s != null) bits.push(`dt=${evt.duration_s}s`);
    return <code className="meta">[meta] {bits.join(" ")}</code>;
  }
  if (type === "_error") return <span className="error">[error] {evt.error}</span>;
  if (type === "done") {
    return (
      <strong>
        ✓ done {evt.bl_id ? `${evt.bl_id} ` : ""}commit {evt.commit_sha?.slice(0, 8) ?? "(none)"}
      </strong>
    );
  }
  if (type === "assistant") {
    const content = evt.message?.content;
    const text = Array.isArray(content)
      ? content.map((c) => c.text || (c.type === "tool_use" ? `→ ${c.name}(${JSON.stringify(c.input)?.slice(0, 80)})` : "")).filter(Boolean).join(" ")
      : (typeof content === "string" ? content : JSON.stringify(content));
    return <span><b>assistant</b>: {text?.slice(0, 600)}</span>;
  }
  if (type === "user") {
    const content = evt.message?.content;
    const text = Array.isArray(content)
      ? content.map((c) => c.content || c.text || "").filter(Boolean).join(" ")
      : JSON.stringify(content);
    return <span className="dim"><b>tool_result</b>: {String(text).slice(0, 200)}</span>;
  }
  if (type === "result") {
    return <strong className="result">result: {String(evt.result || "").slice(0, 600)}</strong>;
  }
  if (type === "system") {
    return <code className="dim">[system] {evt.subtype || JSON.stringify(evt).slice(0, 100)}</code>;
  }
  return <code>{JSON.stringify(evt).slice(0, 400)}</code>;
}
