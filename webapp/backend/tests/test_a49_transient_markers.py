"""Tests for A49: gate non-determinism handling.

`detect_transient_markers` surfaces suspected-transient markers — network/IO
errors (socket hang up / ECONNRESET / ECONNREFUSED / ETIMEDOUT / Network Error)
AND Playwright timing flakes (test-timeout / element-not-stable / browser-closed)
— present in a gate tail.

A49 fix #2 (2026-06-06, operator-approved) makes these markers *act* (no longer
annotate-only): `run_gate` arbitrates a suspected-transient red via (1) a
same-SHA green memory and (2) a single gate re-sample, never blind-flipping a
red to green. These tests assert both the detection semantics and the
arbitration logic, plus the `reset_target_to` rollback primitive.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import regression_gate as g  # noqa: E402
from app.services.regression_gate import detect_transient_markers  # noqa: E402


# Verbatim shape of the A49 invoice-run reset-password flake.
SAMPLE_SOCKET_HANGUP = (
    "  1) [chromium] › tests/reset-password.spec.ts:30:1 › Reset password ───\n"
    "    Error: socket hang up\n"
    "      at ClientRequest.<anonymous>\n"
    "  1 failed\n"
)


def test_detects_socket_hang_up() -> None:
    out = detect_transient_markers(SAMPLE_SOCKET_HANGUP)
    assert any("socket hang up" in m.lower() for m in out)


def test_detects_each_marker() -> None:
    for marker in ("ECONNRESET", "ECONNREFUSED", "ETIMEDOUT", "Network Error"):
        tail = f"    Error: request failed with {marker} during teardown\n"
        out = detect_transient_markers(tail)
        assert out, f"{marker} not detected"
        assert marker.lower() in out[0].lower()


def test_dedup_and_order() -> None:
    tail = (
        "socket hang up\n"
        "ECONNRESET\n"
        "another socket hang up here\n"  # duplicate
    )
    out = detect_transient_markers(tail)
    lowered = [m.lower() for m in out]
    assert lowered == ["socket hang up", "econnreset"]


def test_empty_and_clean_input() -> None:
    assert detect_transient_markers("") == []
    assert detect_transient_markers("3 passed, 0 failed\nall green\n") == []


def test_no_false_positive_on_substrings() -> None:
    # Word-boundary anchored markers should not match unrelated identifiers.
    tail = "def test_econnreset_handler():  # named after the error, not the error\n"
    # 'econnreset' as a bare word DOES match (boundary on both sides of token);
    # this asserts we don't match when embedded without boundaries.
    assert detect_transient_markers("myECONNRESETvar = 1\n") == []


def test_both_gate_templates_pass_retries() -> None:
    webapp_tpl = ROOT / "app" / "templates" / "regression_gate.sh"
    assert webapp_tpl.exists()
    assert "--retries" in webapp_tpl.read_text(encoding="utf-8")


# ── A49 fix #2: Playwright timing-flake markers ──────────────────────────────

def test_detects_playwright_test_timeout() -> None:
    assert detect_transient_markers("Test timeout of 90000ms exceeded.")


def test_detects_element_stability() -> None:
    assert detect_transient_markers(
        "waiting for element to be visible, enabled and stable")


def test_detects_dark_mode_flake_verbatim() -> None:
    # The exact failure that aborted item-comments BL-0001 (QA re-gate of a tree
    # that had gated green an hour earlier).
    tail = (
        "  1) [chromium] › tests/user-settings.spec.ts:224:1 › "
        "Selected mode is preserved across sessions ───\n"
        "    Test timeout of 90000ms exceeded.\n"
        "    Error: locator.click: Test timeout of 90000ms exceeded.\n"
        "    - waiting for element to be visible, enabled and stable\n"
        "  1 failed\n"
    )
    assert detect_transient_markers(tail)


# ── A49 fix #2: run_gate arbitration (re-run + same-SHA green memory) ─────────

def _result(kind: str, markers: list[str] | None = None, reason: str = "r") -> dict:
    return {"kind": kind, "ok": kind == "green", "reason": reason,
            "transient_markers": markers or [], "regressions": [],
            "new_failures": [], "pre": {}, "post": {}}


class _Seq:
    """Scripted async stand-in for _run_gate_once; returns the next result per call."""
    def __init__(self, results: list[dict]) -> None:
        self.results = results
        self.calls = 0

    async def __call__(self, *a, **k) -> dict:
        r = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        return dict(r)


async def _fake_revparse(args, cwd=None):  # _git(["rev-parse", ...]) → (code, out)
    return (0, "deadbeefcafef00d\n")


def _patch(monkeypatch, seq: _Seq) -> None:
    monkeypatch.setattr(g, "_run_gate_once", seq)
    monkeypatch.setattr(g, "_git", _fake_revparse)


def test_rerun_recovers_transient_red(monkeypatch) -> None:
    """red(transient) → re-run green ⇒ recovered to green."""
    seq = _Seq([_result("regressed", ["Test timeout of 90000ms exceeded"]),
                _result("green")])
    _patch(monkeypatch, seq)
    g.clear_green_shas("run-rerun")
    res = asyncio.run(g.run_gate(Path("/x"), "agent", "target", run_id="run-rerun"))
    assert res["kind"] == "green"
    assert res.get("a49_recovered") == "re-run green"
    assert seq.calls == 2  # initial + one re-sample


def test_rerun_reproduced_stays_red(monkeypatch) -> None:
    """red(transient) → re-run red ⇒ real failure, not masked."""
    seq = _Seq([_result("regressed", ["socket hang up"]),
                _result("regressed", ["socket hang up"])])
    _patch(monkeypatch, seq)
    g.clear_green_shas("run-repro")
    res = asyncio.run(g.run_gate(Path("/x"), "agent", "target", run_id="run-repro"))
    assert res["kind"] == "regressed"
    assert res.get("a49_reran_reproduced") is True
    assert seq.calls == 2


def test_same_sha_green_memory_shortcircuits(monkeypatch) -> None:
    """A prior green on the identical SHA recovers a later transient red WITHOUT
    paying for a re-run."""
    seq = _Seq([_result("green"),
                _result("inconclusive", ["Test timeout of 1ms exceeded"])])
    _patch(monkeypatch, seq)
    g.clear_green_shas("run-sha")
    r1 = asyncio.run(g.run_gate(Path("/x"), "agent", "target", run_id="run-sha"))
    assert r1["kind"] == "green"
    r2 = asyncio.run(g.run_gate(Path("/x"), "agent", "target", run_id="run-sha"))
    assert r2["kind"] == "green"
    assert r2.get("a49_recovered") == "same-SHA green"
    assert seq.calls == 2  # one per run_gate; NO third (re-run) call


def test_non_transient_red_is_not_rerun(monkeypatch) -> None:
    """A red with no transient markers is taken at face value — no re-sample."""
    seq = _Seq([_result("regressed", markers=[])])
    _patch(monkeypatch, seq)
    g.clear_green_shas("run-real")
    res = asyncio.run(g.run_gate(Path("/x"), "agent", "target", run_id="run-real"))
    assert res["kind"] == "regressed"
    assert "a49_recovered" not in res
    assert seq.calls == 1


def test_allow_rerun_false_disables_resample(monkeypatch) -> None:
    seq = _Seq([_result("regressed", ["socket hang up"])])
    _patch(monkeypatch, seq)
    g.clear_green_shas("run-norerun")
    res = asyncio.run(g.run_gate(Path("/x"), "agent", "target",
                                 run_id="run-norerun", _allow_rerun=False))
    assert res["kind"] == "regressed"
    assert seq.calls == 1


def test_clear_green_shas_isolates_runs(monkeypatch) -> None:
    seq = _Seq([_result("green"),
                _result("inconclusive", ["socket hang up"])])
    _patch(monkeypatch, seq)
    g.clear_green_shas("run-iso")
    asyncio.run(g.run_gate(Path("/x"), "agent", "target", run_id="run-iso"))
    g.clear_green_shas("run-iso")  # memory wiped → later red must re-run, not shortcut
    res = asyncio.run(g.run_gate(Path("/x"), "agent", "target", run_id="run-iso"))
    # second call's _run_gate_once returns inconclusive(transient) then (clamped)
    # the same → re-run reproduced → stays inconclusive (NOT same-SHA recovered)
    assert res.get("a49_recovered") != "same-SHA green"


# ── Auto-merge atomicity: reset_target_to rollback primitive ─────────────────

def _git_sync(repo: Path, *args: str) -> None:
    import subprocess
    subprocess.run(["git", *args], cwd=repo, check=True,
                   capture_output=True)


def test_reset_target_to_rolls_back_branch(tmp_path) -> None:
    from app.services.git_worktree import rev_parse, reset_target_to
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_sync(repo, "init", "-q")
    _git_sync(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    _git_sync(repo, "config", "user.email", "t@t")
    _git_sync(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("A")
    _git_sync(repo, "add", "-A")
    _git_sync(repo, "commit", "-qm", "A")
    sha_a = asyncio.run(rev_parse(repo, "main"))
    (repo / "a.txt").write_text("B")
    _git_sync(repo, "add", "-A")
    _git_sync(repo, "commit", "-qm", "B")
    sha_b = asyncio.run(rev_parse(repo, "main"))
    assert sha_a and sha_b and sha_a != sha_b

    res = asyncio.run(reset_target_to(repo, "main", sha_a))
    assert res["ok"] is True
    assert asyncio.run(rev_parse(repo, "main")) == sha_a   # ref rolled back
    assert (repo / "a.txt").read_text() == "A"             # working tree too
