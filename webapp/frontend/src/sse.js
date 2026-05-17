/**
 * Stream SSE frames from a POST request body. The webapp's endpoints all
 * accept POST + JSON and respond with text/event-stream, so we can't use the
 * stock EventSource (which only does GET). Returns an async iterator of
 * parsed JSON events.
 */
export async function* streamPost(url, body, signal) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    const txt = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${txt}`);
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
      try {
        yield JSON.parse(line.slice(6));
      } catch {
        yield { type: "_raw", text: line.slice(6) };
      }
    }
  }
}
