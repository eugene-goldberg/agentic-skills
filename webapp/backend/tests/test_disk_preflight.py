"""Tests for A48 pre-flight disk-free check."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import disk_preflight as dp  # noqa: E402


def _fake_usage(total_gb: float, free_gb: float) -> SimpleNamespace:
    GB = 1024 ** 3
    return SimpleNamespace(
        total=int(total_gb * GB),
        used=int((total_gb - free_gb) * GB),
        free=int(free_gb * GB),
    )


def test_ok_when_free_above_required(tmp_path: Path) -> None:
    with patch("shutil.disk_usage", return_value=_fake_usage(500.0, 100.0)):
        r = dp.check(tmp_path, min_free_gb=5.0, per_bl_gb=1.0, n_bls=10)
    assert r.ok is True
    assert r.reason == ""
    assert abs(r.free_gb - 100.0) < 0.5
    assert r.required_gb == 10.0  # max(5, 1*10)


def test_blocked_when_below_floor(tmp_path: Path) -> None:
    """Free space below the absolute floor (e.g. 5 GB) — not OK even
    if the per-BL estimate × n_bls is small."""
    with patch("shutil.disk_usage", return_value=_fake_usage(500.0, 3.0)):
        r = dp.check(tmp_path, min_free_gb=5.0, per_bl_gb=1.0, n_bls=1)
    assert r.ok is False
    assert "insufficient_disk" in r.reason
    assert "3.0 GB free" in r.reason
    assert r.required_gb == 5.0


def test_blocked_when_below_per_bl_estimate(tmp_path: Path) -> None:
    """Above floor but below per-BL estimate — large sprint, tight host."""
    with patch("shutil.disk_usage", return_value=_fake_usage(500.0, 12.0)):
        r = dp.check(tmp_path, min_free_gb=5.0, per_bl_gb=2.0, n_bls=10)
    assert r.ok is False
    assert r.required_gb == 20.0
    assert "20.0 GB" in r.reason


def test_n_bls_none_uses_conservative_fallback(tmp_path: Path) -> None:
    """An unbounded sprint can't slip under the check via n_bls=None."""
    with patch("shutil.disk_usage", return_value=_fake_usage(500.0, 7.0)):
        r = dp.check(tmp_path, min_free_gb=5.0, per_bl_gb=1.0, n_bls=None)
    # required = max(5, 1 * DEFAULT_N_BLS_FALLBACK=10) = 10
    assert r.required_gb == 10.0
    assert r.n_bls_assumed == dp.DEFAULT_N_BLS_FALLBACK
    assert r.ok is False  # 7 < 10


def test_used_pct_reported_accurately(tmp_path: Path) -> None:
    with patch("shutil.disk_usage", return_value=_fake_usage(100.0, 10.0)):
        r = dp.check(tmp_path, min_free_gb=1.0, per_bl_gb=0.5, n_bls=2)
    # used = 90 GB out of 100 GB = 90.00%
    assert abs(r.used_pct - 90.0) < 0.1


def test_zero_n_bls_treated_as_unknown(tmp_path: Path) -> None:
    with patch("shutil.disk_usage", return_value=_fake_usage(500.0, 50.0)):
        r = dp.check(tmp_path, min_free_gb=1.0, per_bl_gb=1.0, n_bls=0)
    assert r.n_bls_assumed == dp.DEFAULT_N_BLS_FALLBACK


def test_disk_usage_error_returns_ok_with_reason(tmp_path: Path) -> None:
    """Best-effort: a probe failure (transient OSError) must not block
    a legitimate sprint. reason carries the explanation; ok=True so
    the caller-side gate decision doesn't refuse the submission."""
    with patch("shutil.disk_usage", side_effect=OSError("EIO")):
        r = dp.check(tmp_path)
    assert r.ok is True
    assert "disk_usage error" in r.reason


def test_to_event_shape(tmp_path: Path) -> None:
    """Event payload has the keys the SSE consumer expects."""
    with patch("shutil.disk_usage", return_value=_fake_usage(500.0, 100.0)):
        r = dp.check(tmp_path, min_free_gb=5.0, per_bl_gb=1.0, n_bls=3)
    evt = r.to_event()
    for k in (
        "ok", "free_gb", "used_pct", "required_gb", "floor_gb",
        "n_bls_assumed", "per_bl_gb", "target_path", "reason",
    ):
        assert k in evt
    assert evt["ok"] is True
    assert evt["n_bls_assumed"] == 3
    # numeric values are rounded for SSE readability
    assert isinstance(evt["free_gb"], float)
    assert evt["free_gb"] == round(r.free_gb, 2)


def test_exact_boundary_is_ok(tmp_path: Path) -> None:
    """Edge case: free == required → ok=True (the >= boundary)."""
    with patch("shutil.disk_usage", return_value=_fake_usage(500.0, 5.0)):
        r = dp.check(tmp_path, min_free_gb=5.0, per_bl_gb=1.0, n_bls=1)
    assert r.ok is True


def test_defaults_sensible(tmp_path: Path) -> None:
    """Sanity: calling check() with no kwargs uses module defaults."""
    with patch("shutil.disk_usage", return_value=_fake_usage(500.0, 100.0)):
        r = dp.check(tmp_path)
    assert r.floor_gb == dp.DEFAULT_MIN_FREE_GB
    assert r.per_bl_gb == dp.DEFAULT_PER_BL_GB
    assert r.n_bls_assumed == dp.DEFAULT_N_BLS_FALLBACK
