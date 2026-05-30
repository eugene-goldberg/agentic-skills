"""Acceptance-agent output validator (ABL-0010, Batch A).

After the acceptance agent (`skills/brownfield/brownfield-acceptance-agent`)
emits its artifacts under
``<target>/_brownfield/features/<slug>/acceptance/``, this module verifies
the contract defined in the SKILLS.md spec:

- ``journeys.yaml`` is parseable, matches the journey schema, and respects
  the cost caps (≤ 8 journeys; ≤ 15 steps per journey).
- Every step in every journey has an on-disk screenshot at the path it
  declares.
- ``report.md`` and ``report.json`` exist and are non-empty.
- ``report.json``'s per-journey ``outcome`` is one of
  ``{passed, failed, unshippable}``; failed journeys carry a
  ``classification`` from ``{product_bug, test_bug, data_bug,
  infra_bug, uncertain}``.
- ``fixtures/seed_log.txt`` exists.

The return shape mirrors ``doctrine_validator``'s validator dicts so the
orchestrator's R10.1 doctrine-retry loop can re-use ``build_fix_prompt``-
style delta prompts on the next iteration:

    {
      "ok": bool,
      "missing": [<path or contract clause>],
      "empty":   [<path>],
      "summary": "<one-line>"
    }

This module is read-only against the target repo — it inspects on-disk
artifacts written by the agent. It never spawns or mutates anything.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MIN_ARTIFACT_BYTES = 120

MAX_JOURNEYS = 8           # §E.1 Q4 — two-layer cost cap (this is layer 2)
MAX_STEPS_PER_JOURNEY = 15

VALID_OUTCOMES = {"passed", "failed", "unshippable"}
VALID_CLASSIFICATIONS = {
    "product_bug", "test_bug", "data_bug", "infra_bug", "uncertain",
}

# Top-level files the acceptance agent must produce.
REQUIRED_TOP_LEVEL = (
    "journeys.yaml",
    "report.md",
    "report.json",
    "fixtures/seed_log.txt",
)


def _safe_load_yaml(path: Path) -> tuple[Any, str | None]:
    """Parse ``path`` as YAML. Returns (data, None) or (None, err)."""
    try:
        import yaml  # PyYAML is already a dep of the webapp backend
    except ImportError as exc:
        return None, f"<pyyaml unavailable: {exc}>"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"<unreadable: {exc}>"
    try:
        return yaml.safe_load(text), None
    except yaml.YAMLError as exc:
        return None, f"<yaml parse error: {exc}>"


def _safe_load_json(path: Path) -> tuple[Any, str | None]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"<unreadable: {exc}>"
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"<json parse error: {exc}>"


def _validate_journeys_yaml(acc_dir: Path, acc: dict) -> list[dict]:
    """Validate journeys.yaml; mutate ``acc`` with missing/empty. Return
    the parsed journey list (or [] on error) so downstream screenshot
    checks can run."""
    path = acc_dir / "journeys.yaml"
    if not path.exists():
        acc["missing"].append("journeys.yaml")
        return []
    data, err = _safe_load_yaml(path)
    if err:
        acc["missing"].append(f"journeys.yaml ({err})")
        return []
    if not isinstance(data, list):
        acc["missing"].append("journeys.yaml (expected a top-level list of journeys)")
        return []
    if len(data) > MAX_JOURNEYS:
        acc["missing"].append(
            f"journeys.yaml (cost cap: {len(data)} journeys > MAX {MAX_JOURNEYS})"
        )

    valid_journeys: list[dict] = []
    for idx, j in enumerate(data):
        if not isinstance(j, dict):
            acc["missing"].append(f"journeys.yaml[{idx}] (not a mapping)")
            continue
        for required_key in ("id", "slug", "steps"):
            if required_key not in j:
                acc["missing"].append(
                    f"journeys.yaml[{idx}] missing key '{required_key}'"
                )
        steps = j.get("steps")
        if not isinstance(steps, list) or len(steps) == 0:
            acc["missing"].append(
                f"journeys.yaml[{idx}] '{j.get('slug', '?')}' (≥1 step required)"
            )
        elif len(steps) > MAX_STEPS_PER_JOURNEY:
            acc["missing"].append(
                f"journeys.yaml[{idx}] '{j.get('slug', '?')}' "
                f"(cost cap: {len(steps)} steps > MAX {MAX_STEPS_PER_JOURNEY})"
            )
        valid_journeys.append(j)
    return valid_journeys


def _validate_screenshots(acc_dir: Path, journeys: list[dict], acc: dict) -> None:
    """Every step's `screenshot:` value MUST exist on disk under
    `acc_dir/screenshots/journey_<NN>_<slug>/<screenshot>` per SKILLS.md
    §Outputs."""
    screenshots_root = acc_dir / "screenshots"
    for j in journeys:
        slug = j.get("slug", "?")
        # padded id (e.g. "01") — fall back to raw if non-numeric
        raw_id = str(j.get("id", "??"))
        try:
            jid = f"{int(raw_id):02d}"
        except (TypeError, ValueError):
            jid = raw_id
        journey_dir = screenshots_root / f"journey_{jid}_{slug}"
        steps = j.get("steps") or []
        for step_idx, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            ss = step.get("screenshot")
            if not ss:
                acc["missing"].append(
                    f"journey '{slug}' step {step_idx + 1} missing 'screenshot:' field"
                )
                continue
            ss_path = journey_dir / ss
            if not ss_path.exists():
                acc["missing"].append(
                    f"screenshots/journey_{jid}_{slug}/{ss} (declared by step "
                    f"'{step.get('name', step_idx + 1)}' but file missing on disk)"
                )


def _validate_report_json(acc_dir: Path, acc: dict) -> None:
    """report.json must hold per-journey outcomes with valid enums."""
    path = acc_dir / "report.json"
    if not path.exists():
        return  # already flagged by REQUIRED_TOP_LEVEL check
    data, err = _safe_load_json(path)
    if err:
        acc["missing"].append(f"report.json ({err})")
        return
    if not isinstance(data, dict):
        acc["missing"].append("report.json (expected a top-level object)")
        return
    journeys = data.get("journeys")
    if not isinstance(journeys, list):
        acc["missing"].append("report.json missing 'journeys: [...]' array")
        return
    for idx, j in enumerate(journeys):
        if not isinstance(j, dict):
            acc["missing"].append(f"report.json journeys[{idx}] (not a mapping)")
            continue
        outcome = j.get("outcome")
        if outcome not in VALID_OUTCOMES:
            acc["missing"].append(
                f"report.json journeys[{idx}] outcome={outcome!r} "
                f"(must be one of {sorted(VALID_OUTCOMES)})"
            )
            continue
        if outcome == "failed":
            cls = j.get("classification")
            if cls not in VALID_CLASSIFICATIONS:
                acc["missing"].append(
                    f"report.json journeys[{idx}] failed but classification={cls!r} "
                    f"(must be one of {sorted(VALID_CLASSIFICATIONS)})"
                )


def _check_required_file(acc_dir: Path, rel: str, acc: dict) -> None:
    p = acc_dir / rel
    if not p.exists():
        acc["missing"].append(rel)
        return
    try:
        sz = len(p.read_text(encoding="utf-8").strip())
    except OSError:
        acc["missing"].append(rel)
        return
    if sz < MIN_ARTIFACT_BYTES:
        acc["empty"].append(rel)


def validate_acceptance(acceptance_dir: Path) -> dict:
    """Validate the contents of an acceptance-agent output dir.

    Parameters
    ----------
    acceptance_dir
        Absolute path to
        ``<target>/_brownfield/features/<slug>/acceptance/``.

    Returns
    -------
    A dict matching the doctrine_validator return shape:
    ``{ok, missing, empty, summary}``.
    """
    acc: dict[str, Any] = {"missing": [], "empty": []}

    if not acceptance_dir.exists():
        acc["missing"].append(f"<acceptance dir not created: {acceptance_dir}>")
        acc["ok"] = False
        acc["summary"] = "acceptance dir missing"
        return acc

    for rel in REQUIRED_TOP_LEVEL:
        _check_required_file(acceptance_dir, rel, acc)

    journeys = _validate_journeys_yaml(acceptance_dir, acc)
    if journeys:
        _validate_screenshots(acceptance_dir, journeys, acc)
    _validate_report_json(acceptance_dir, acc)

    acc["ok"] = not acc["missing"] and not acc["empty"]
    acc["summary"] = (
        f"ok={acc['ok']} missing={len(acc['missing'])} empty={len(acc['empty'])}"
    )
    return acc
