import { useEffect, useRef, useState } from "react";

const EXAMPLE_TASK =
  "Add a /version endpoint to the FastAPI app that returns the current git commit short SHA. Add a test. Commit.";

export function App() {
  const [repos, setRepos] = useState([]);
  const [repo, setRepo] = useState("");
  const [task, setTask] = useState(EXAMPLE_TASK);
  const [events, setEvents] = useState([]);
  const [running, setRunning] = useState(false);
  const [summary, setSummary] = useState(null);
  const abortRef = useRef(null);
  const logBottomRef = useRef(null);

  useEffect(() => {
    fetch("/api/tasks/repos")
      .then((r) => r.json())
      .then((data) => {
        setRepos(data.repos || []);
        if (data.repos?.length) setRepo(data.repos[0].name);
      })
      .catch(() => setRepos([]));
  }, []);

  useEffect(() => {
    logBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  const runTask = async () => {
    if (!repo || !task.trim() || running) return;
    setEvents([]);
    setSummary(null);
    setRunning(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch("/api/tasks/run-stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task, repo }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        const txt = await res.text();
        setEvents([{ type: "_error", error: `HTTP ${res.status}: ${txt}` }]);
        setRunning(false);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() || "";
        for (const frame of frames) {
          const line = frame.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          const payload = line.slice(6);
          try {
            const evt = JSON.parse(payload);
            setEvents((prev) => [...prev, evt]);
            if (evt.type === "done") setSummary(evt);
          } catch {
            setEvents((prev) => [...prev, { type: "_raw", text: payload }]);
          }
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        setEvents((prev) => [...prev, { type: "_error", error: String(err) }]);
      }
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  };

  const cancel = () => abortRef.current?.abort();

  return (
    <div className="page">
      <header>
        <h1>Claude Code Agent Runner</h1>
        <p className="sub">
          Fires the <code>claude</code> CLI against an isolated git worktree, streams every
          tool call, and verifies the agent committed.
        </p>
      </header>

      <section className="form">
        <label>
          Repo
          <select value={repo} onChange={(e) => setRepo(e.target.value)} disabled={running}>
            {repos.length === 0 && <option value="">— no repos found —</option>}
            {repos.map((r) => (
              <option key={r.name} value={r.name}>
                {r.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Task
          <textarea
            value={task}
            onChange={(e) => setTask(e.target.value)}
            rows={5}
            disabled={running}
            placeholder="Describe a single complex task for the agent..."
          />
        </label>
        <div className="actions">
          <button onClick={runTask} disabled={running || !repo || !task.trim()}>
            {running ? "Agent running…" : "Run agent"}
          </button>
          {running && <button onClick={cancel} className="secondary">Cancel</button>}
        </div>
      </section>

      {summary && (
        <section className="summary">
          <h2>✓ Done</h2>
          <dl>
            <dt>Branch</dt><dd><code>{summary.branch}</code></dd>
            <dt>Commit</dt><dd><code>{summary.commit_sha || "(no commit)"}</code></dd>
            <dt>New commits</dt><dd>{summary.new_commits}</dd>
            <dt>Task ID</dt><dd><code>{summary.task_id}</code></dd>
          </dl>
        </section>
      )}

      <section className="log">
        <h2>Stream <span className="count">({events.length})</span></h2>
        {events.length === 0 && !running && <p className="empty">No events yet.</p>}
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

function EventLine({ evt }) {
  const type = evt.type || "unknown";
  if (type === "_meta") {
    return <code className="meta">[meta] {evt.phase} {evt.task_id ? `task=${evt.task_id}` : ""} {evt.branch ? `branch=${evt.branch}` : ""} {evt.exit_code != null ? `exit=${evt.exit_code}` : ""}</code>;
  }
  if (type === "_error") {
    return <span className="error">[error] {evt.error}</span>;
  }
  if (type === "done") {
    return <strong>✓ done — commit {evt.commit_sha?.slice(0, 8) ?? "(none)"}</strong>;
  }
  if (type === "assistant") {
    const content = evt.message?.content;
    const text = Array.isArray(content)
      ? content.map((c) => c.text || (c.type === "tool_use" ? `→ ${c.name}` : "")).filter(Boolean).join(" ")
      : (typeof content === "string" ? content : JSON.stringify(content));
    return <span><b>assistant</b>: {text?.slice(0, 600)}</span>;
  }
  if (type === "user") {
    const content = evt.message?.content;
    const text = Array.isArray(content)
      ? content.map((c) => c.content || c.text || "").filter(Boolean).join(" ")
      : JSON.stringify(content);
    return <span className="dim"><b>tool_result</b>: {text?.slice(0, 200)}</span>;
  }
  if (type === "result") {
    return <strong className="result">result: {evt.result?.slice(0, 600) ?? JSON.stringify(evt).slice(0, 300)}</strong>;
  }
  if (type === "system") {
    return <code className="dim">[system] {evt.subtype || JSON.stringify(evt).slice(0, 100)}</code>;
  }
  return <code>{JSON.stringify(evt).slice(0, 400)}</code>;
}
