"""Per-target-repo configuration for the webapp.

Each brownfield target repo may carry an `.agentic-skills.json` at its
root that tells the webapp:

- `agent_branch`  — the branch off which all agent worktrees should be
  created, AND the branch into which Engineer / QA fast-forward on success.
  Default: "agentic-skills-work" if it exists, else "main".
- `main_ref`      — name of the pristine upstream branch (default "main").
  Used by the regression gate to compute a pre-merge baseline.
- `test_cmd`      — optional override for the regression-gate test command
  (otherwise auto-detected by brownfield.detect_test_command).
- `doctrine`      — optional explicit override ("brownfield"/"greenfield").
  Normally derived from target_status() at run time; this lets you force a
  family.
- `app_boot`      — optional native-boot contract for the acceptance phase on
  NON-compose targets (PROPOSAL_NATIVE_BOOT_ACCEPTANCE, 2026-06-11). A dict:
  `cmd` (list[str], may contain `${PORT}`), `env` (dict[str,str]), `ready_url`
  (str, may contain `${PORT}`), `ready_timeout_s` (int), `materialize`
  (list of {from,to} — `from` MUST be a committed `*.example.*` template,
  enforced at use), `pre_cmd` (list[list[str]] — e.g. migrations). When absent,
  acceptance uses the existing compose path.

Greenfield repos that lack the file get sensible defaults: branch="main",
no doctrine override.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path


CONFIG_FILENAME = ".agentic-skills.json"
DEFAULT_AGENT_BRANCH = "agentic-skills-work"
DEFAULT_MAIN_REF = "main"

# ABL-0014 Item 1 (Batch B, 2026-06-01): default glob set for identifying
# "backend route" files when computing which merged BLs need api_journey
# coverage. Tuned for FastAPI/Flask-style trees; targets with different
# layouts can override via the `api_route_globs` key in
# .agentic-skills.json. Use forward-slash globs; matched case-insensitively
# against repo-relative paths.
DEFAULT_API_ROUTE_GLOBS: list[str] = [
    "**/api/routes/*.py",
    "**/api/routes/**/*.py",
    "**/api/*.py",
    "**/routers/*.py",
    "**/routers/**/*.py",
    "**/routes/*.py",
    "**/routes/**/*.py",
]

# ABL-0014 Item 2 (Batch C, 2026-06-01): default glob set for identifying
# "user-facing UI" files for the sprint UI-coverage ratio check. A merged
# BL whose commit touches at least one matching path is counted as a
# "UI BL." Tuned for React/Vue/Svelte/Angular trees; targets with other
# stacks (Flutter, native mobile, server-rendered Django templates) can
# override via the `ui_globs` key in .agentic-skills.json.
DEFAULT_UI_GLOBS: list[str] = [
    "**/*.tsx",
    "**/*.jsx",
    "**/*.vue",
    "**/*.svelte",
    "frontend/**/*",
    "web/**/*",
    "ui/**/*",
    "**/templates/**/*.html",
    "**/templates/**/*.jinja",
]


def _normalize_app_boot(raw: object) -> dict | None:
    """Validate/normalize the optional `app_boot` block from .agentic-skills.json.

    Returns a clean dict or None. Enforces TYPES only (a trustworthy shape for
    use sites); the security policy that `materialize[].from` must be a committed
    `*.example.*` template and resolve inside the repo is enforced at the
    materialize use-site (orchestrator), where it can emit telemetry on rejection.
    """
    if not isinstance(raw, dict):
        return None
    cmd = raw.get("cmd")
    if not (isinstance(cmd, list) and cmd and all(isinstance(x, str) for x in cmd)):
        return None  # cmd is the one required field; without it app_boot is meaningless
    out: dict = {"cmd": [str(x) for x in cmd]}
    env = raw.get("env")
    if isinstance(env, dict) and env:
        out["env"] = {str(k): str(v) for k, v in env.items()}
    ready_url = raw.get("ready_url")
    if isinstance(ready_url, str) and ready_url:
        out["ready_url"] = ready_url
    rt = raw.get("ready_timeout_s")
    if isinstance(rt, (int, float)) and rt > 0:
        out["ready_timeout_s"] = int(rt)
    mat = raw.get("materialize")
    if isinstance(mat, list) and mat:
        clean_mat = [
            {"from": str(m["from"]), "to": str(m["to"])}
            for m in mat
            if isinstance(m, dict) and isinstance(m.get("from"), str) and isinstance(m.get("to"), str)
        ]
        if clean_mat:
            out["materialize"] = clean_mat
    pre = raw.get("pre_cmd")
    if isinstance(pre, list) and pre:
        clean_pre = [
            [str(tok) for tok in step]
            for step in pre
            if isinstance(step, list) and step and all(isinstance(tok, str) for tok in step)
        ]
        if clean_pre:
            out["pre_cmd"] = clean_pre
    return out


@dataclass
class RepoConfig:
    repo_root: Path
    agent_branch: str
    main_ref: str
    test_cmd: list[str] | None  # None = auto-detect via brownfield.detect_test_command
    test_env: dict[str, str] | None  # extra env merged into the gate test subprocess
    doctrine: str | None        # None = derive from target_status
    source: str                 # "file" | "default"
    api_route_globs: list[str] | None = None  # None = use DEFAULT_API_ROUTE_GLOBS
    ui_globs: list[str] | None = None          # None = use DEFAULT_UI_GLOBS
    test_file_globs: list[str] | None = None   # None = built-in per-language conventions (run_bl_tests)
    app_boot: dict | None = None               # None = compose path; native-boot contract for acceptance (PROPOSAL_NATIVE_BOOT_ACCEPTANCE)

    def effective_api_route_globs(self) -> list[str]:
        return self.api_route_globs or list(DEFAULT_API_ROUTE_GLOBS)

    def effective_ui_globs(self) -> list[str]:
        return self.ui_globs or list(DEFAULT_UI_GLOBS)

    def to_dict(self) -> dict:
        return {
            "agent_branch": self.agent_branch,
            "main_ref": self.main_ref,
            "test_cmd": self.test_cmd,
            "test_env": self.test_env,
            "doctrine": self.doctrine,
            "api_route_globs": self.api_route_globs,
            "test_file_globs": self.test_file_globs,
            "app_boot": self.app_boot,
            "source": self.source,
        }


def _git_branch_exists(repo_root: Path, branch: str) -> bool:
    """Cheap check — returns True if `branch` is a valid ref in the repo."""
    if not shutil.which("git"):
        return False
    import subprocess
    code = subprocess.call(
        ["git", "rev-parse", "--verify", "--quiet", branch],
        cwd=str(repo_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return code == 0


def load(repo_root: Path) -> RepoConfig:
    """Load .agentic-skills.json from the repo root, falling back to defaults.

    Behavior when the file is absent:
    - agent_branch = "agentic-skills-work" IF that branch exists in the repo,
      otherwise "main" (preserves backward compatibility for repos that have
      never been bootstrapped).
    - main_ref = "main" (or whatever the default branch is named locally).
    """
    config_path = repo_root / CONFIG_FILENAME
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text())
            agent_branch = data.get("agent_branch") or DEFAULT_AGENT_BRANCH
            main_ref = data.get("main_ref") or DEFAULT_MAIN_REF
            test_cmd = data.get("test_cmd")
            test_env = data.get("test_env")
            doctrine = data.get("doctrine")
            api_route_globs = data.get("api_route_globs")
            ui_globs = data.get("ui_globs")
            test_file_globs = data.get("test_file_globs")
            app_boot = _normalize_app_boot(data.get("app_boot"))
            return RepoConfig(
                repo_root=repo_root,
                agent_branch=agent_branch,
                main_ref=main_ref,
                test_cmd=list(test_cmd) if isinstance(test_cmd, list) else None,
                test_env=(
                    {str(k): str(v) for k, v in test_env.items()}
                    if isinstance(test_env, dict) and test_env
                    else None
                ),
                doctrine=doctrine,
                api_route_globs=(
                    list(api_route_globs)
                    if isinstance(api_route_globs, list) and api_route_globs
                    else None
                ),
                ui_globs=(
                    list(ui_globs)
                    if isinstance(ui_globs, list) and ui_globs
                    else None
                ),
                test_file_globs=(
                    list(test_file_globs)
                    if isinstance(test_file_globs, list) and test_file_globs
                    else None
                ),
                app_boot=app_boot,
                source="file",
            )
        except (OSError, json.JSONDecodeError):
            pass

    # Default path: prefer agentic-skills-work if it already exists; else main.
    branch = DEFAULT_AGENT_BRANCH if _git_branch_exists(repo_root, DEFAULT_AGENT_BRANCH) else DEFAULT_MAIN_REF
    return RepoConfig(
        repo_root=repo_root,
        agent_branch=branch,
        main_ref=DEFAULT_MAIN_REF,
        test_cmd=None,
        test_env=None,
        doctrine=None,
        source="default",
    )


def write(repo_root: Path, *, agent_branch: str = DEFAULT_AGENT_BRANCH, main_ref: str = DEFAULT_MAIN_REF, test_cmd: list[str] | None = None, test_env: dict[str, str] | None = None, doctrine: str | None = None) -> Path:
    """Write a fresh .agentic-skills.json. Used when bootstrapping a target."""
    config_path = repo_root / CONFIG_FILENAME
    payload = {
        "agent_branch": agent_branch,
        "main_ref": main_ref,
    }
    if test_cmd:
        payload["test_cmd"] = test_cmd
    if test_env:
        payload["test_env"] = test_env
    if doctrine:
        payload["doctrine"] = doctrine
    config_path.write_text(json.dumps(payload, indent=2) + "\n")
    return config_path
