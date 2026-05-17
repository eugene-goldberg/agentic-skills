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

export function App() {
  const [repos, setRepos] = useState([]);
  const [repo, setRepo] = useState("");
  const [brief, setBrief] = useState(EXAMPLE_BRIEF);
  const [projectName, setProjectName] = useState("");
  const [backlog, setBacklog] = useState([]);
  const [selectedBL, setSelectedBL] = useState(null);
  const [extraNotes, setExtraNotes] = useState("");

  const [phase, setPhase] = useState("idle"); // idle | po | engineer
  const [events, setEvents] = useState([]);
  const [summary, setSummary] = useState(null);
  const [indexStatus, setIndexStatus] = useState({ ctx: null, graph: null });
  const [indexRunning, setIndexRunning] = useState({ ctx: false, graph: false });
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
          </dl>
        </section>
      )}

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


function EventLine({ evt }) {
  const type = evt.type || "unknown";
  if (type === "_meta") {
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
