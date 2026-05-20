"""Brownfield-specific helpers shared across prompts, gating, and config.

Responsibilities:
- pick_artifact_dir(repo_root)  → returns the top-level dir name agents
  should write brownfield artifacts into. Default `_brownfield`; falls back
  to `_agentic_artifacts` if upstream already uses `_brownfield` for a
  conflicting purpose.
- detect_test_command(repo_root) → best-guess test command for the repo's
  test suite, used by the regression gate. Honors a per-repo override at
  `_brownfield/test_cmd.txt`.
- RUBRIC_PATHS — paths to the two rubric files; the scorer picks one.
"""
from __future__ import annotations

import json
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
AGENTIC_ROOT = BACKEND_DIR.parent.parent  # webapp/.. = agentic-skills/

RUBRIC_PATHS = {
    "greenfield": AGENTIC_ROOT / "rubrics" / "production_grade_scorecard.md",
    "brownfield": AGENTIC_ROOT / "rubrics" / "production_grade_scorecard_brownfield.md",
}

DEFAULT_ARTIFACT_DIR = "_brownfield"
FALLBACK_ARTIFACT_DIR = "_agentic_artifacts"


_SOURCE_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".rb",
    ".kt", ".cs", ".cpp", ".c", ".h", ".swift", ".sql",
}


def classify_target(repo_root: Path, max_files: int = 5000) -> dict:
    """In-process equivalent of mcp__retrieval__target_status — used by the
    router to pick the doctrine family before spawning an agent.

    Returns at minimum {"kind": "greenfield"|"brownfield", "source_file_count": int}.
    Skips hidden dirs and common build artifacts.
    """
    if not repo_root.exists():
        return {"kind": "greenfield", "source_file_count": 0, "exists": False}
    n = 0
    seen = 0
    for p in repo_root.rglob("*"):
        if seen >= max_files:
            break
        rel = p.relative_to(repo_root)
        parts = set(rel.parts)
        if any(s.startswith(".") for s in parts):
            continue
        if parts & {"node_modules", "__pycache__", "graphify-out", ".venv", "venv", "dist", "build"}:
            continue
        if not p.is_file():
            continue
        seen += 1
        if p.suffix.lower() in _SOURCE_EXTS:
            n += 1
    return {"kind": "brownfield" if n > 0 else "greenfield", "source_file_count": n, "exists": True}


def pick_artifact_dir(repo_root: Path) -> str:
    """Return the directory name the agents should write artifacts into.

    Uses `_brownfield` unless the target repo already has a `_brownfield`
    directory containing something that doesn't look like our own artifacts
    (i.e. no per-BL subdirs and no SPRINT_PLAN_CN.md). In that case, fall
    back to `_agentic_artifacts` to avoid collision.
    """
    candidate = repo_root / DEFAULT_ARTIFACT_DIR
    if not candidate.exists():
        return DEFAULT_ARTIFACT_DIR
    # Allow if it already looks like our own artifacts dir.
    children = list(candidate.iterdir())
    looks_like_ours = any(
        c.name == "SPRINT_PLAN_C1.md"
        or c.name == "_codebase_context"
        or (c.is_dir() and c.name.startswith("BL-"))
        for c in children
    )
    if looks_like_ours:
        return DEFAULT_ARTIFACT_DIR
    return FALLBACK_ARTIFACT_DIR


def detect_test_command(repo_root: Path) -> list[str]:
    """Pick the right shell command to run the repo's full test suite.

    Order of resolution:
    1. <repo_root>/<artifact_dir>/test_cmd.txt — one-line override.
    2. pyproject.toml or pytest.ini present → `pytest -q`.
    3. package.json present and has a "test" script → `npm test --silent`.
    4. Makefile present with a `test` target → `make test`.
    5. requirements.txt present (no pyproject) → still try `pytest -q`.
    6. Fallback → ["pytest", "-q"] and let it fail loudly.
    """
    artifact_dir = pick_artifact_dir(repo_root)
    override = repo_root / artifact_dir / "test_cmd.txt"
    if override.exists():
        txt = override.read_text().strip()
        if txt:
            # Shell-split the override line.
            import shlex
            return shlex.split(txt)
    if (repo_root / "pyproject.toml").exists() or (repo_root / "pytest.ini").exists():
        return ["pytest", "-q"]
    pkg = repo_root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text())
            if isinstance(data.get("scripts"), dict) and "test" in data["scripts"]:
                return ["npm", "test", "--silent"]
        except (OSError, json.JSONDecodeError):
            pass
    if (repo_root / "Makefile").exists():
        try:
            mk = (repo_root / "Makefile").read_text()
            if "\ntest:" in mk or mk.startswith("test:"):
                return ["make", "test"]
        except OSError:
            pass
    if (repo_root / "requirements.txt").exists():
        return ["pytest", "-q"]
    return ["pytest", "-q"]
