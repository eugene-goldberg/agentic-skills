"""ABL-0017 Stage 2 — closed-loop doctrine efficacy aggregator.

A13 made "which rule fired in which run" reconstructable from the sealed
archive (per-agent ``phase_events.jsonl`` + explicit ``rule_id`` on streaming
kills). This module JOINS those sealed rule-firings against the per-run
``doctrine_manifest`` (which rules were enforced + harness_sha) and the
per-BL ``bl_outcomes``, to answer: **is each rule earning its keep?**

What the sealed data supports TODAY (solid signal):
  - **Fire rate** per rule — how often a rule actually catches a violation
    (vs runs clean). A rule that never fires across many runs is a
    retirement candidate (or the crew is simply clean on this target).
  - **Per-run firing + outcome tables** — self-contained from the archive.

What needs MORE data / enforcement variation (scaffolded, flagged low-conf):
  - **Targeted-failure-class reduction** — "did class C drop after rule R
    (targeting C) was enforced?" requires runs where R's enforcement TOGGLES
    (the manifest is currently static) or a long longitudinal series. We
    surface each rule's ``targeted_failure_class`` + a per-run outcome
    distribution so the trend is observable as runs accumulate, but we do NOT
    claim causal efficacy from n≈1. Honesty over a dramatic-but-unfounded score.

Open-loop → closed-loop: the retirement candidates this produces are the input
to the doctrine-meta-agent's (future) ``retire`` Direction. I-7 stays
operator-gated — this MEASURES; it never changes doctrine.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.services import doctrine_spec as _spec
from app.services import traces as _traces

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_STATE_DIR = _BACKEND_DIR / ".orchestrator-state"
_ARCHIVE_DIR = _BACKEND_DIR / "traces_archive"

# Phase → the rule it enforces, when the phase doesn't carry an explicit
# ``rule_id`` (streaming kills do). doctrine_check is the post_validation
# aggregate (R5/R5b/R7/R9/R12); we refine it per-rule from its text below.
_PHASE_RULE = {
    "bl_tests": "R10",          # the per-BL gate retry loop (R10/R10.2)
    "regression_gate": "R10",
}

# A doctrine_check / gate record "caught" a violation (the rule did work) vs
# "ran clean" (enforced, nothing to catch).
_CATCH_KINDS = {
    "doctrine_check": {"incomplete", "give_up"},
    "gate": {"failed", "regressed", "no_tests", "inconclusive"},
}
_CLEAN_KINDS = {
    "doctrine_check": {"complete"},
    "gate": {"green", "skipped"},
}

# Keyword → rule for refining a doctrine_check catch into the specific
# post_validation rule(s) that fired (best-effort scan of summary+missing).
_DOCTRINE_KEYWORDS = (
    ("citation", "R5b"),
    ("grounded", "R5"),
    ("grounding", "R5"),
    ("graph", "R9"),
    ("rubric", "R7"),
    ("self-consist", "R7"),
)

# Phases that are dispositions/setup, not rule firings — ignored for efficacy.
_NON_RULE_PHASES = {
    "worktree_ready", "brief_persisted", "spawn", "exit", "no_op",
    "merge_to_target", "merge_rebase_attempt", "merge_rebase_succeeded",
    "merge_rebase_failed", "awaiting_review",
}


@dataclass
class RuleFiring:
    rule_id: str
    phase: str
    kind: Optional[str]
    caught: bool          # True = rule caught a violation; False = ran clean
    bl_id: Optional[str]
    trace_dir: str


def _role_of(trace_dir_name: str) -> str:
    # "<ts>-<role>-<bl>-<task>" → role (best-effort)
    parts = trace_dir_name.split("-")
    return parts[1] if len(parts) > 1 else ""


def _rules_from_doctrine_text(event: dict) -> list[str]:
    """Best-effort: which specific post_validation rule(s) a doctrine_check
    catch implicates, from its summary + missing text. Falls back to the role
    default (engineer→R5, scorer→R12) then the generic bucket."""
    blob = (str(event.get("summary") or "") + " " + str(event.get("missing") or "")).lower()
    hits = [rid for kw, rid in _DOCTRINE_KEYWORDS if kw in blob]
    return sorted(set(hits))


def extract_firings(run_id: str, *, archive_root: Path | None = None) -> list[RuleFiring]:
    """Read every sealed phase_events.jsonl in the run's archive and project
    each enforcement event to a RuleFiring. Returns [] if the archive is absent."""
    base = (archive_root or _ARCHIVE_DIR) / run_id
    out: list[RuleFiring] = []
    if not base.exists():
        return out
    for tdir in sorted(p for p in base.iterdir() if p.is_dir()):
        role = _role_of(tdir.name)
        for ev in _traces.read_phase_events(tdir):
            phase = ev.get("phase")
            if not phase or phase in _NON_RULE_PHASES:
                continue
            kind = ev.get("kind")
            bl_id = ev.get("bl_id")
            explicit = ev.get("rule_id")
            if explicit:  # streaming kills (R8 / Tier1.5 / R13) always = a catch
                out.append(RuleFiring(explicit, phase, kind, True, bl_id, tdir.name))
                continue
            if phase == "doctrine_check":
                caught = kind in _CATCH_KINDS["doctrine_check"]
                if caught:
                    rids = _rules_from_doctrine_text(ev) or [
                        "R12" if role == "scorer" else "R5"]
                    for rid in rids:
                        out.append(RuleFiring(rid, phase, kind, True, bl_id, tdir.name))
                else:
                    out.append(RuleFiring("doctrine_check", phase, kind, False, bl_id, tdir.name))
                continue
            if phase in _PHASE_RULE:
                rid = _PHASE_RULE[phase]
                caught = kind in _CATCH_KINDS["gate"]
                out.append(RuleFiring(rid, phase, kind, caught, bl_id, tdir.name))
    return out


def load_run_state(run_id: str, *, state_root: Path | None = None) -> dict:
    """Load the per-run orchestrator-state json (active or done/). {} if absent."""
    root = state_root or _STATE_DIR
    for cand in (root / f"{run_id}.json", root / "done" / f"{run_id}.json"):
        try:
            return json.loads(cand.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def run_efficacy(run_id: str, *, archive_root: Path | None = None,
                 state_root: Path | None = None) -> dict:
    """Per-run rule firing + outcome summary, joined with the doctrine manifest."""
    firings = extract_firings(run_id, archive_root=archive_root)
    state = load_run_state(run_id, state_root=state_root)
    manifest = state.get("doctrine_manifest") or {}
    enforced = {r["id"] for r in manifest.get("rules", []) if r.get("enforced")}
    by_rule: dict[str, dict] = {}
    for f in firings:
        slot = by_rule.setdefault(f.rule_id, {"caught": 0, "clean": 0})
        slot["caught" if f.caught else "clean"] += 1
    outcomes = Counter(o.get("outcome") for o in state.get("bl_outcomes", []))
    return {
        "run_id": run_id,
        "repo": state.get("repo"),
        "status": state.get("status"),
        "harness_sha": manifest.get("harness_sha"),
        "rules_enforced": sorted(enforced),
        "by_rule": by_rule,
        "outcome_counts": dict(outcomes),
        "n_firings": len(firings),
    }


def _targeted_class(rule_id: str) -> Optional[str]:
    for r in _spec.DOCTRINE_SPEC:
        if r.id == rule_id:
            return r.targeted_failure_class
    return None


def efficacy_report(run_ids: list[str], *, archive_root: Path | None = None,
                    state_root: Path | None = None) -> dict:
    """Aggregate efficacy across runs. Solid: per-rule fire rate + retirement
    candidates. Scaffolded (low-conf, n-flagged): per-run outcome distribution
    for longitudinal failure-class observation."""
    per_run = [run_efficacy(r, archive_root=archive_root, state_root=state_root)
               for r in run_ids]
    rules: dict[str, dict] = {}
    for pr in per_run:
        enforced = set(pr["rules_enforced"])
        for rid, c in pr["by_rule"].items():
            slot = rules.setdefault(rid, {
                "caught": 0, "clean": 0, "runs_present": 0, "runs_enforced": 0,
                "targeted_failure_class": _targeted_class(rid)})
            slot["caught"] += c["caught"]
            slot["clean"] += c["clean"]
            slot["runs_present"] += 1
        for rid in enforced:
            rules.setdefault(rid, {
                "caught": 0, "clean": 0, "runs_present": 0, "runs_enforced": 0,
                "targeted_failure_class": _targeted_class(rid)})
            rules[rid]["runs_enforced"] += 1
    n = len(per_run)
    for rid, slot in rules.items():
        slot["fire_rate_per_run"] = round(slot["caught"] / n, 3) if n else 0.0

    # Two HONEST buckets — never conflate them (the real-data trap: pre-A13 runs
    # lack sealing, so a rule can look "never fired" when it was simply
    # unobservable):
    #   never_fired : enforced AND observed running (caught+clean records exist)
    #                 yet caught==0. Review-worthy, but note a guardrail that
    #                 never trips may just mean a CLEAN crew, not a dead rule —
    #                 this is a CANDIDATE for the operator-gated meta `retire`,
    #                 NOT a verdict.
    #   unobserved  : enforced but its phase never appears in ANY analyzed run.
    #                 CANNOT be assessed (observability gap or no trigger arose);
    #                 explicitly NOT a retirement signal.
    never_fired = sorted(
        rid for rid, s in rules.items()
        if s["runs_enforced"] >= 1 and s["runs_present"] >= 1 and s["caught"] == 0
    )
    enforced_any = {rid for pr in per_run for rid in pr["rules_enforced"]}
    unobserved = sorted(
        rid for rid in enforced_any
        if rules.get(rid, {}).get("runs_present", 0) == 0
    )
    return {
        "run_count": n,
        "rules": rules,
        # review candidates (observed-but-never-caught) — input to operator-gated
        # meta `retire`, NOT auto-action. Guardrail-never-tripped ≠ dead rule.
        "never_fired_review_candidates": never_fired,
        "unobserved_rules": unobserved,
        "per_run": per_run,
        "confidence": (
            "low (n<3): fire-rate + never-fired signal only; failure-class "
            "reduction needs enforcement variation or a longer series. "
            "unobserved_rules are NOT assessable (likely pre-A13 partial "
            "sealing or no trigger arose)."
            if n < 3 else
            "moderate (n>=3) for fire-rate/never-fired; failure-class causal "
            "attribution still needs enforcement variation. Runs predating the "
            "A13 sealing completion under-report gate/kill firings — treat "
            "unobserved_rules as unassessable, not dead."
        ),
    }
