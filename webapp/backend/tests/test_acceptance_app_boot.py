"""Native-boot acceptance for non-compose targets (PROPOSAL_NATIVE_BOOT_ACCEPTANCE).

Covers the three locked decisions:
- A: materialize only from committed *.example.* templates, inside the worktree.
- agent-driven: the task prompt carries an explicit native-boot contract.
- Level-3: the prompt requires a NEW-feature-route check before journeys.
"""
from pathlib import Path

from app.services import orchestrator as o
from app.services.repo_config import _normalize_app_boot


# ---- config normalizer -----------------------------------------------------

def test_normalize_requires_cmd():
    assert _normalize_app_boot({"env": {"X": "1"}}) is None
    assert _normalize_app_boot("nope") is None
    assert _normalize_app_boot({"cmd": []}) is None


def test_normalize_clean_shape():
    out = _normalize_app_boot({
        "cmd": ["dotnet", "run", "--urls", "http://localhost:${PORT}"],
        "env": {"ASPNETCORE_ENVIRONMENT": "Development"},
        "ready_url": "http://localhost:${PORT}/api/v1/products",
        "ready_timeout_s": 180,
        "materialize": [{"from": "a.example.json", "to": "a.json"}, {"bad": "drop"}],
        "pre_cmd": [["dotnet", "ef", "database", "update"], "notalist"],
    })
    assert out["cmd"][-1] == "http://localhost:${PORT}"
    assert out["env"]["ASPNETCORE_ENVIRONMENT"] == "Development"
    assert out["ready_timeout_s"] == 180
    assert out["materialize"] == [{"from": "a.example.json", "to": "a.json"}]  # bad entry dropped
    assert out["pre_cmd"] == [["dotnet", "ef", "database", "update"]]          # non-list dropped


# ---- app_boot v2: frontend sub-block (PROPOSAL_LIVE_ACCEPTANCE_LOOP) --------

def test_frontend_absent_by_default():
    out = _normalize_app_boot({"cmd": ["dotnet", "run"]})
    assert "frontend" not in out


def test_frontend_requires_cmd():
    out = _normalize_app_boot({"cmd": ["dotnet", "run"], "frontend": {"dir": "frontend"}})
    assert "frontend" not in out  # no cmd ⇒ dropped


def test_frontend_clean_shape():
    out = _normalize_app_boot({
        "cmd": ["dotnet", "run", "--urls", "http://localhost:5096"],
        "frontend": {
            "dir": "frontend",
            "pre_cmd": [["npm", "ci"], "bad"],
            "cmd": ["npm", "run", "dev", "--", "--port", "${FE_PORT}"],
            "ready_url": "http://localhost:${FE_PORT}/",
            "ready_timeout_s": 180,
            "base_url_env": "VITE_API_URL",
        },
    })
    fe = out["frontend"]
    assert fe["dir"] == "frontend"
    assert fe["cmd"][-1] == "${FE_PORT}"
    assert fe["pre_cmd"] == [["npm", "ci"]]  # non-list dropped
    assert fe["ready_url"] == "http://localhost:${FE_PORT}/"
    assert fe["ready_timeout_s"] == 180
    assert fe["base_url_env"] == "VITE_API_URL"


def test_frontend_dir_defaults_and_hardcoded_url():
    # base_url_env omitted ⇒ hardcoded-URL target (no key stored)
    out = _normalize_app_boot({
        "cmd": ["dotnet", "run"],
        "frontend": {"cmd": ["npm", "run", "dev"]},
    })
    fe = out["frontend"]
    assert fe["dir"] == "."            # default
    assert "base_url_env" not in fe    # hardcoded-URL semantics


# ---- port substitution -----------------------------------------------------

def test_resolve_app_boot_port_substitutes():
    ab = o._resolve_app_boot_port({
        "cmd": ["dotnet", "run", "--urls", "http://localhost:${PORT}"],
        "ready_url": "http://localhost:${PORT}/h",
        "pre_cmd": [["x", "--at", "${PORT}"]],
    }, 5099)
    assert ab["cmd"][-1] == "http://localhost:5099"
    assert ab["ready_url"] == "http://localhost:5099/h"
    assert ab["pre_cmd"] == [["x", "--at", "5099"]]
    assert ab["_port"] == 5099


def test_alloc_free_port_is_usable():
    p = o._alloc_free_port()
    assert isinstance(p, int) and 1024 < p < 65536


