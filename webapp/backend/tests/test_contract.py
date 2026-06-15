"""Contract-First Phase 1 — unit tests for the R22 validation + conformance core
(app.services.contract). Pure functions, no harness/IO; runs in the backend venv.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import contract as C  # noqa: E402


VALID_SPEC = """\
openapi: 3.1.0
info:
  title: Product Questions API
  version: 1.0.0
paths:
  /api/products/{productId}/questions:
    get:
      operationId: listProductQuestions
      responses:
        '200':
          description: ok
    post:
      operationId: addProductQuestion
      responses:
        '201':
          description: created
  /api/questions/{id}:
    get:
      operationId: getQuestion
      responses:
        '200':
          description: ok
"""


# ── parse ────────────────────────────────────────────────────────────────────

def test_parse_valid() -> None:
    spec = C.parse_openapi(VALID_SPEC)
    assert spec["openapi"] == "3.1.0"
    assert spec["info"]["title"] == "Product Questions API"


def test_parse_non_mapping_raises() -> None:
    with pytest.raises(ValueError):
        C.parse_openapi("- just\n- a\n- list\n")


# ── validate_openapi ───────────────────────────────────────────────────────────

def test_validate_clean() -> None:
    assert C.validate_openapi(C.parse_openapi(VALID_SPEC)) == []


def test_validate_bad_version() -> None:
    spec = C.parse_openapi(VALID_SPEC)
    spec["openapi"] = "2.0"
    errs = C.validate_openapi(spec)
    assert any("3.x" in e for e in errs)


def test_validate_missing_title() -> None:
    spec = C.parse_openapi(VALID_SPEC)
    spec["info"] = {}
    assert any("info.title" in e for e in C.validate_openapi(spec))


def test_validate_empty_paths() -> None:
    spec = {"openapi": "3.1.0", "info": {"title": "x"}, "paths": {}}
    assert any("paths" in e for e in C.validate_openapi(spec))


def test_validate_path_without_operation() -> None:
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "x"},
        "paths": {"/x": {"description": "no verb here"}},
    }
    assert any("no HTTP operation" in e for e in C.validate_openapi(spec))


# ── operations ─────────────────────────────────────────────────────────────────

def test_operations_flatten() -> None:
    ops = C.operations(C.parse_openapi(VALID_SPEC))
    assert len(ops) == 3
    keys = {(o["method"], o["path"]) for o in ops}
    assert ("get", "/api/products/{productId}/questions") in keys
    assert ("post", "/api/products/{productId}/questions") in keys
    assert {o["operationId"] for o in ops} == {
        "listProductQuestions", "addProductQuestion", "getQuestion",
    }


# ── conformance ────────────────────────────────────────────────────────────────

def _stub_corpus_all_ops() -> str:
    # A pretend generated-stub corpus referencing every operationId.
    return (
        "public interface IProductQuestionsController {\n"
        "  Task ListProductQuestions();  // listProductQuestions\n"
        "  Task AddProductQuestion();    // addProductQuestion\n"
        "  Task GetQuestion();           // getQuestion\n"
        "}\n"
    )


def test_conformance_all_present() -> None:
    spec = C.parse_openapi(VALID_SPEC)
    assert C.conformance_report(spec, _stub_corpus_all_ops()) == []


def test_conformance_missing_one() -> None:
    spec = C.parse_openapi(VALID_SPEC)
    corpus = _stub_corpus_all_ops().replace("getQuestion", "somethingElse")
    missing = C.conformance_report(spec, corpus)
    assert len(missing) == 1
    assert "getQuestion" in missing[0]


def test_conformance_path_fallback_when_no_opid() -> None:
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "x"},
        "paths": {"/api/widgets": {"get": {"responses": {"200": {"description": "ok"}}}}},
    }
    assert C.conformance_report(spec, "route: /api/widgets") == []
    assert C.conformance_report(spec, "nothing here") == ["GET /api/widgets"]


# ── contract_report (the R22 entry point) ───────────────────────────────────────

def test_report_ok_contract_only() -> None:
    r = C.contract_report(VALID_SPEC)
    assert r["ok"] is True
    assert r["validation_errors"] == [] and r["unconformant"] == []


def test_report_ok_with_conformant_stubs() -> None:
    r = C.contract_report(VALID_SPEC, _stub_corpus_all_ops())
    assert r["ok"] is True


def test_report_validation_failure() -> None:
    r = C.contract_report("openapi: 2.0\ninfo: {title: x}\npaths: {}\n")
    assert r["ok"] is False
    assert r["validation_errors"]


def test_report_conformance_failure() -> None:
    r = C.contract_report(VALID_SPEC, "interface Empty {}")
    assert r["ok"] is False
    assert len(r["unconformant"]) == 3


def test_report_unparseable() -> None:
    r = C.contract_report(": : not valid yaml : :\n\t- broken")
    assert r["ok"] is False
    assert any("unparseable" in e for e in r["validation_errors"])
