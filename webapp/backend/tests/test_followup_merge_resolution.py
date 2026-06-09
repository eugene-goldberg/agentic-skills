"""A66 + A65 — the acceptance-followup engineer must self-resolve a repairable
merge failure (dirty target checkout) via the Janitor + remerge, exactly as the
per-BL engineer path does (A58/A59); and the ABL-0019 pattern-profile refresh
must never dirty the target's tracked tree (the immediate trigger).

Surfaced live by run-20260609T133620Z-fb16cc (beaverhabits, periodic-habit-goals):
the Playwright acceptance found a real product_bug, the follow-up engineer FIXED
it (gate green, 3 passed), but `merge_to_target` failed ("main checkout has
modified tracked files") because the pattern-profile refresh left
`_brownfield/_pattern_profile/PATTERN_PROFILE.md` modified+tracked — and the
follow-up path had NO Janitor wired in, so a correct fix was abandoned.
"""
from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app.services.orchestrator as orch  # noqa: E402
from app.services import pattern_profile as pp  # noqa: E402


# ── A65: pattern-profile refresh must not dirty the tracked tree ──────────────

def test_consolidate_writes_gitignore_so_artifact_is_untracked(tmp_path: Path) -> None:
    entry = pp.PatternEntry(pattern_id="p1", area="storage", bl_id="BL-0001",
                            feature_slug="feat", text="use X")
    pp.consolidate(tmp_path, entries=[entry])
    art_dir = tmp_path / "_brownfield" / "_pattern_profile"
    assert (art_dir / "PATTERN_PROFILE.md").exists(), "profile still written"
    gi = art_dir / ".gitignore"
    assert gi.exists(), "A65: a .gitignore must guard the runtime artifact dir"
    assert gi.read_text(encoding="utf-8").strip().endswith("*"), \
        "A65: the .gitignore must ignore the dir's contents (trailing `*`)"


def test_consolidate_does_not_clobber_existing_gitignore(tmp_path: Path) -> None:
    art_dir = tmp_path / "_brownfield" / "_pattern_profile"
    art_dir.mkdir(parents=True)
    (art_dir / ".gitignore").write_text("custom\n", encoding="utf-8")
    pp.consolidate(tmp_path, entries=[])
    assert (art_dir / ".gitignore").read_text(encoding="utf-8") == "custom\n", \
        "must not overwrite an operator-customized .gitignore"


# ── A66: follow-up engineer self-resolves a merge_error via Janitor + remerge ──

class _FakeFinding:
    classification = "product_bug"
    verdict = "confirmed"
    finding_id = "sha256:deadbeef"
    dispatch_state = None


class _FakeLedger:
    def __init__(self):
        self.states: list[tuple] = []

    def set_dispatch_state(self, fid, state, **kw):
        self.states.append((state, kw))

    def set_verdict(self, fid, verdict, note):
        return _FakeFinding()


def _patch_common(monkeypatch, *, dossier: dict, merged_first: bool):
    monkeypatch.setattr(orch, "_evt", lambda phase, **kw: {"type": "_meta", "phase": phase, **kw})
    monkeypatch.setattr(orch, "_build_followup_section", lambda *a, **k: "section")
    monkeypatch.setattr(orch, "_followup_hypothesis", lambda f: None)
    monkeypatch.setattr(orch, "_should_self_confirm", lambda finding, merged: False)
    monkeypatch.setattr(orch.repo_config_svc, "load",
                        lambda repo_dir: types.SimpleNamespace(agent_branch="integration"))

    async def _eng_flow(*a, **k):
        yield {"type": "_meta", "phase": "merge_to_target", "ok": merged_first,
               "merged_sha": "orig123" if merged_first else None}
        yield {"_orchestrator_outcome": True, "role": "engineer",
               "merged": merged_first, "dossier": dossier}

    monkeypatch.setattr(orch, "_engineer_flow", _eng_flow)


def _drive_followup(monkeypatch, **patch_kw) -> tuple[list[dict], _FakeLedger]:
    ledger = _FakeLedger()
    _patch_common(monkeypatch, **patch_kw)

    async def _collect():
        out = []
        async for ev in orch._dispatch_one_followup(
            Path("/tmp/repo"), "repo", "run-X", "feat", _FakeFinding(), 0,
            None, ledger, timeout=60,
        ):
            out.append(ev)
        return out

    return asyncio.run(_collect()), ledger


def test_followup_janitor_repairs_and_remerges(monkeypatch) -> None:
    """The headline A66 path: merge_error -> Janitor repairs -> remerge ok ->
    the follow-up is recorded as MERGED (the fix is no longer abandoned)."""
    dossier = {"blocker": "merge_error", "merge_branch": "agent/abc",
               "merge_error": "main checkout has modified tracked files"}

    async def _janitor(*a, **k):
        if False:
            yield {}  # make it an async generator
    _janitor.last_outcome = {"status": "repaired"}
    monkeypatch.setattr(orch, "_run_janitor", _janitor)

    async def _ffwd(repo_dir, branch, *, target_ref):
        return {"ok": True, "merged_sha": "fixed999", "kind": "ff", "error": None}
    monkeypatch.setattr(orch, "fast_forward_target", _ffwd)

    events, ledger = _drive_followup(monkeypatch, dossier=dossier, merged_first=False)
    phases = [e.get("phase") for e in events]
    assert "merge_retry_post_janitor" in phases
    assert "janitor.resolved" in phases
    done = [e for e in events if e.get("phase") == "acceptance.followup.done"][-1]
    assert done["outcome"] == "merged", "A66: a repaired+remerged follow-up is MERGED"
    assert ("merged", {"merged_sha": "fixed999"}) in ledger.states


def test_followup_no_remerge_when_janitor_cannot_repair(monkeypatch) -> None:
    """If the Janitor does NOT report 'repaired', the remerge must NOT fire and
    the outcome stays not_merged (honest — no false 'fixed')."""
    dossier = {"blocker": "merge_error", "merge_branch": "agent/abc",
               "merge_error": "dirty"}

    async def _janitor(*a, **k):
        if False:
            yield {}
    _janitor.last_outcome = {"status": "unrepaired"}
    monkeypatch.setattr(orch, "_run_janitor", _janitor)

    called = {"ffwd": False}

    async def _ffwd(*a, **k):
        called["ffwd"] = True
        return {"ok": True}
    monkeypatch.setattr(orch, "fast_forward_target", _ffwd)

    events, _ = _drive_followup(monkeypatch, dossier=dossier, merged_first=False)
    assert called["ffwd"] is False, "remerge must not run if the Janitor didn't repair"
    done = [e for e in events if e.get("phase") == "acceptance.followup.done"][-1]
    assert done["outcome"] == "not_merged"


def test_followup_clean_merge_skips_janitor(monkeypatch) -> None:
    """When the follow-up merges cleanly the first time, the Janitor block is a
    no-op (no spurious janitor/remerge events)."""
    monkeypatch.setattr(orch, "_should_self_confirm", lambda finding, merged: False)

    def _boom(*a, **k):
        raise AssertionError("Janitor must not fire on a clean merge")
    monkeypatch.setattr(orch, "_run_janitor", _boom)

    events, _ = _drive_followup(monkeypatch, dossier={}, merged_first=True)
    phases = [e.get("phase") for e in events]
    assert "merge_retry_post_janitor" not in phases
    done = [e for e in events if e.get("phase") == "acceptance.followup.done"][-1]
    assert done["outcome"] == "merged"
