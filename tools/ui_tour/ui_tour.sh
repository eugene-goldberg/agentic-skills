#!/usr/bin/env bash
# UI tour — boots the target repo's branch in an isolated docker stack,
# runs a playwright tour that screenshots every curated route (and dialog
# open states), then preserves the screenshots under
#   webapp/backend/screenshots/<repo>-<branch>-<ts>/
# and prints absolute paths.
#
# Usage:
#   tools/ui_tour/ui_tour.sh [branch] [repo]
#
# Defaults: branch=time-tracking, repo=full-stack-fastapi-template.
# Safe to run while a sprint is in flight — uses git worktree to a sandbox
# dir (does not touch the orchestrator's working tree) and a unique
# COMPOSE_PROJECT_NAME so the temporary stack doesn't collide with the
# gate's stacks. Cleanup runs even on error via trap.

set -euo pipefail

BRANCH="${1:-time-tracking}"
REPO="${2:-full-stack-fastapi-template}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AS_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TARGET="${BROWNFIELD_TARGETS_ROOT:-/Users/eugenegoldberg/dev/ai-projects/brownfield-targets}/$REPO"
WORKTREE="/tmp/ui-tour-${BRANCH}-${TS}"
OUT_DIR="$AS_ROOT/webapp/backend/screenshots/${REPO}-${BRANCH}-${TS}"
COMPOSE_PROJECT="uitour-$(echo "$BRANCH-$TS" | tr -c 'a-z0-9' '-' | head -c 50)"

