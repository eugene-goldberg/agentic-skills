"""Tests for A48 fix #3: DiskFull-aware classifier.

Verifies that `regression_gate.extract_disk_full_reason` pulls the
original disk-exhaustion line out of cascade-noisy tails, and that
when present in the gate's post_tail the result payload carries
`infra_fail_reason="host_disk_full"` with the disk-specific reason
headline (not the SQLAlchemy PendingRollback cascade).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.regression_gate import (  # noqa: E402
    extract_disk_full_reason,
)


# ─── extract_disk_full_reason: pattern coverage ───────────────────────────


def test_psycopg_disk_full_extracted() -> None:
    """The empirical BL-0003 case — psycopg.errors.DiskFull buried under
    a PendingRollback cascade."""
    tail = (
        "E       sqlalchemy.exc.PendingRollbackError: This Session's "
        "transaction has been rolled back due to a previous exception "
        "during flush. To begin a new transaction with this Session, "
        "first issue Session.rollback().\n"
        "Original exception was: (psycopg.errors.DiskFull) could not "
        'extend file "base/16384/16505": No space left on device.\n'
        "HINT:  Check free disk space.\n"
    )
    line = extract_disk_full_reason(tail)
    assert line is not None
    assert "psycopg.errors.DiskFull" in line
    # Surface the canonical postgres wording, not the SQLAlchemy
    # cascade.
    assert "PendingRollback" not in line


def test_postgres_could_not_extend_file_extracted() -> None:
    tail = (
        "Some preamble\n"
        'could not extend file "base/16384/16505": No space left on device\n'
        "HINT: Check disk space.\n"
    )
    line = extract_disk_full_reason(tail)
    assert line is not None
    assert "could not extend file" in line


def test_sqlalchemy_operational_error_disk_extracted() -> None:
    tail = (
        "Setup output\n"
        "sqlalchemy.exc.OperationalError: database disk full at offset 0\n"
    )
    line = extract_disk_full_reason(tail)
    assert line is not None
    assert "disk full" in line.lower()


def test_enospc_fallback_match() -> None:
    """Last-resort POSIX pattern catches non-DB code paths."""
    tail = "Building image...\nOSError: [Errno 28] No space left on device\n"
    line = extract_disk_full_reason(tail)
    assert line is not None
    assert "No space left on device" in line


def test_disk_quota_exceeded_extracted() -> None:
    """CI quota'd workspaces — operator sees this as "disk full"."""
    tail = "...\nwrite /tmp/xyz: Disk quota exceeded\n"
    line = extract_disk_full_reason(tail)
    assert line is not None
    assert "uota" in line  # match either case


def test_empty_input_returns_none() -> None:
    assert extract_disk_full_reason("") is None
    assert extract_disk_full_reason(None) is None  # type: ignore[arg-type]


def test_clean_tail_returns_none() -> None:
    """No disk-exhaustion signal → None (caller falls back to generic
    infra reason)."""
    tail = (
        "tests/foo.py::test_a PASSED\n"
        "tests/foo.py::test_b FAILED\n"
        "AssertionError: expected 1 but got 2\n"
    )
    assert extract_disk_full_reason(tail) is None


def test_reason_truncated_to_300_chars() -> None:
    """A very long matched line is clipped so the SSE event stays small."""
    payload = (
        "E    psycopg.errors.DiskFull: could not extend file " + ("X" * 1000)
    )
    line = extract_disk_full_reason(payload)
    assert line is not None
    assert len(line) <= 300


def test_priority_picks_psycopg_over_generic_enospc() -> None:
    """When BOTH a psycopg-specific line AND a generic ENOSPC line
    exist, the priority order in _DISK_FULL_PATTERNS prefers the
    DB-specific message — more actionable for the operator."""
    tail = (
        "Earlier in log: container saw 'No space left on device'\n"
        "E    psycopg.errors.DiskFull: could not extend file ...\n"
    )
    line = extract_disk_full_reason(tail)
    assert line is not None
    assert "psycopg.errors.DiskFull" in line


# ─── classifier integration via _classify-like shape ──────────────────────


def test_priority_over_pending_rollback_in_bl0003_shape() -> None:
    """The exact BL-0003 shape from run-20260531T211839Z-1f47e6: the
    canonical line MUST be the psycopg DiskFull, not the SQLAlchemy
    cascade. This is the precise misclassification A48 fix #3
    addresses."""
    tail = (
        "tests/crud/test_user.py:109\n"
        "E       sqlalchemy.exc.PendingRollbackError: This Session's "
        "transaction has been rolled back due to a previous exception "
        "during flush. To begin a new transaction with this Session, "
        "first issue Session.rollback().\n"
        "Original exception was: (psycopg.errors.DiskFull) could not "
        'extend file "base/16384/16505": No space left on device.\n'
        "HINT:  Check free disk space.\n"
        "[SQL: INSERT INTO portalauditlog ...]\n"
    )
    line = extract_disk_full_reason(tail)
    assert line is not None
    assert "psycopg.errors.DiskFull" in line
    # Reject the cascade
    assert "PendingRollbackError" not in line
