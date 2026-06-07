"""ABL-0020 Batch A — the doctrine-spec registry (I-2 fulfillment).

I-2's architectural mandate (ARCHITECTURE_INVARIANTS.md) calls for "a single
doctrine spec data structure (in code, not prose) [that] names each rule,
its enforcement point, and a callable check," plus a meta-test asserting
every entry has an enforcement point AND a resolvable check. That mandate
has been unfulfilled since the invariants were written; this module is it.

It is also the **keystone** for ABL-0017 Stage 2 (closed-loop doctrine
efficacy): `targeted_failure_class` is what lets efficacy ask "did failure
class C drop while rule R (which targets C) was active in run X?".

Seeded from the verified canonical tables (CLAUDE.md R-rules +
ARCHITECTURE_INVARIANTS I-2 coverage). Dormant: nothing reads it at runtime
yet (ABL-0020 Batch B writes the per-run manifest; ABL-0017 consumes it).
The I-2 meta-test in tests/test_doctrine_spec.py keeps it honest.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Optional

# Enforcement points a rule can live at (the I-2 enforcement-point vocabulary
# + the orchestrator/flow sites the R10.x retries and R15 selector use).
ALLOWED_ENFORCEMENT_POINTS = frozenset({
    "prompt", "preflight", "streaming", "post_validation",
    "gate", "orchestrator", "flow",
})

# I-6 failure taxonomy — the class a rule is meant to *reduce*. Optional per
# rule (set only where the mapping is clear; never force-fit).
I6_FAILURE_CLASSES = frozenset({
    "race", "resource-leak", "silent-failure", "silent-success",
    "consistency-violation", "enforcement-gap", "starvation",
    "data-loss", "observability-gap", "scope-creep",
})

# Rules documented but NOT enforced — must be explicit so "documented but
# unenforced" is an intentional, tracked gap (never a silent one). I-2:
# documenting a rule no code enforces is otherwise a build failure.
KNOWN_GAPS = frozenset({"R9"})  # A8 in the ledger


@dataclass(frozen=True)
class DoctrineRule:
    id: str
    summary: str
    enforcement_point: str          # one of ALLOWED_ENFORCEMENT_POINTS
    enforced: bool                  # False only for KNOWN_GAPS (R9/A8)
    check_ref: Optional[str]        # "module:symbol" of the enforcing code
    has_test: bool                  # is the rule exercised by a test today
    targeted_failure_class: Optional[str]  # I-6 class — the Stage-2 hook
    docs: tuple[str, ...] = field(default_factory=tuple)


# ── The registry ───────────────────────────────────────────────────────────
# check_ref points at the actual enforcing symbol so the meta-test can resolve
# it (I-2's "callable check"). enforcement_point is the primary site.

DOCTRINE_SPEC: tuple[DoctrineRule, ...] = (
    DoctrineRule(
        "R5", "≥3 grounded retrieval calls before the change is trusted",
        "post_validation", True,
        "app.services.doctrine_validator:_count_grounded_retrieval",
        has_test=True, targeted_failure_class="silent-failure",
        docs=("CLAUDE.md", "ARCHITECTURE_INVARIANTS.md", "SKILLS.md"),
    ),
    DoctrineRule(
        "R5b", "citations to retrieval evidence in role artifacts",
        "post_validation", True,
        "app.services.doctrine_validator:_check_citations",
        has_test=False, targeted_failure_class="observability-gap",
        docs=("SKILLS.md",),
    ),
    DoctrineRule(
        "R7", "rubric self-consistency (brownfield-axis ≤2 → Fail)",
        "post_validation", True,
        "app.services.doctrine_validator:validate_scorer",
        has_test=False, targeted_failure_class="consistency-violation",
        docs=("rubric", "CLAUDE.md"),
    ),
    DoctrineRule(
        "R8", "≤30 mcp__retrieval__* calls (budget ceiling)",
        "streaming", True,
        "app.services.claude_agent:MAX_RETRIEVAL_CALLS_DEFAULT",
        has_test=False, targeted_failure_class=None,
        docs=("SKILLS.md", "CLAUDE.md"),
    ),
    DoctrineRule(
        "R9", "≥1 graph_* call",
        "streaming", False,  # GAP — A8: advisory only, not enforced
        None, has_test=False, targeted_failure_class=None,
        docs=("CLAUDE.md",),
    ),
    DoctrineRule(
        "R10", "up to 2 gate retries with a focused fix prompt",
        "orchestrator", True,
        "app.services.orchestrator:_engineer_flow",
        has_test=False, targeted_failure_class=None,
        docs=("CLAUDE.md", "code"),
    ),
    DoctrineRule(
        "R10.1", "up to 2 doctrine retries per role",
        "flow", True,
        "app.services.orchestrator:_qa_or_scorer_flow",
        has_test=False, targeted_failure_class=None,
        docs=("CLAUDE.md", "code"),
    ),
    DoctrineRule(
        "R10.2", "up to 2 retries on gate fail (re-spawn w/ failure detail)",
        "orchestrator", True,
        "app.services.orchestrator:_engineer_flow",
        has_test=False, targeted_failure_class=None,
        docs=("CLAUDE.md", "code"),
    ),
    DoctrineRule(
        "R11", "no-op short-circuit when work already on agent_branch",
        "flow", True,
        "app.services.doctrine_validator:validate_engineer",
        has_test=False, targeted_failure_class=None,
        docs=("CLAUDE.md", "code"),
    ),
    DoctrineRule(
        "R12", "scorer grounding floor (same Tier-1.5 streaming kill)",
        "streaming", True,
        "app.services.claude_agent:stream_agent_task",
        has_test=False, targeted_failure_class="silent-failure",
        docs=("SKILLS.md", "CLAUDE.md"),
    ),
    DoctrineRule(
        "R13", "no agent-initiated history-rewriting git commands",
        "streaming", True,
        "app.services.claude_agent:FORBIDDEN_GIT_RE",
        has_test=True, targeted_failure_class="data-loss",
        docs=("SKILLS.md", "CLAUDE.md", "code"),
    ),
    DoctrineRule(
        "R15", "acceptance product_bug dispatched at most once",
        "orchestrator", True,
        "app.services.orchestrator:_select_followup_candidates",
        has_test=True, targeted_failure_class=None,
        docs=("CLAUDE.md", "ABL-0015_AUTO_DISPATCH_DESIGN.md"),
    ),
    DoctrineRule(
        "R16", "non-code failures spawn the Janitor (never silent-abort); "
               "structural repairs route to doctrine-meta",
        "orchestrator", True,
        "app.services.orchestrator:_janitor_flow",
        has_test=True, targeted_failure_class="silent-failure",
        docs=("CLAUDE.md", "PROPOSAL_OPS_STEWARD_ROLE.md"),
    ),
    DoctrineRule(
        "Tier1.5", "pre-modification kill: <min grounded calls before Write/Edit",
        "streaming", True,
        "app.services.claude_agent:stream_agent_task",
        has_test=False, targeted_failure_class="silent-failure",
        docs=("CLAUDE.md", "code"),
    ),
)

# Canonical id set the registry must cover (guards a rule added to prose but
# not here). R14 (QA test-timeout, QA SKILLS + pytest config) is intentionally
# not yet registered — its enforcement point is to be confirmed first.
CANONICAL_RULE_IDS = frozenset({
    "R5", "R5b", "R7", "R8", "R9", "R10", "R10.1", "R10.2",
    "R11", "R12", "R13", "R15", "R16", "Tier1.5",
})


# ── accessors ────────────────────────────────────────────────────────────────


def by_id(rule_id: str) -> Optional[DoctrineRule]:
    for r in DOCTRINE_SPEC:
        if r.id == rule_id:
            return r
    return None


def enforced_rules() -> tuple[DoctrineRule, ...]:
    return tuple(r for r in DOCTRINE_SPEC if r.enforced)


def manifest() -> dict:
    """The per-run doctrine snapshot (ABL-0020 Batch B writes this into run
    state). Captures which rules were in force so ABL-0017 efficacy can join
    rule-state against per-BL outcomes."""
    return {
        "rules": [{"id": r.id, "enforced": r.enforced} for r in DOCTRINE_SPEC],
    }


def resolve_check(rule: DoctrineRule):
    """Import and return the enforcing symbol named by ``check_ref``
    ("module:symbol"). Raises if it cannot be resolved — this is the
    teeth of the I-2 "callable check" requirement. Returns None for an
    unenforced gap (check_ref is None)."""
    if rule.check_ref is None:
        return None
    module_name, _, symbol = rule.check_ref.partition(":")
    mod = importlib.import_module(module_name)
    return getattr(mod, symbol)
