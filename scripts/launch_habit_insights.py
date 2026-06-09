#!/usr/bin/env python3
"""Launch the "Habit Insights" sprint on the real third-party brownfield target
`beaverhabits`. POSTs the brief to the orchestrator's /run-brief SSE endpoint
and tees the event stream to stdout (redirect to a log).

Purpose of THIS run (2026-06-08, architect): produce the FIRST post-A13 *sealed*
brownfield sprint so the Stage-2 doctrine-efficacy machinery has real data. The
feature itself is incidental — a small, read-only, lowest-risk additive analytic
chosen to seal the full engineer -> QA(bl_tests) -> merge -> acceptance ->
doctrine-meta pipeline. After completion, read
  traces_archive/<run>/doctrine_efficacy.json
and the doctrine_meta.efficacy event to confirm gate/kill firings now seal and
the never_fired vs unobserved split is honest. (Frontier #1.)

Run detached:
  cd webapp/backend && nohup ../../scripts/launch_habit_insights.py \
      > logs/harness/habit_insights_<ts>.log 2>&1 &
"""
import json
import time
import urllib.request

REPO = "beaverhabits"
URL = f"http://127.0.0.1:8000/api/projects/{REPO}/run-brief"

BRIEF = """Add "Habit Insights" — read-only statistics so a user can see how a habit is going.

Context: Users can complete habits day-to-day and the app already tracks a
current streak, but there is no way to look back and quantify how a habit has
performed over time. We want first-class, read-only insight endpoints that
report a habit's history without changing anything about how habits or records
are stored.

Requirements (product behavior — the implementation approach is yours to design
from the actual codebase):
1. A user can request a habit's completion statistics over a calendar date
   range via the API: the number of completed days in the range, the number of
   days in the range, and the completion rate as a fraction between 0.0 and 1.0.
   An empty range (zero days) must report a rate of 0.0, never an error or a
   divide-by-zero.
2. A user can request a habit's "best streak" — the length of the single
   longest run of consecutive completed days the habit has ever achieved —
   returned alongside its current streak so the two can be compared. A habit
   with no completions reports a best streak of 0.
3. Rest days must be honored consistently with the rest of the app: a rest day
   is not a completion (it does not count toward the completed-day total or the
   completion rate), and — exactly as for the current streak — a rest day
   bridges rather than breaks the best streak.
4. These endpoints are STRICTLY READ-ONLY. They must not create, mutate, or
   delete any habit, record, or persisted field. Requesting insights for a
   habit must leave that habit byte-for-byte unchanged.
5. Existing behavior must be preserved exactly. All existing tests must continue
   to pass.

Out of scope: UI styling polish, charts/graphs, CSV/JSON export, notifications,
caching. Do NOT add, remove, or change any PERSISTED field on a habit or record,
and do NOT touch, extend, or "improve" the application's storage backends,
persistence layer, or any infrastructure plumbing (file/disk storage, database
session wiring, the FilePersistentDict/user_file machinery). This feature is
ordinary read-only web-app business logic computed over the EXISTING habit/record
model and exposed over the EXISTING HTTP API — nothing below that line.

TESTING CONSTRAINTS (hard requirements — the regression gate depends on them):
- Put ALL of your new tests in a brand-new, dedicated file: tests/test_habit_insights.py.
- Do NOT modify, append to, or import wholesale any of the application's
  pre-existing test files (e.g. tests/test_storage.py, tests/test_apis.py,
  tests/test_gui.py). Those exercise the app's storage backends and other
  infrastructure that is OUT OF SCOPE here; editing them drags backend-storage
  smoke tests into this feature's gate, which is wrong.
- Your tests must target the FEATURE itself: the insight HTTP API endpoints and
  the completion-rate / best-streak business logic — the substance a user cares
  about. Test it the way you would test any typical web application: drive the
  HTTP API and assert behavior. Do not write tests about disk files, JSON
  serialization formats, or storage-backend internals.

Acceptance: the feature must be verifiable through the API. Provide tests (in
tests/test_habit_insights.py) demonstrating that completion rate is computed
correctly over a date range (including the empty-range 0.0 case); that best
streak finds the longest historical run and is 0 for a habit with no
completions; that rest days are excluded from completions but bridge the best
streak; and that calling an insight endpoint does not mutate the habit.
"""

payload = {
    "brief": BRIEF,
    "project_name": "habit-insights",
    "feature_name": "habit-insights",
    "skip_po": False,             # fresh PO so testing constraints land in each BL spec
    "stop_on_failure": True,      # halt at first escalation -> capture any wall cleanly
    "run_acceptance": True,       # whole-feature API E2E + the one full-suite regression checkpoint
    "run_doctrine_meta": True,    # post-sprint self-hardening -> writes doctrine_efficacy.json (Frontier #1)
    "run_acceptance_followup": True,  # A60 — crew auto-resolves high-confidence acceptance product_bugs in-loop
    "warm_retrieval": True,       # A56 — PO grounding on the (re-indexed) target
    "timeout_per_role": 2400,     # 40 min/role
    "acceptance_timeout": 3600,
}

data = json.dumps(payload).encode()
req = urllib.request.Request(
    URL, data=data, headers={"Content-Type": "application/json"}
)

print(f"[launch] POST {URL}", flush=True)
print(f"[launch] payload keys: {sorted(payload)}", flush=True)
print(f"[launch] start {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}", flush=True)

try:
    with urllib.request.urlopen(req, timeout=6 * 3600) as resp:
        for raw in resp:
            line = raw.decode(errors="replace").rstrip("\n")
            if line:
                print(line, flush=True)
except Exception as e:  # noqa: BLE001
    print(f"[launch] stream ended/error: {e!r}", flush=True)

print(f"[launch] done {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}", flush=True)
