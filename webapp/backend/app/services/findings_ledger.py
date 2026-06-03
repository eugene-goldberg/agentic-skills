"""I.3 findings feedback ledger.

Filed against ABL-0014 §I.3 (production-ready roadmap). Shipped in
Batch A 2026-06-01.

Acceptance runs emit findings (classifications: ``product_bug``,
``test_bug``, ``data_bug``, ``infra_bug``, ``uncertain``) inside
``acceptance/report.json`` under each failed journey's ``failure``
object. Today those findings vanish into ``traces_archive/`` once the
sprint terminates — there is no record of which were confirmed real
bugs, which were classifier mistakes, and which the operator deferred.
Without that record, classifier accuracy is structurally unbounded:
the agent cannot learn from prior verdicts, and ABL-0015 auto-dispatch
of follow-up engineers cannot filter on operator confirmation.

This module is the persistence half of I.3. It owns one file per
brownfield feature:

    <repo>/_brownfield/features/<slug>/acceptance/findings_log.jsonl

Each line is a JSON object describing one finding (one failed journey
in one acceptance run). Reruns of the same sprint shape upsert the
existing line (bumping ``seen_count`` and ``last_seen_ts``) rather
than appending a duplicate — the ``finding_id`` is a sha256 hash of
the tuple ``(repo, feature_slug, journey_id, classification,
evidence_summary[:200])`` and is therefore stable across runs.

Verdicts (``confirmed`` / ``refuted`` / ``deferred``) are written by
``set_verdict``, called from the AppV2 triage UI (Batch D, not yet
shipped).

This batch has zero call sites — the module is dormant until Batch B
wires it into the acceptance flow. Schema changes are free until then.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

VALID_CLASSIFICATIONS = frozenset({
    "product_bug", "test_bug", "data_bug", "infra_bug", "uncertain",
})
VALID_VERDICTS = frozenset({"confirmed", "refuted", "deferred"})

# Truncation cap for evidence_summary contribution to finding_id.
# Beyond this the hash hits diminishing returns and a long stack trace
# can mutate trivially (line numbers shift) across reruns, producing
# false-distinct findings.
_EVIDENCE_HASH_PREFIX = 200
# Hard cap on stored evidence_summary; longer evidence is truncated
# with a trailing ellipsis so the ledger stays human-readable.
_EVIDENCE_STORE_CAP = 500


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _compute_finding_id(
    repo: str, feature_slug: str, journey_id: str,
    classification: str, evidence_summary: str,
) -> str:
    raw = "|".join((
        repo, feature_slug, journey_id, classification,
        evidence_summary[:_EVIDENCE_HASH_PREFIX],
    ))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _truncate_evidence(text: str) -> str:
    if len(text) <= _EVIDENCE_STORE_CAP:
        return text
    return text[: _EVIDENCE_STORE_CAP - 1].rstrip() + "…"


def _extract_evidence_summary(failure_obj: dict | None) -> str:
    """Pull a stable evidence string out of a journey's failure object.

    ``report.json`` has shifted shape across runs — try the most
    explicit fields first and fall back to a stringification so a
    finding is never lost just because the schema drifted.
    """
    if not failure_obj:
        return ""
    for key in ("evidence", "message", "summary", "detail", "reason"):
        v = failure_obj.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    # Last resort: stable JSON so reruns of the same failure produce
    # the same hash regardless of dict ordering.
    try:
        return json.dumps(failure_obj, sort_keys=True, default=str)
    except Exception:
        return str(failure_obj)


@dataclass
class Finding:
    finding_id: str
    run_id: str
    feature_slug: str
    journey_id: str
    journey_kind: str  # "api" | "ui"
    classification: str
    evidence_summary: str
    report_path: str
    first_seen_ts: str
    last_seen_ts: str
    seen_count: int
    verdict: Optional[str] = None
    verdict_ts: Optional[str] = None
    verdict_note: Optional[str] = None

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_jsonl(cls, line: str) -> "Finding":
        d = json.loads(line)
        return cls(**d)


class FindingsLedger:
    """Per-feature JSONL ledger of acceptance findings + operator verdicts.

    The ledger file is created lazily on first append. All write paths
    (``append_from_report``, ``set_verdict``) acquire an exclusive
    ``fcntl`` lock on the file for the duration of the read-modify-
    write cycle. Read paths (``list_all``, ``list_pending``,
    ``get_priors_for_classification``) do not take the lock and may
    observe a slightly stale view; this is acceptable for the
    intended UI/agent-prior consumers.
    """

    def __init__(self, repo_root: Path, feature_slug: str) -> None:
        self.repo_root = Path(repo_root)
        self.feature_slug = feature_slug
        self.path = (
            self.repo_root / "_brownfield" / "features" / feature_slug
            / "acceptance" / "findings_log.jsonl"
        )

    # ---------- internals ----------

    def _ensure_parent(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def _read_all_unlocked(self) -> list[Finding]:
        if not self.path.exists():
            return []
        out: list[Finding] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(Finding.from_jsonl(line))
                except Exception:
                    # Skip malformed lines rather than corrupt the whole
                    # ledger; future tooling can rewrite the file.
                    continue
        return out

    def _write_all_unlocked(self, findings: Iterable[Finding]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for f in findings:
                fh.write(f.to_jsonl() + "\n")
        tmp.replace(self.path)

    # ---------- public API ----------

    def append_from_report(
        self,
        report: dict,
        *,
        run_id: str,
        report_path: str,
    ) -> list[Finding]:
        """Extract findings from an acceptance ``report.json`` payload
        and upsert each into the ledger.

        Returns the list of ``Finding`` objects as persisted (new
        inserts and upserted-existing both included).
        """
        self._ensure_parent()
        extracted = _extract_findings_from_report(
            report,
            repo=str(self.repo_root),
            feature_slug=self.feature_slug,
            run_id=run_id,
            report_path=report_path,
        )

        with self.path.open("a+", encoding="utf-8") as lockfh:
            fcntl.flock(lockfh.fileno(), fcntl.LOCK_EX)
            try:
                current = self._read_all_unlocked()
                by_id: dict[str, Finding] = {f.finding_id: f for f in current}
                persisted: list[Finding] = []
                for new in extracted:
                    existing = by_id.get(new.finding_id)
                    if existing is None:
                        by_id[new.finding_id] = new
                        persisted.append(new)
                    else:
                        existing.last_seen_ts = new.last_seen_ts
                        existing.seen_count += 1
                        existing.report_path = new.report_path
                        persisted.append(existing)
                self._write_all_unlocked(by_id.values())
                return persisted
            finally:
                fcntl.flock(lockfh.fileno(), fcntl.LOCK_UN)

    def list_all(self) -> list[Finding]:
        return self._read_all_unlocked()

    def list_pending(self) -> list[Finding]:
        return [f for f in self._read_all_unlocked() if f.verdict is None]

    def set_verdict(
        self, finding_id: str, verdict: str, note: Optional[str] = None,
    ) -> Finding:
        if verdict not in VALID_VERDICTS:
            raise ValueError(
                f"invalid verdict {verdict!r}; expected one of "
                f"{sorted(VALID_VERDICTS)}"
            )
        self._ensure_parent()
        with self.path.open("a+", encoding="utf-8") as lockfh:
            fcntl.flock(lockfh.fileno(), fcntl.LOCK_EX)
            try:
                current = self._read_all_unlocked()
                target: Optional[Finding] = None
                for f in current:
                    if f.finding_id == finding_id:
                        target = f
                        break
                if target is None:
                    raise ValueError(f"unknown finding_id {finding_id!r}")
                target.verdict = verdict
                target.verdict_ts = _now_iso()
                target.verdict_note = note
                self._write_all_unlocked(current)
                return target
            finally:
                fcntl.flock(lockfh.fileno(), fcntl.LOCK_UN)

    def get_priors_for_classification(self, classification: str) -> dict:
        """Aggregate verdict counts for a classification. Intended for
        Batch E (agent reads priors at spawn) — surfaces e.g.
        'classification=product_bug has been refuted 4 times in this
        feature', so the agent can raise its falsification bar."""
        counts = {"confirmed": 0, "refuted": 0, "deferred": 0, "pending": 0}
        for f in self._read_all_unlocked():
            if f.classification != classification:
                continue
            if f.verdict is None:
                counts["pending"] += 1
            else:
                counts[f.verdict] = counts.get(f.verdict, 0) + 1
        return counts


