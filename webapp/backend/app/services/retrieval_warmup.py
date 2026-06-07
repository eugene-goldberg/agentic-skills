"""A56 fix part 1 — local retrieval readiness gate.

Before the first agent (the PO) spawns, warm the LOCAL retrieval backend so its
heavy state is ready and the agent never hits the cold "still connecting / first
call may take ~10s to warm up" window that left the PO grounding-blind
(DESIGN_SHORTCOMINGS A56). This spawns ``mcp_servers.warm_probe`` as a bounded
subprocess and retries until it reports the backend warm or an overall timeout
elapses.

EXTERNAL-FREE BY CONSTRUCTION (operator directive 2026-06-07): the probe runs
the same local code path the agents use, and this module forwards ONLY
local-embedding / localhost-Milvus / local-graphify env to it. Azure/OpenAI
keys are deliberately NOT forwarded, so the warm-up can never select a remote
provider even if such keys exist in the environment. Everything is local:
Ollama (127.0.0.1), Milvus (localhost), graphify (on-disk cache).
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

WARM_PROBE_MODULE = "mcp_servers.warm_probe"

# Local-only env keys forwarded to the probe. Azure/OpenAI keys are
# intentionally EXCLUDED — the warm-up must never reach an external service.
_LOCAL_ENV_KEYS = (
    "EMBEDDING_PROVIDER", "EMBEDDING_MODEL", "EMBEDDING_DIMENSION",
    "OLLAMA_HOST", "MILVUS_ADDRESS", "MILVUS_TOKEN",
    "RETRIEVAL_TOOL_BUDGET", "PATH", "HOME",
)


def _backend_dir() -> Path:
    # app/services/retrieval_warmup.py -> backend/
    return Path(__file__).resolve().parents[2]


def build_local_env(target_repo: Path | None,
                    reference_repo: Path | None = None) -> dict[str, str]:
    """Construct the probe's env: PYTHONPATH + repo paths + LOCAL provider keys
    only. Never includes Azure/OpenAI credentials (external-free guarantee)."""
    env: dict[str, str] = {"PYTHONPATH": str(_backend_dir())}
    if target_repo:
        env["RETRIEVAL_TARGET_REPO"] = str(Path(target_repo).resolve())
    if reference_repo:
        env["RETRIEVAL_REFERENCE_REPO"] = str(Path(reference_repo).resolve())
    for k in _LOCAL_ENV_KEYS:
        if k in os.environ:
            env.setdefault(k, os.environ[k])
    return env


async def warm_retrieval(
    target_repo: Path | str,
    *,
    reference_repo: Path | str | None = None,
    timeout: float = 60.0,
    attempt_timeout: float = 25.0,
    retry_sleep: float = 2.0,
    python_bin: str | None = None,
) -> dict:
    """Spawn the local warm-up probe, retrying until it exits 0 (``WARM_OK``) or
    ``timeout`` seconds elapse. Returns
    ``{ok: bool, attempts: int, reason: str, elapsed_s: float}``.

    Advisory: never raises — a warm-up failure must not abort the run (the
    caller warns and proceeds; the post-PO grounding check is the safety net)."""
    python_bin = python_bin or os.environ.get("RETRIEVAL_PYTHON") or sys.executable
    env = build_local_env(
        Path(target_repo) if target_repo else None,
        Path(reference_repo) if reference_repo else None,
    )
    start = time.monotonic()
    attempts = 0
    last = ""
    while time.monotonic() - start < timeout:
        attempts += 1
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                python_bin, "-m", WARM_PROBE_MODULE,
                cwd=str(_backend_dir()), env=env,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout=attempt_timeout)
            if proc.returncode == 0 and b"WARM_OK" in (out or b""):
                return {"ok": True, "attempts": attempts, "reason": "warm",
                        "elapsed_s": round(time.monotonic() - start, 1)}
            last = ((err or out) or b"").decode("utf-8", "replace").strip()[:300] or "probe non-zero exit"
        except asyncio.TimeoutError:
            if proc is not None:
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
            last = f"probe attempt exceeded {attempt_timeout}s"
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"[:300]
        await asyncio.sleep(retry_sleep)
    return {"ok": False, "attempts": attempts, "reason": last or "timeout",
            "elapsed_s": round(time.monotonic() - start, 1)}
