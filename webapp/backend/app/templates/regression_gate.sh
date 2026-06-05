#!/bin/sh
# Regression-gate test runner for the brownfield agentic-skills pipeline.
#
# Three test suites:
#   1. fe-lint        — biome + tsc + vite build (frontend Dockerfile build stage)
#   2. backend pytest — full backend test suite via in-process TestClient
#   3. playwright E2E — runs against a freshly brought-up stack (db+backend+frontend)
#
# Emits synthetic pytest-format lines for fe-lint and playwright suite results
# so the existing regression_gate.py parser (PYTEST_RESULT_RE) treats them as
# regression-detectable entries:
#   tests/frontend::lint_typecheck_build PASSED|FAILED
#   tests/playwright::e2e_suite          PASSED|FAILED
#
# Exits 0 on full green, non-zero on any failure. Always cleans up.

set +e

COMPOSE="docker compose -f compose.yml -f compose.gate.yml"

cleanup() {
  $COMPOSE --profile gate-e2e --profile gate-lint down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

# Idempotent network creation — compose.yml expects traefik-public to exist.
docker network inspect traefik-public >/dev/null 2>&1 || docker network create traefik-public >/dev/null

# Stale Playwright artifacts from a prior run leak through the bind mount
# and cause biome to lint generated JSON. Clean before each gate run.
rm -rf frontend/test-results frontend/blob-report frontend/playwright-report 2>/dev/null

# ─── 1. Build images (uv + bun caches make rebuilds fast) ──────────────
$COMPOSE --profile gate-e2e --profile gate-lint build || { echo "tests/gate::build FAILED"; exit 1; }

# ─── 2. Frontend lint + typecheck + build (fail-fast) ──────────────────
$COMPOSE --profile gate-lint run --rm --no-deps fe-lint
fe_rc=$?
if [ $fe_rc -eq 0 ]; then
  echo "tests/frontend::lint_typecheck_build PASSED"
else
  echo "tests/frontend::lint_typecheck_build FAILED"
fi

# ─── 3. Bring stack up and wait for healthchecks ───────────────────────
$COMPOSE up -d db mailcatcher backend frontend >/dev/null 2>&1
ready=0
for i in $(seq 1 30); do
  s_be=$($COMPOSE ps backend --format '{{.Health}}' 2>/dev/null)
  s_fe=$($COMPOSE ps frontend --format '{{.Health}}' 2>/dev/null)
  if [ "$s_be" = "healthy" ] && [ "$s_fe" = "healthy" ]; then
    ready=1
    break
  fi
  sleep 3
done
if [ $ready -ne 1 ]; then
  echo "tests/gate::stack_healthy FAILED  # backend=$s_be frontend=$s_fe"
  exit 1
fi

# ─── 4. Backend pytest (in-process TestClient; uses fresh DB) ──────────
# A32: per-test timeout (120s) via pytest-timeout, installed inline since
# the vanilla backend image doesn't bundle it. Any deadlock-prone test
# (Alembic DDL vs session-scoped fixture, leaked TestClient connections,
# fixture race) now fails as a TEST result line ("Failed: Timeout >120s")
# instead of hanging until the orchestrator's 30-min asyncio wait_for
# fires. The shell `timeout 900` is defense-in-depth — if pytest itself
# wedges, the whole invocation dies at 15 min and the orchestrator sees
# a non-zero exit immediately.
$COMPOSE run --rm --no-deps \
  -v "$PWD/backend/tests:/app/backend/tests:ro" \
  backend bash -c "uv pip install --quiet pytest-timeout && timeout 900 pytest -v --timeout=120 --timeout-method=signal tests"
be_rc=$?

# ─── 5. Playwright E2E against running stack ───────────────────────────
# A49: `--retries=2` is passed explicitly so the gate's flake tolerance is
# self-contained and does NOT depend on the target repo's playwright.config
# reading CI env (full-stack-fastapi-template already sets
# `retries: process.env.CI ? 2 : 0`, so on that target this is belt-and-
# suspenders; on a target whose config omits CI-retries it is the actual
# source of retry tolerance). A test that fails then passes on retry counts
# as `flaky` → exit 0 → PASSED. Note: this does NOT rescue a transient
# (socket hang up / ECONNRESET) that fails ALL retries — that case is
# annotated downstream by regression_gate.detect_transient_markers (A49),
# pending an operator-approved verdict-reclassification doctrine change.
$COMPOSE --profile gate-e2e run --rm -e CI=1 playwright bunx playwright test --retries=2
e2e_rc=$?
if [ $e2e_rc -eq 0 ]; then
  echo "tests/playwright::e2e_suite PASSED"
else
  echo "tests/playwright::e2e_suite FAILED"
fi

# Composite exit: only green if frontend lint AND backend tests AND playwright are all 0.
if [ $fe_rc -eq 0 ] && [ $be_rc -eq 0 ] && [ $e2e_rc -eq 0 ]; then
  exit 0
fi
exit 1