def _extract_findings_from_report(
    report: dict,
    *,
    repo: str,
    feature_slug: str,
    run_id: str,
    report_path: str,
) -> list[Finding]:
    """Walk a report.json payload and produce one Finding per failed
    journey OR pass-with-caveat journey that carries a classification.

    Three journey shapes produce findings:

    1. **Failed journey, top-level classification (SKILLS.md canonical
       for api_journeys, lines 440-462).** ``status=fail|failed|error``
       plus ``classification`` and ``evidence``/``hypothesis`` at the
       journey top level.

    2. **Failed journey, nested-failure shape (validator-defensive,
       see acceptance_validator.py:307-309).** Same status set, but
       ``classification`` lives under ``failure: {...}``.

    3. **Pass-with-caveat journey (gap closed 2026-06-02).** A journey
       can complete successfully at the step it exercises but still
       observe an architectural defect — e.g. UI Journey 03 from the
       financial-management run, where the legal draft→sent step
       passes but the PUT path is found to bypass BL-0005's transition
       state machine. The agent emits these as
       ``status=pass_with_caveat`` with a ``caveat: {classification,
       severity, summary, hypothesis}`` object. Without this branch,
       those findings vanish into report.md prose and never reach the
       ledger — defeating the §I.4 ABL-0015 auto-dispatch loop.

    Quiet on schema drift: missing fields are skipped, not raised.
    """
    out: list[Finding] = []
    now = _now_iso()
    # Accept both ``ui_journeys``/``api_journeys`` (Batch B+) and a
    # single ``journeys`` list (older shape).
    buckets: list[tuple[str, list]] = []
    for kind_key, journey_kind in (
        ("ui_journeys", "ui"),
        ("api_journeys", "api"),
        ("journeys", "ui"),
    ):
        items = report.get(kind_key)
        if isinstance(items, list):
            buckets.append((journey_kind, items))
    for journey_kind, items in buckets:
        for j in items:
            if not isinstance(j, dict):
                continue
            extracted = _extract_finding_from_journey(
                j,
                repo=repo,
                feature_slug=feature_slug,
                run_id=run_id,
                report_path=report_path,
                journey_kind=journey_kind,
                now=now,
            )
            if extracted is not None:
                out.append(extracted)
    return out