cleanup() {
  echo ""
  echo "[ui_tour] cleanup…"
  ( cd "$WORKTREE" 2>/dev/null && \
    COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT" docker compose -f compose.yml -f compose.gate.yml down -v --remove-orphans 2>/dev/null ) || true
  git -C "$TARGET" worktree remove "$WORKTREE" --force 2>/dev/null || true
  rm -rf "$WORKTREE" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

mkdir -p "$OUT_DIR"

echo "[ui_tour] branch=$BRANCH  repo=$REPO  ts=$TS"
echo "[ui_tour] out=$OUT_DIR"

# 1. Worktree-checkout the branch into a sandbox dir.
#    Use --detach because the branch is almost certainly already checked
#    out in the main repo and git refuses two worktrees on the same branch.
#    --detach creates a detached HEAD at the branch's tip SHA, which is
#    all we need for read-only tour purposes.
BRANCH_SHA="$(git -C "$TARGET" rev-parse "$BRANCH")"
echo "[ui_tour] forking detached worktree at $BRANCH ($BRANCH_SHA) → $WORKTREE"
git -C "$TARGET" worktree add --detach "$WORKTREE" "$BRANCH_SHA"

cd "$WORKTREE"

# 2. Drop the tour spec + config into the worktree.
cp "$SCRIPT_DIR/_tour_template.spec.ts" frontend/tests/_ui_tour.spec.ts
cp "$SCRIPT_DIR/playwright.tour.config.ts" frontend/playwright.tour.config.ts
mkdir -p frontend/test-results/tour

# 3. Idempotent traefik-public network (compose.yml depends on it).
docker network inspect traefik-public >/dev/null 2>&1 || docker network create traefik-public >/dev/null

# 4. Boot the stack (db + backend + frontend + mailcatcher + prestart) in
#    isolation. We explicitly bring up `prestart` FIRST and wait for it to
#    exit 0 — prestart runs `alembic upgrade head` AND seeds the
#    firstSuperuser. Without this wait, backend is "healthy" (HTTP responsive)
#    but the User table is empty, so auth.setup's login returns 401 silently
#    (no toast, no redirect — exactly the failure mode we observed).
echo "[ui_tour] booting stack as project=$COMPOSE_PROJECT"
COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT" \
  docker compose -f compose.yml -f compose.gate.yml build backend frontend

# Bring up db first, wait for healthy, then run prestart synchronously
# (up --wait makes docker-compose wait for service_completed_successfully).
COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT" \
  docker compose -f compose.yml -f compose.gate.yml up -d db mailcatcher

echo "[ui_tour] waiting for db healthy + prestart migrations + seed…"
# Run prestart attached so $? captures its container exit code directly.
# (`docker compose ps prestart` doesn't list stopped one-shot services
# without --all, so we use the up command's exit code instead.)
COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT" \
  docker compose -f compose.yml -f compose.gate.yml up --no-log-prefix --exit-code-from prestart prestart
prestart_rc=$?
echo "[ui_tour] prestart exited with code $prestart_rc"
[ "$prestart_rc" = "0" ] || {
  echo "[ui_tour] ERROR: prestart did not exit 0 — DB may not be migrated/seeded"
  exit 1
}

COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT" \
  docker compose -f compose.yml -f compose.gate.yml up -d backend
# NOTE: we skip the static frontend container — playwright's webServer
# block spawns `bun run dev` inside its own container on localhost:5173,
# which matches BACKEND_CORS_ORIGINS (the static `http://frontend:80`
# origin is NOT in CORS, causing silent login failures).

# 5. Wait for backend healthy.
echo "[ui_tour] waiting for backend healthy…"
for i in $(seq 1 40); do
  be=$(COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT" docker compose -f compose.yml -f compose.gate.yml ps backend --format '{{.Health}}' 2>/dev/null || echo "")
  [ "$be" = "healthy" ] && { echo "[ui_tour] backend healthy"; break; }
  sleep 3
done
[ "$be" = "healthy" ] || {
  echo "[ui_tour] ERROR: backend did not become healthy (backend=$be)"
  exit 1
}

# 5b. Smoke-test the login endpoint directly so a backend failure is caught
# here (with a clear log) instead of inside the playwright headless run.
echo "[ui_tour] smoke-testing backend login endpoint…"
smoke=$(COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT" \
  docker compose -f compose.yml -f compose.gate.yml exec -T backend \
  curl -sf -o /dev/null -w "%{http_code}" \
  -X POST -d "username=admin@example.com&password=changethis" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  http://localhost:8000/api/v1/login/access-token 2>/dev/null || echo "??")
echo "[ui_tour] backend login smoke-test HTTP $smoke (expect 200)"
[ "$smoke" = "200" ] || {
  echo "[ui_tour] WARN: backend login smoke-test did not return 200; auth.setup will likely fail"
}

# 6. Run the tour inside the playwright container.
echo "[ui_tour] running playwright tour…"
COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT" \
  docker compose -f compose.yml -f compose.gate.yml --profile gate-e2e run --rm \
  -v "$WORKTREE/frontend/test-results:/app/frontend/test-results" \
  playwright bunx playwright test --config=playwright.tour.config.ts || \
  echo "[ui_tour] (tour exited non-zero — partial screenshots may still be present)"

# 7. Copy screenshots out to persistent location.
#    Includes (a) curated tour shots under test-results/tour/ and
#    (b) playwright auto-failure shots under test-results/<test-id>/.
echo "[ui_tour] preserving screenshots → $OUT_DIR"
echo "[ui_tour] inventory of test-results before copy:"
find "$WORKTREE/frontend/test-results" -name "*.png" 2>/dev/null | sed 's|^|  |' || true
find "$WORKTREE/frontend/test-results/tour" -name "*.png" -exec cp {} "$OUT_DIR/" \; 2>/dev/null || true
# Auto-failure screenshots get a "failure_" prefix and the test-id slug.
mkdir -p "$OUT_DIR/failures"
find "$WORKTREE/frontend/test-results" -name "test-failed-*.png" 2>/dev/null | while read -r f; do
  rel="$(dirname "${f#$WORKTREE/frontend/test-results/}")"
  cp "$f" "$OUT_DIR/failures/${rel//\//__}__$(basename "$f")" 2>/dev/null || true
done
# Also copy error-context.md files which include console + page state at failure.
find "$WORKTREE/frontend/test-results" -name "error-context.md" 2>/dev/null | while read -r f; do
  rel="$(dirname "${f#$WORKTREE/frontend/test-results/}")"
  cp "$f" "$OUT_DIR/failures/${rel//\//__}__$(basename "$f")" 2>/dev/null || true
done

# 8. Surface absolute paths.
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  UI TOUR COMPLETE — screenshots at:"
echo "════════════════════════════════════════════════════════════════"
ls -1 "$OUT_DIR"/*.png 2>/dev/null | sort | while read -r f; do
  size_kb=$(( $(stat -f%z "$f" 2>/dev/null || stat -c%s "$f") / 1024 ))
  echo "  $f  (${size_kb} KB)"
done
echo ""
echo "Open in macOS Preview:"
echo "  open $OUT_DIR/*.png"
