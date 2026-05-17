"""Initialize: validate inputs, snapshot skill files into skills/<role>/<id>/SKILLS.md."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from ..state import GraphState


def _hash_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _snapshot_skill(source: Path, dest_dir: Path) -> tuple[Path, str]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "SKILLS.md"
    shutil.copy2(source, dest)
    return dest, _hash_file(dest)


def initialize(state: GraphState) -> GraphState:
    workspace = Path(state["workspace_root"]).resolve()
    target = Path(state["target_repo_path"]).resolve()
    brief = Path(state["project_brief_path"]).resolve()

    for label, p in [("workspace_root", workspace), ("target_repo_path", target), ("project_brief_path", brief)]:
        if not p.exists():
            return {**state, "error": f"{label} does not exist: {p}"}

    # Snapshot skills (each role gets a stable id derived from filename)
    skills_root = workspace / "skills"
    updates: dict = {}
    for role in ("po", "eng", "qa"):
        src = Path(state[f"{role}_skill_source_path"]).resolve()
        if not src.exists():
            return {**state, "error": f"{role}_skill_source_path does not exist: {src}"}
        skill_id = src.stem  # filename without extension
        dest_dir = skills_root / role / f"lg-{skill_id}"
        snapshot, sha = _snapshot_skill(src, dest_dir)
        updates[f"{role}_skill_id"] = f"lg-{skill_id}"
        updates[f"{role}_skill_snapshot_path"] = str(snapshot)
        updates[f"{role}_skill_sha256"] = sha

    return {
        **state,
        "completed_cycles": [],
        "current_index": -1,
        "last_eng_commit": "",
        **updates,
    }
