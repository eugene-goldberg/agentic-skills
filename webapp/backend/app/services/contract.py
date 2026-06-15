"""Contract-First Decomposition — Phase 1 (PROPOSAL_CONTRACT_FIRST_DECOMPOSITION.md).

R22 — a feature's interface contract is materialized as **compilable C# stubs
before any consuming slice runs**. This module is the *pure*, import-light
validation + conformance core that the R22 gate resolves to (it mirrors
``backlog.dependency_report`` for R21). The orchestrator wires these checks
plus the real ``dotnet build`` proof around the stub-materializer agent; this
module stays dependency-free and unit-testable.

Design decisions (operator 2026-06-15):
- Contract format = raw **OpenAPI 3.1** (Decision A), authored by the crew.
- Scope = the **HTTP seam** only (Decision B1).
- The materializer is a **crew agent**, not an external codegen tool — so the
  R22 guarantee is "the agent's stubs compile (``dotnet build`` green) AND
  conform to the contract", NOT byte-identical tool output. That makes the
  **conformance check below load-bearing.**
- **Zero new deps**: OpenAPI is parsed with the already-present PyYAML (YAML is
  a superset of JSON, so this also accepts a JSON contract).
"""
from __future__ import annotations

import re

import yaml

# The HTTP methods an OpenAPI path-item may carry as operation objects.
_HTTP_METHODS = (
    "get", "put", "post", "delete", "options", "head", "patch", "trace",
)


def parse_openapi(text: str) -> dict:
    """Parse an OpenAPI document (YAML or JSON) into a dict. Raises ValueError
    on anything that is not a mapping."""
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("contract is not a mapping at the top level")
    return data


def validate_openapi(spec: dict) -> list[str]:
    """Zero-dep structural validation of an OpenAPI 3.1 contract. Returns a
    list of human-readable errors (empty == structurally valid).

    This is intentionally NOT full JSON-Schema validation (that would be the
    deferred ``openapi-spec-validator`` dependency the operator declined). It
    asserts the load-bearing structure the materializer + conformance need:
    a 3.x version, an info.title, and a non-empty paths map where every path
    item declares at least one HTTP operation.
    """
    errs: list[str] = []

    version = str(spec.get("openapi", ""))
    if not version.startswith("3."):
        errs.append(f"openapi version must be 3.x, got {version!r}")

    info = spec.get("info")
    if not isinstance(info, dict) or not info.get("title"):
        errs.append("info.title is required")

    paths = spec.get("paths")
    if not isinstance(paths, dict) or not paths:
        errs.append("paths must be a non-empty mapping")
        return errs

    for path, item in paths.items():
        if not str(path).startswith("/"):
            errs.append(f"path {path!r} must start with '/'")
        if not isinstance(item, dict):
            errs.append(f"path item {path!r} must be a mapping")
            continue
        ops = [m for m in item if str(m).lower() in _HTTP_METHODS]
        if not ops:
            errs.append(f"path {path!r} declares no HTTP operation")

    return errs


def operations(spec: dict) -> list[dict]:
    """Flatten the contract to the operations a server stub must expose: one
    entry per (method, path) carrying its operationId (when declared)."""
    out: list[dict] = []
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if str(method).lower() not in _HTTP_METHODS:
                continue
            opid = op.get("operationId") if isinstance(op, dict) else None
            out.append(
                {"method": str(method).lower(), "path": str(path), "operationId": opid}
            )
    return out


def conformance_report(spec: dict, stub_text: str) -> list[str]:
    """Every contract operation must be represented in the generated C# stub
    corpus. Strict-but-language-agnostic (the same substring approach R19's
    coverage gate uses): the stubs must reference each ``operationId`` (when
    the contract declares one) OR the literal route path.

    Returns the list of unmatched operations (empty == conformant). A
    non-empty result is a blocking R22 finding that drives the no-abort loop.
    """
    missing: list[str] = []
    for op in operations(spec):
        opid = op.get("operationId")
        if opid:
            present = re.search(rf"\b{re.escape(opid)}\b", stub_text) is not None
        else:
            present = op["path"] in stub_text
        if not present:
            label = f"{op['method'].upper()} {op['path']}"
            if opid:
                label += f" ({opid})"
            missing.append(label)
    return missing


def contract_report(spec_text: str, stub_text: str = "") -> dict:
    """R22 check entry point (the ``doctrine_spec`` check_ref resolves here).

    Combines structural validation with (optional) stub conformance. Pass
    ``stub_text=""`` to validate the contract alone (pre-materialization);
    pass the concatenated generated-stub corpus to also assert conformance.

    Returns ``{"ok": bool, "validation_errors": [...], "unconformant": [...]}``.
    """
    try:
        spec = parse_openapi(spec_text)
    except Exception as e:  # malformed YAML/JSON or non-mapping top level
        return {
            "ok": False,
            "validation_errors": [f"unparseable contract: {e}"],
            "unconformant": [],
        }

    verrs = validate_openapi(spec)
    missing = conformance_report(spec, stub_text) if stub_text else []
    return {
        "ok": not verrs and not missing,
        "validation_errors": verrs,
        "unconformant": missing,
    }
