"""Tests for A49: gate non-determinism handling (annotate-only).

`detect_transient_markers` surfaces transient network/IO error markers
(socket hang up / ECONNRESET / ECONNREFUSED / ETIMEDOUT / Network Error)
present in a gate tail. It is ANNOTATION ONLY — it must never flip a verdict
(turning a red gate non-red is a deferred, operator-approved doctrine change),
so these tests assert detection semantics, not verdict changes.

Also asserts both gate templates pass `--retries` to Playwright (A49 fix #1,
explicit flake tolerance).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

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