def _extract_finding_from_journey(
    journey: dict,
    *,
    repo: str,
    feature_slug: str,
    run_id: str,
    report_path: str,
    journey_kind: str,
    now: str,
) -> "Finding | None":
    """Single-journey extraction. Tries fail-shape first, then
    pass-with-caveat shape. Returns ``None`` if neither produces a
    valid classification."""
    status = journey.get("status")
    journey_id = str(journey.get("id") or journey.get("journey_id") or "")
    if not journey_id:
        return None

    # Shape #3: pass_with_caveat — agent passed the step but found an
    # architectural defect. Caveat object carries the structured finding.
    if status == "pass_with_caveat":
        caveat = journey.get("caveat")
        if not isinstance(caveat, dict):
            return None
        classification = caveat.get("classification")
        if classification not in VALID_CLASSIFICATIONS:
            return None
        evidence_raw = _extract_caveat_evidence(caveat)
    elif status in ("failed", "fail", "error"):
        # Shapes #1 + #2: failed journey.
        failure = journey.get("failure") if isinstance(journey.get("failure"), dict) else {}
        # Validator pattern (acceptance_validator.py:307-309):
        # top-level classification wins; fall back to nested.
        classification = journey.get("classification")
        if classification is None:
            classification = failure.get("classification")
        if classification not in VALID_CLASSIFICATIONS:
            return None
        evidence_raw = _extract_evidence_summary_dual(journey, failure)
    else:
        return None

    evidence_stored = _truncate_evidence(evidence_raw)
    fid = _compute_finding_id(
        repo, feature_slug, journey_id, classification, evidence_raw,
    )
    return Finding(
        finding_id=fid,
        run_id=run_id,
        feature_slug=feature_slug,
        journey_id=journey_id,
        journey_kind=journey_kind,
        classification=classification,
        evidence_summary=evidence_stored,
        report_path=report_path,
        first_seen_ts=now,
        last_seen_ts=now,
        seen_count=1,
    )


def _extract_caveat_evidence(caveat: dict) -> str:
    """Pull a stable evidence string out of a caveat object.

    Prefers ``summary`` (the agent's full description of the
    architectural gap) over ``hypothesis`` (the file-line guess) so
    that the finding_id is stable across reruns even if the
    hypothesis text shifts. Falls back to stable JSON if neither is
    a non-empty string.
    """
    for key in ("summary", "hypothesis", "detail", "evidence"):
        v = caveat.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    try:
        return json.dumps(caveat, sort_keys=True, default=str)
    except Exception:
        return str(caveat)


def _extract_evidence_summary_dual(journey: dict, failure: dict) -> str:
    """Pull an evidence string honoring the SKILLS.md top-level shape
    AND the validator's nested-``failure`` fallback. Tries the most
    descriptive sources first."""
    # Top-level (SKILLS.md canonical) wins.
    for key in ("evidence", "hypothesis", "message", "summary", "detail"):
        v = journey.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    # Then the nested-failure fallback.
    nested = _extract_evidence_summary(failure)
    if nested:
        return nested
    # Last resort: stable JSON of whichever side carries content, so
    # reruns of the same finding still hash consistently.
    payload = failure if failure else {
        k: journey.get(k) for k in ("id", "classification", "status")
    }
    try:
        return json.dumps(payload, sort_keys=True, default=str)
    except Exception:
        return str(payload)
