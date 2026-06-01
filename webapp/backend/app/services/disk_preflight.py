"""A48 pre-flight disk-free check.

Filed 2026-05-31 (ledger entry A48); fix #1 of 4 shipped 2026-06-01.

A sprint launches multiple heavy docker stacks (PRE+POST gate per BL,
acceptance compose, the agent's own claude subprocesses) plus a
growing graphify cache and a Milvus collection. Empirical baseline from
`run-20260531T211839Z-1f47e6` (Client_Portal, 10 BLs): the run filled
the Mac volume from 93% → DiskFull mid-sprint at BL-0003 QA gate; the
underlying postgres-in-docker volume could not extend its data file
because the host had no space left. The orchestrator surfaced the
failure as a misleading SQLAlchemy `PendingRollbackError`; the real
cause `(psycopg.errors.DiskFull) could not extend file` was buried in
the gate's `post_tail` ~3 KB deep.

This module is the pre-flight half of the A48 fix. It queries the
host's free disk space at sprint submission time and returns a
structured assessment the operator (and the orchestrator) can act on.
The router decides whether to refuse the run (HTTP 409) or just emit
an advisory `pre_flight.disk` SSE event; default is advisory so the
behavior is backward-compatible.

Deferred fixes (A48 entries #2-#4): inter-BL volume reaper, DiskFull-
aware classifier in regression_gate, tmpfs-cap override for gate
postgres data dirs. Tracked in DESIGN_SHORTCOMINGS.md.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

# Conservative defaults tuned to the FastAPI template's observed
# footprint. A 10-BL sprint consumed ~16 GB of disposable volumes
# end-to-end on Client_Portal; per-BL average ~1.6 GB (PRE+POST gate
# stacks × ~250 MB pg-data + node_modules layer + image pulls when
# cache is cold). Floor at 5 GB to keep host livable even on tiny
# sprints. Operators override per-call.
DEFAULT_MIN_FREE_GB = 5.0
DEFAULT_PER_BL_GB = 1.0
# Used as the upper bound when caller doesn't supply n_bls (max_bls).
# Real sprints have ranged 2..14; 10 is a defensible conservative cap.
DEFAULT_N_BLS_FALLBACK = 10


@dataclass
class DiskPreflightResult:
    ok: bool
    free_gb: float
    used_pct: float
    required_gb: float
    floor_gb: float
    n_bls_assumed: int
    per_bl_gb: float
    target_path: str
    reason: str  # human-readable; empty when ok=True

    def to_event(self) -> dict:
        """Shape suitable for an SSE `pre_flight.disk` event payload."""
        return {
            "ok": self.ok,
            "free_gb": round(self.free_gb, 2),
            "used_pct": round(self.used_pct, 2),
            "required_gb": round(self.required_gb, 2),
            "floor_gb": round(self.floor_gb, 2),
            "n_bls_assumed": self.n_bls_assumed,
            "per_bl_gb": round(self.per_bl_gb, 2),
            "target_path": self.target_path,
            "reason": self.reason,
        }


def check(
    target_path: Path,
    *,
    min_free_gb: float = DEFAULT_MIN_FREE_GB,
    per_bl_gb: float = DEFAULT_PER_BL_GB,
    n_bls: int | None = None,
) -> DiskPreflightResult:
    """Inspect the host's free space on the volume holding ``target_path``.

    Parameters
    ----------
    target_path
        Any path on the target volume (typically the brownfield repo
        root). ``shutil.disk_usage`` reads the filesystem this path
        sits on.
    min_free_gb
        Hard floor: a run is never considered OK if free space is
        below this absolute number, regardless of how few BLs it
        plans to run.
    per_bl_gb
        Estimated additional disk consumed per BL during the run.
        Multiplied by ``n_bls`` to compute the per-sprint estimate.
    n_bls
        Number of BLs the sprint expects to execute. When ``None``,
        falls back to ``DEFAULT_N_BLS_FALLBACK`` (conservative
        upper bound) so an unbounded sprint can't slip under the
        check.

    Returns
    -------
    A ``DiskPreflightResult`` with ``ok=True`` iff free space ≥
    ``required_gb = max(min_free_gb, per_bl_gb * effective_n_bls)``.
    Best-effort: on any OS error reading disk_usage, returns
    ``ok=True`` with ``reason="<disk_usage error: ...>"`` so a
    transient probe failure doesn't block a legitimate sprint.
    """
    effective_n_bls = n_bls if (n_bls and n_bls > 0) else DEFAULT_N_BLS_FALLBACK
    required_gb = max(min_free_gb, per_bl_gb * effective_n_bls)

    try:
        usage = shutil.disk_usage(str(target_path))
    except OSError as exc:
        return DiskPreflightResult(
            ok=True,
            free_gb=0.0, used_pct=0.0,
            required_gb=required_gb, floor_gb=min_free_gb,
            n_bls_assumed=effective_n_bls, per_bl_gb=per_bl_gb,
            target_path=str(target_path),
            reason=f"<disk_usage error: {exc}; pre-flight skipped>",
        )

    GB = 1024 ** 3
    free_gb = usage.free / GB
    used_pct = (usage.used / usage.total) * 100.0 if usage.total else 0.0

    ok = free_gb >= required_gb
    if ok:
        reason = ""
    else:
        reason = (
            f"insufficient_disk: {free_gb:.1f} GB free; need "
            f"{required_gb:.1f} GB (floor {min_free_gb:.1f} GB, "
            f"+{per_bl_gb:.1f} GB × {effective_n_bls} BLs); host at "
            f"{used_pct:.1f}% capacity. Free disk before submitting or "
            f"opt out via enforce_disk_preflight=false. Recommended: "
            f"`docker system prune -af --volumes` recovers ~5–15 GB on "
            f"a stale daemon."
        )
    return DiskPreflightResult(
        ok=ok,
        free_gb=free_gb, used_pct=used_pct,
        required_gb=required_gb, floor_gb=min_free_gb,
        n_bls_assumed=effective_n_bls, per_bl_gb=per_bl_gb,
        target_path=str(target_path),
        reason=reason,
    )
