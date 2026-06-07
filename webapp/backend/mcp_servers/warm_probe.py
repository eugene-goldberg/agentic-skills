"""A56 fix — local, external-free warm-up probe for the retrieval backend.

Spawned by ``app.services.retrieval_warmup.warm_retrieval`` BEFORE the first
agent (the PO) so the LOCAL stdio retrieval server's heavy state is warm:
the embedding model (``bge-m3`` via local Ollama) is loaded into memory, the
local Milvus collection is opened, and the on-disk graphify cache is built/loaded.
This collapses the "still connecting / first call may take ~10s to warm up"
window that left the first agent grounding-blind (DESIGN_SHORTCOMINGS A56).

LOCAL ONLY — by construction this probe never reaches an external service:
- it calls the exact same ``mcp_servers.retrieval_server`` tool functions the
  agents use (``target_status`` + one ``semantic_search`` against the target);
- the caller forwards only local-embedding / localhost-Milvus / local-graphify
  env (``EMBEDDING_PROVIDER=Ollama``, ``OLLAMA_HOST=127.0.0.1``,
  ``MILVUS_ADDRESS=localhost``). Azure/OpenAI keys are NOT forwarded, so even if
  they exist in the parent environment the warm-up cannot select a remote
  provider.

Contract: prints ``WARM_OK`` and exits 0 when both calls return without a hard
error; prints ``WARM_FAIL …`` to stderr and exits 1 otherwise. The caller
retries until exit 0 or an overall timeout.
"""
from __future__ import annotations

import sys


def _call(fn, *args, **kwargs):
    """Call a retrieval tool function. FastMCP's ``@mcp.tool()`` returns the
    original function in the current SDK, but be defensive: unwrap a tool object
    that exposes ``.fn``."""
    target = getattr(fn, "fn", fn)
    return target(*args, **kwargs)


def main() -> int:
    # Env (RETRIEVAL_TARGET_REPO, EMBEDDING_*, OLLAMA_HOST, MILVUS_*) is already
    # set by the caller. Importing the server builds its ``sources`` map from
    # that env and registers the tools — it does NOT start the stdio loop.
    try:
        import mcp_servers.retrieval_server as r
    except Exception as exc:  # noqa: BLE001
        print(f"WARM_FAIL import: {exc}", file=sys.stderr)
        return 1
    try:
        ts = _call(r.target_status)
        if isinstance(ts, dict) and ts.get("ok") is False:
            print(f"WARM_FAIL target_status: {ts}", file=sys.stderr)
            return 1
        # Force the heavy local warm-up: embed-model load + Milvus collection
        # open + index warm-up. A miss (0 hits) is a SUCCESSFUL warm-up; only a
        # hard error / timeout means the server is not yet ready → retry.
        ss = _call(r.semantic_search, "warm up retrieval grounding", k=1, source="target")
        if isinstance(ss, dict) and ss.get("ok") is False:
            err = str(ss.get("error", "")).lower()
            if "timeout" in err or "warm" in err or "connect" in err:
                print(f"WARM_FAIL semantic_search not ready: {ss}", file=sys.stderr)
                return 1
        print("WARM_OK")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"WARM_FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
