#!/usr/bin/env bash
# Phase 4 A/B harness: same model, same brief, with vs. without retrieval.
# Sequential runs, archived to ab_runs/{label}/runs/ so they don't collide.
#
# Usage:
#   scripts/ab_run.sh <env_file> <label_a> <label_b>
# Example:
#   scripts/ab_run.sh .env.gpt54 control treatment

set -euo pipefail

ENV_FILE="${1:-.env.gpt54}"
LABEL_A="${2:-control}"
LABEL_B="${3:-treatment}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

AB_DIR="ab_runs/$(date -u +%Y%m%dT%H%M%S)"
mkdir -p "$AB_DIR"

source .venv-lg/bin/activate

bootstrap_target() {
  rm -rf runs/po-lg-lg-SKILLS runs/eng-lg-lg-SKILLS-* runs/qa-lg-lg-SKILLS-* target-repos/lg-graph-test
  mkdir -p target-repos/lg-graph-test
  cd target-repos/lg-graph-test
  python3.12 -m venv .venv >/dev/null
  source .venv/bin/activate
  pip install -q --upgrade pip
  pip install -q 'fastapi>=0.136.1' 'sqlalchemy>=2.0.49' 'pydantic>=2.13.4' uvicorn pytest httpx
  deactivate
  cd "$ROOT"
  source .venv-lg/bin/activate
}

run_one() {
  local label="$1"
  local retrieval="$2"   # 0 or 1
  local logf="$AB_DIR/$label.log"
  echo "=== [$label] retrieval=$retrieval ==="
  bootstrap_target
  # Load env
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
  export RETRIEVAL_ENABLED="$retrieval"
  local ref_arg=()
  if [[ "$retrieval" == "1" ]]; then
    ref_arg=(--reference-repo "$ROOT/reference-repos/fastapi-good-patterns")
  fi
  # Run
  python -u -m langgraph_engine run \
    --project-name "project_tracker_v1" \
    --workspace "$ROOT" \
    --target-repo "$ROOT/target-repos/lg-graph-test" \
    --brief briefs/project_tracker_v1_po_planning.md \
    --po-skill skills/po/po-001-agile-v-product-owner/SKILLS.md \
    --eng-skill skills/engineer/eng-001-incremental-implementation/SKILLS.md \
    --qa-skill skills/qa/qa-001-test-engineer/SKILLS.md \
    "${ref_arg[@]}" \
    > "$logf" 2>&1 &
  local pid=$!
  echo "PID=$pid log=$logf"
  wait "$pid" || echo "[$label] exit=$?"
  # Archive run artifacts
  mkdir -p "$AB_DIR/$label"
  rsync -a runs/ "$AB_DIR/$label/runs/" 2>/dev/null || true
  rsync -a target-repos/lg-graph-test/ "$AB_DIR/$label/target/" --exclude .venv --exclude __pycache__ 2>/dev/null || true
  echo "[$label] artifacts -> $AB_DIR/$label/"
}

echo "AB dir: $AB_DIR"
run_one "$LABEL_A" 0
run_one "$LABEL_B" 1

echo
echo "=== compare scores ==="
python scripts/ab_compare.py "$AB_DIR" | tee "$AB_DIR/COMPARE.md"
