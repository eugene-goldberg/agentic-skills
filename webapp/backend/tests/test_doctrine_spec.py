"""ABL-0020 Batch A — the I-2 doctrine-spec meta-test.

I-2's mandate: "every doctrine entry has at least one enforcement point AND
a callable check. Adding a new R-rule without enforcement fails CI.
Documenting a rule that no code enforces is a build failure."

This file is that meta-test, pragmatically realized:
- enforcement_point ∈ ALLOWED;
- enforced rule → check_ref present AND resolvable to real code (the
  "callable check" teeth);
- unenforced rule → must be an explicit, tracked gap (KNOWN_GAPS);
- the registry covers the canonical rule set (a rule in prose but not the
  registry fails here);
- targeted_failure_class (where set) is a valid I-6 class.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import doctrine_spec as ds  # noqa: E402


def test_ids_unique() -> None:
    ids = [r.id for r in ds.DOCTRINE_SPEC]
    assert len(ids) == len(set(ids)), f"duplicate rule ids: {ids}"


def test_every_rule_has_valid_enforcement_point() -> None:
    for r in ds.DOCTRINE_SPEC:
        assert r.enforcement_point in ds.ALLOWED_ENFORCEMENT_POINTS, \
            f"{r.id}: bad enforcement_point {r.enforcement_point!r}"


def test_enforced_rule_has_check_ref() -> None:
    """I-2: an enforced rule with no check is a build failure."""
    for r in ds.DOCTRINE_SPEC:
        if r.enforced:
            assert r.check_ref, f"{r.id} is enforced but names no check_ref"


def test_enforced_check_refs_resolve_to_real_code() -> None:
    """The teeth of I-2's 'callable check': every enforced rule's check_ref
    must import and resolve to an actual symbol."""
    for r in ds.DOCTRINE_SPEC:
        if not r.enforced:
            continue
        sym = ds.resolve_check(r)
        assert sym is not None, f"{r.id}: check_ref {r.check_ref!r} resolved to None"


def test_unenforced_rules_are_explicit_gaps() -> None:
    """A rule that no code enforces must be a tracked gap, never silent."""
    for r in ds.DOCTRINE_SPEC:
        if not r.enforced:
            assert r.id in ds.KNOWN_GAPS, \
                f"{r.id} is unenforced but not in KNOWN_GAPS (silent gap)"
            assert r.check_ref is None


def test_known_gaps_are_actually_in_registry_and_unenforced() -> None:
    for gap_id in ds.KNOWN_GAPS:
        r = ds.by_id(gap_id)
        assert r is not None, f"KNOWN_GAPS lists {gap_id} but it's not registered"
        assert r.enforced is False


def test_registry_covers_canonical_rule_set() -> None:
    """A rule added to the prose tables but not the registry fails here."""
    registered = {r.id for r in ds.DOCTRINE_SPEC}
    missing = ds.CANONICAL_RULE_IDS - registered
    assert not missing, f"canonical rules missing from registry: {sorted(missing)}"


def test_targeted_failure_class_valid_when_set() -> None:
    for r in ds.DOCTRINE_SPEC:
        if r.targeted_failure_class is not None:
            assert r.targeted_failure_class in ds.I6_FAILURE_CLASSES, \
                f"{r.id}: bad targeted_failure_class {r.targeted_failure_class!r}"


# ── accessors + manifest ────────────────────────────────────────────────────


def test_by_id_and_enforced_rules() -> None:
    assert ds.by_id("R15").id == "R15"
    assert ds.by_id("nope") is None
    enforced = ds.enforced_rules()
    assert all(r.enforced for r in enforced)
    assert ds.by_id("R9") not in enforced  # the gap is excluded


def test_manifest_shape() -> None:
    m = ds.manifest()
    assert "rules" in m
    ids = {e["id"] for e in m["rules"]}
    assert ds.CANONICAL_RULE_IDS <= ids
    r9 = next(e for e in m["rules"] if e["id"] == "R9")
    assert r9["enforced"] is False


# ── ABL-0020 Batch C: registry ↔ prose consistency (the source-of-truth guard) ──


def _parse_claude_rule_ids() -> set[str]:
    """Extract the rule ids from CLAUDE.md's R-rules table. Normalizes
    'Tier 1.5' -> 'Tier1.5' to match the registry id convention."""
    claude = ROOT.parents[1] / "CLAUDE.md"   # webapp/backend -> agentic-skills root
    lines = claude.read_text(encoding="utf-8").splitlines()
    ids: set[str] = set()
    in_table = False
    for line in lines:
        if line.strip().startswith("| Rule | Floor | Enforcement point"):
            in_table = True
            continue
        if in_table:
            s = line.strip()
            if not s.startswith("|"):
                break  # table ended
            if s.startswith("|---") or s.startswith("| ---"):
                continue
            cell = s.split("|")[1].strip()
            if cell and cell.lower() != "rule":
                ids.add(cell.replace(" ", ""))   # "Tier 1.5" -> "Tier1.5"
    return ids


def test_registry_matches_claude_prose_table() -> None:
    """The registry is the source of truth — but it must not silently drift
    from the CLAUDE.md R-rules table the operator reads. A rule in one but
    not the other fails here (governance guard)."""
    prose = _parse_claude_rule_ids()
    registry = {r.id for r in ds.DOCTRINE_SPEC}
    assert prose, "could not parse CLAUDE.md R-rules table (format changed?)"
    in_prose_not_registry = prose - registry
    in_registry_not_prose = registry - prose
    assert not in_prose_not_registry, \
        f"rules in CLAUDE.md but not the registry: {sorted(in_prose_not_registry)}"
    assert not in_registry_not_prose, \
        f"rules in the registry but not CLAUDE.md: {sorted(in_registry_not_prose)}"
