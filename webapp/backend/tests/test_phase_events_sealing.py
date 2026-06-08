"""A13 completion (Stage 2 prerequisite) — every orchestrator phase event the
crew constructs must be SEALED into the per-agent ``phase_events.jsonl``.

A13 shipped the ``phase_events.jsonl`` mechanism but with partial coverage: the
``_ptag`` calls that build ``doctrine_check`` forwarded ``trace=trace`` (and
sealed), while ``bl_tests`` / ``regression_gate`` / merge events dropped it and
silently never reached the sealed trace. Stage 2 (closed-loop doctrine efficacy)
must reconstruct "which rule fired in which run" from the sealed archive alone,
so EVERY enforcement/disposition phase event must seal.

``_ptag``'s sole purpose is sealing (vs ``_tag`` which only annotates). So the
invariant is simply: **every ``_ptag(...)`` call forwards a ``trace`` keyword.**
A ``_ptag`` without ``trace`` is always a latent A13 regression — this test
fails red on it (driving + pinning the fix), so a future copy-paste that forgets
the kwarg can't silently drop a rule firing again.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ORCH = ROOT / "app" / "services" / "orchestrator.py"


def _ptag_calls_without_trace(src: str) -> list[tuple[int, str]]:
    """Return (lineno, phase) for every _ptag(...) call that does NOT forward a
    `trace` keyword. `phase` is the literal phase value when statically known."""
    tree = ast.parse(src)
    offenders: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Name) and fn.id == "_ptag"):
            continue
        has_trace = any(kw.arg == "trace" for kw in node.keywords)
        if has_trace:
            continue
        # extract the phase literal from the first arg dict (best-effort)
        phase = "?"
        if node.args and isinstance(node.args[0], ast.Dict):
            for k, v in zip(node.args[0].keys, node.args[0].values):
                if isinstance(k, ast.Constant) and k.value == "phase" and isinstance(v, ast.Constant):
                    phase = v.value
        offenders.append((node.lineno, phase))
    return offenders


def test_every_ptag_call_forwards_trace() -> None:
    """The A13 completeness invariant. If this fails, the listed _ptag calls
    silently drop their phase event from the sealed trace (Stage-2 blind spots)."""
    offenders = _ptag_calls_without_trace(ORCH.read_text(encoding="utf-8"))
    assert offenders == [], (
        "A13: these _ptag() calls don't forward trace= so their phase event is "
        "never sealed into phase_events.jsonl:\n"
        + "\n".join(f"  orchestrator.py:{ln}  phase={ph!r}" for ln, ph in offenders)
    )


def test_negative_guard_ptag_without_trace_does_not_seal() -> None:
    """Pins the exact regression: a phase _ptag WITHOUT trace must NOT seal;
    WITH trace it MUST. (Mirrors the meta-agent proposal's negative guard.)"""
    from app.services import orchestrator as orch

    class _SpyTrace:
        def __init__(self): self.events = []
        def write_phase_event(self, e): self.events.append(e)

    ev = {"type": "_meta", "phase": "bl_tests", "kind": "green"}
    spy = _SpyTrace()
    orch._ptag(dict(ev), "engineer", "BL-X")                 # no trace
    assert spy.events == []
    orch._ptag(dict(ev), "engineer", "BL-X", trace=spy)      # with trace
    assert len(spy.events) == 1 and spy.events[0]["phase"] == "bl_tests"


def test_phase_events_schema_header_and_reader(tmp_path, monkeypatch) -> None:
    """A13 mitigation #2: phase_events.jsonl leads with a schema-version header;
    the canonical reader skips it and returns the records in order."""
    import json
    from app.services import traces
    monkeypatch.setattr(traces, "TRACES_ROOT", tmp_path)
    tw = traces.TraceWriter(repo="r", role="engineer", bl_id="BL-1")
    tw.write_phase_event({"type": "_meta", "phase": "bl_tests", "kind": "green"})
    tw.write_phase_event({"type": "_meta", "phase": "merge_to_target", "ok": True})
    raw = (tw.dir / "phase_events.jsonl").read_text().splitlines()
    assert json.loads(raw[0]) == {"_schema_version": traces.PHASE_EVENTS_SCHEMA_VERSION}
    recs = traces.read_phase_events(tw.dir)
    assert [r["phase"] for r in recs] == ["bl_tests", "merge_to_target"]  # header skipped


def test_read_phase_events_missing_file_is_empty(tmp_path) -> None:
    from app.services import traces
    assert traces.read_phase_events(tmp_path) == []