def test_resolve_app_boot_port_resolves_frontend(tmp_path):
    ab = o._resolve_app_boot_port({
        "cmd": ["dotnet", "run", "--urls", "http://localhost:5096"],
        "ready_url": "http://localhost:5096/api/v1/Products",
        "frontend": {
            "dir": "frontend",
            "pre_cmd": [["npm", "ci"]],
            "cmd": ["npm", "run", "dev", "--", "--port", "${FE_PORT}"],
            "ready_url": "http://localhost:${FE_PORT}/",
        },
    }, 5096, 4317)
    assert ab["_port"] == 5096
    fe = ab["frontend"]
    assert fe["_port"] == 4317
    assert fe["cmd"][-1] == "4317"
    assert fe["ready_url"] == "http://localhost:4317/"
    assert fe["pre_cmd"] == [["npm", "ci"]]


def test_prompt_full_app_drives_frontend_and_playwright():
    ab = o._resolve_app_boot_port({
        "cmd": ["dotnet", "run", "--urls", "http://localhost:5096"],
        "ready_url": "http://localhost:5096/api/v1/Products",
        "frontend": {"dir": "frontend", "cmd": ["npm", "run", "dev", "--", "--port", "${FE_PORT}"],
                     "ready_url": "http://localhost:${FE_PORT}/"},
    }, 5096, 4317)
    p = o._build_acceptance_task("SKILL", app_boot=ab, **_COMMON)
    assert "BOOT THE REAL FRONTEND TOO" in p
    assert "4317" in p                                  # FE port surfaced
    assert "Playwright" in p
    assert "VERIFY PERSISTENCE" in p
    assert "EVIDENCE PER CRITERION" in p
    assert "evidence` MUST cite a real" in p


def test_prompt_backend_only_has_no_frontend_block():
    ab = o._resolve_app_boot_port(
        {"cmd": ["dotnet", "run", "--urls", "http://localhost:${PORT}"],
         "ready_url": "http://localhost:${PORT}/h"}, 5099)
    p = o._build_acceptance_task("SKILL", app_boot=ab, **_COMMON)
    assert "BOOT THE APP NATIVELY" in p
    assert "BOOT THE REAL FRONTEND TOO" not in p        # no frontend ⇒ no UI block


# ---- materialize security (decision A) -------------------------------------

def test_materialize_copies_example_template(tmp_path: Path):
    (tmp_path / "cfg.example.json").write_text('{"db":"local"}')
    res = o._materialize_app_boot(
        {"materialize": [{"from": "cfg.example.json", "to": "cfg.json"}]}, tmp_path)
    assert res[0]["ok"] is True
    assert (tmp_path / "cfg.json").read_text() == '{"db":"local"}'


def test_materialize_rejects_non_example_source(tmp_path: Path):
    (tmp_path / "secrets.json").write_text("SECRET")
    res = o._materialize_app_boot(
        {"materialize": [{"from": "secrets.json", "to": "cfg.json"}]}, tmp_path)
    assert res[0]["ok"] is False
    assert "*.example.*" in res[0]["reason"]
    assert not (tmp_path / "cfg.json").exists()  # nothing copied


def test_materialize_rejects_escape_source(tmp_path: Path):
    res = o._materialize_app_boot(
        {"materialize": [{"from": "../outside.example.json", "to": "cfg.json"}]}, tmp_path)
    assert res[0]["ok"] is False
    assert "escapes worktree" in res[0]["reason"]


def test_materialize_rejects_escape_dest(tmp_path: Path):
    (tmp_path / "cfg.example.json").write_text("x")
    res = o._materialize_app_boot(
        {"materialize": [{"from": "cfg.example.json", "to": "../escape.json"}]}, tmp_path)
    assert res[0]["ok"] is False
    assert "escapes worktree" in res[0]["reason"]


# ---- prompt: native vs compose (agent-driven + Level-3) --------------------

_COMMON = dict(run_id="r", feature_slug="f", brief_rel="b", backlog_rel="bk",
               acceptance_rel="a", compose_project="proj", attempt=1)


def test_prompt_native_when_app_boot_set():
    ab = o._resolve_app_boot_port(
        {"cmd": ["dotnet", "run", "--urls", "http://localhost:${PORT}"],
         "ready_url": "http://localhost:${PORT}/api/v1/products",
         "pre_cmd": [["dotnet", "ef", "database", "update"]]}, 5099)
    p = o._build_acceptance_task("SKILL", app_boot=ab, **_COMMON)
    assert "BOOT THE APP NATIVELY" in p
    assert "5099" in p
    assert "LEVEL-3 READINESS" in p
    assert "dotnet ef database update" in p          # pre_cmd surfaced
    assert "COMPOSE_PROJECT_NAME" not in p           # compose line suppressed


def test_prompt_compose_when_app_boot_absent():
    p = o._build_acceptance_task("SKILL", app_boot=None, **_COMMON)
    assert "COMPOSE_PROJECT_NAME=proj" in p
    assert "BOOT THE APP NATIVELY" not in p
