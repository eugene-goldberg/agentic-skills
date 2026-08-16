#!/usr/bin/env bash
# agentic-skills regression gate — .NET template (xunit / NUnit / MSTest).
#
# Copy to <target>/scripts/regression_gate.sh and reference it from
# .agentic-skills.json::test_cmd as ["bash","scripts/regression_gate.sh"].
#
# Contract with the harness (webapp/backend/app/services/regression_gate.py
# → classify_gate_outcome):
#   * per-test verdicts must match  ^tests?/<path>::<name> (PASSED|FAILED)
#     — `dotnet test` does NOT emit that shape, so we convert its TRX/console
#     output below. Without this the parser sees zero results and correctly
#     reports `inconclusive` (never a false green).
#   * non-test steps emit pseudo-test sentinels so a compile break is
#     classified `build_fail` (A39a) instead of "every test regressed":
#       tests/gate::restore   — NuGet restore (private feed auth lands here)
#       tests/gate::build     — compilation
#   * COMPOSE_PROJECT_NAME is set by the harness (M2-1); never override it.
#   * cleanup trap on every exit path (A48).
#   * macOS has no coreutils `timeout`; with_timeout() is the portable form.
set -uo pipefail

GATE_FAILED=0
TRX_DIR="${TMPDIR:-/tmp}/agentic-gate-trx-$$"
SOLUTION="${GATE_SOLUTION:-}"          # optional: path to .sln, else auto-detect

say()  { echo "[gate] $*"; }
pass() { echo "$1 PASSED"; }
fail() { echo "$1 FAILED"; GATE_FAILED=1; }

with_timeout() {
  local secs="$1"; shift
  if command -v timeout >/dev/null 2>&1; then timeout "$secs" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then gtimeout "$secs" "$@"
  else perl -e 'alarm shift; exec @ARGV' "$secs" "$@"
  fi
}

cleanup() {
  rm -rf "$TRX_DIR" 2>/dev/null || true
  # Only reap compose stacks if this repo actually uses them for tests.
  if [ -f docker-compose.test.yml ] || [ -f compose.gate.yml ]; then
    docker compose -f compose.gate.yml down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

[ -z "$SOLUTION" ] && SOLUTION="$(ls ./*.sln 2>/dev/null | head -1)"
TARGET="${SOLUTION:-.}"
say "target: $TARGET"

# ── Step 1: restore ─────────────────────────────────────────────────────────
# Private Azure DevOps Artifacts feeds live in nuget.config. CI substitutes
# __nugetUser__ / credentials; locally the operator must have run
#   dotnet nuget add source <feed> -u <user> -p <PAT> --store-password-in-clear-text
# A 401 here surfaces as build_fail with the auth error in the reason — the
# engineer is told it is an environment problem, not a code problem.
say "dotnet restore"
if with_timeout 900 dotnet restore "$TARGET" --nologo 2>&1; then
  pass "tests/gate::restore"
else
  fail "tests/gate::restore"
  echo "[gate] restore failed — check private feed auth (nuget.config)"
  exit 1
fi

# ── Step 2: build ───────────────────────────────────────────────────────────
say "dotnet build"
if with_timeout 900 dotnet build "$TARGET" --nologo --no-restore -c Release 2>&1; then
  pass "tests/gate::build"
else
  fail "tests/gate::build"
  exit 1
fi

# ── Step 3: test, converted to the harness nodeid contract ──────────────────
mkdir -p "$TRX_DIR"
say "dotnet test (trx → nodeid conversion)"
with_timeout 1800 dotnet test "$TARGET" --nologo --no-build -c Release \
  --logger "trx;LogFileName=results.trx" --results-directory "$TRX_DIR" 2>&1
TEST_RC=$?

# Convert every TRX UnitTestResult into `tests/<class>::<method> PASSED|FAILED`.
# Class name becomes the path segment so nodeids stay stable and readable.
python3 - "$TRX_DIR" <<'PYEOF'
import glob, os, sys, xml.etree.ElementTree as ET
ns = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}
n = 0
for path in glob.glob(os.path.join(sys.argv[1], "**", "*.trx"), recursive=True):
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        continue
    for r in root.findall(".//t:UnitTestResult", ns):
        name = r.get("testName") or ""
        outcome = (r.get("outcome") or "").lower()
        # Fully-qualified name → Namespace.Class.Method; split off the method.
        cls, _, method = name.rpartition(".")
        nodeid = f"tests/{cls.replace('.', '/') or 'unknown'}::{method or name}"
        if outcome == "passed":
            print(f"{nodeid} PASSED"); n += 1
        elif outcome in ("failed", "error", "timeout"):
            print(f"{nodeid} FAILED"); n += 1
            msg = r.find(".//t:Message", ns)
            if msg is not None and msg.text:
                print(f"    {msg.text.strip()[:400]}")
print(f"[gate] converted {n} test result(s) from trx", file=sys.stderr)
PYEOF

if [ "$TEST_RC" != "0" ]; then
  say "dotnet test exit=$TEST_RC"
  GATE_FAILED=1
fi

exit $GATE_FAILED
