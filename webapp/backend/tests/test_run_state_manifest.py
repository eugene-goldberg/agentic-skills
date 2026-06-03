"""ABL-0020 Batch B — per-run doctrine manifest in A7 run state.

Verifies write_checkpoint persists the doctrine_manifest snapshot (the
rule-state record ABL-0017 Stage-2 efficacy joins against bl_outcomes), and
that it is backward compatible (omitting it loads cleanly).

Uses ORCH_STATE_DIR to redirect the state dir to tmp_path so the real
.orchestrator-state is never touched.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _fresh_run_state(tmp_path, monkeypatch):
    """Point run_state's STATE_DIR/DONE_DIR at tmp_path without a global
    reload (auto-reverted by monkeypatch) so the real .orchestrator-state is
    never touched and no cross-test contamination occurs."""
    import app.services.run_state as rs
    state = tmp_path / "state"
    monkeypatch.setattr(rs, "STATE_DIR", state)
    monkeypatch.setattr(rs, "DONE_DIR", state / "done")
    return rs


def _started():
    return datetime(2026, 6, 3, tzinfo=timezone.utc)


def test_checkpoint_persists_doctrine_manifest(tmp_path, monkeypatch) -> None:
    rs = _fresh_run_state(tmp_path, monkeypatch)
    manifest = {"harness_sha": "abc123", "rules": [{"id": "R5", "enforced": True},
                                                    {"id": "R9", "enforced": False}]}
    path = rs.write_checkpoint(
        run_id="run-x", repo="repo", brief_hash="h", started_at=_started(),
        current_bl="BL-0001", bl_outcomes=[], doctrine_manifest=manifest,
    )
    data = json.loads(Path(path).read_text())
    assert data["doctrine_manifest"] == manifest
    assert data["doctrine_manifest"]["harness_sha"] == "abc123"


def test_checkpoint_manifest_defaults_null(tmp_path, monkeypatch) -> None:
    """Backward compat: a caller that omits the manifest writes null, not a
    KeyError, and old readers stay happy."""
    rs = _fresh_run_state(tmp_path, monkeypatch)
    path = rs.write_checkpoint(
        run_id="run-y", repo="repo", brief_hash="h", started_at=_started(),
        current_bl=None, bl_outcomes=[],
    )
    data = json.loads(Path(path).read_text())
    assert data["doctrine_manifest"] is None


def test_manifest_survives_terminate(tmp_path, monkeypatch) -> None:
    rs = _fresh_run_state(tmp_path, monkeypatch)
    manifest = {"harness_sha": "deadbee", "rules": [{"id": "R15", "enforced": True}]}
    rs.write_checkpoint(
        run_id="run-z", repo="repo", brief_hash="h", started_at=_started(),
        current_bl="BL-0002", bl_outcomes=[], doctrine_manifest=manifest,
    )
    done = rs.mark_terminated("run-z", "sprint_complete")
    data = json.loads(Path(done).read_text())
    assert data["doctrine_manifest"] == manifest
    assert data["status"] == "sprint_complete"


def test_real_manifest_from_doctrine_spec_persists(tmp_path, monkeypatch) -> None:
    """End-to-end shape: the actual doctrine_spec.manifest() persists and
    carries the canonical rule set + the R9 gap."""
    rs = _fresh_run_state(tmp_path, monkeypatch)
    from app.services import doctrine_spec as ds
    manifest = ds.manifest()
    manifest["harness_sha"] = "sha-test"
    path = rs.write_checkpoint(
        run_id="run-real", repo="repo", brief_hash="h", started_at=_started(),
        current_bl="BL-0001", bl_outcomes=[], doctrine_manifest=manifest,
    )
    data = json.loads(Path(path).read_text())
    ids = {e["id"] for e in data["doctrine_manifest"]["rules"]}
    assert ds.CANONICAL_RULE_IDS <= ids
    r9 = next(e for e in data["doctrine_manifest"]["rules"] if e["id"] == "R9")
    assert r9["enforced"] is False
