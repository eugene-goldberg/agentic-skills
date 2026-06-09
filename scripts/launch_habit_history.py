#!/usr/bin/env python3
"""Launch the "Habit History" sprint on beaverhabits — the SECOND post-A13
sealed sprint, whose purpose is to confirm A64: that the acceptance flow now
seals the full-suite ``regression_checkpoint`` into a co-located
phase_events.jsonl and the ABL-0017 efficacy aggregator surfaces it as a
``by_rule`` row in ``traces_archive/<run>/doctrine_efficacy.json``.

The feature is incidental — a small, read-only, lowest-risk additive analytic
chosen to drive the full engineer -> QA -> merge -> regression_checkpoint ->
acceptance -> doctrine_meta pipeline cheaply.

Run detached:
  cd webapp/backend && nohup ../../scripts/launch_habit_history.py \
      > logs/harness/habit_history_<ts>.log 2>&1 &
"""
import json
import time
import urllib.request

REPO = "beaverhabits"
URL = f"http://127.0.0.1:8000/api/projects/{REPO}/run-brief"

BRIEF = """Add "Habit History" — a read-only per-day status timeline for a habit.

Context: A user can complete habits and (since the rest-days feature) mark rest
days, and the app reports streaks and completion stats. But there is no single
read-only view that lays out, day by day, what happened to a habit across a date
range. We want a first-class history timeline endpoint that changes nothing
about how habits or records are stored.

Requirements (product behavior — the implementation approach is yours to design
from the actual codebase):
1. A user can request a habit's per-day status over an inclusive calendar date
   range via the API. The response lists every day in the range with a status
   of exactly one of: "done" (a completion), "rest" (a rest day), or "none"
   (neither). The days are returned in chronological order.
2. Rest days must be honored consistently with the rest of the app: a day a user
   marked as a rest day reports "rest", never "done" and never "none".
3. An empty or inverted range (end date before start date) returns an empty
   timeline (no days) — never an error and never a divide-by-zero.
4. This endpoint is STRICTLY READ-ONLY. It must not create, mutate, or delete
   any habit, record, or persisted field. Requesting a habit's history must
   leave that habit byte-for-byte unchanged.
5. Existing behavior must be preserved exactly. All existing tests must continue
   to pass.

Out of scope: UI styling polish, charts/graphs, CSV/JSON export, pagination,
caching. Do NOT add, remove, or change any PERSISTED field on a habit or record,
and do NOT touch, extend, or "improve" the application's storage backends,
persistence layer, or any infrastructure plumbing (file/disk storage, database
session wiring, the FilePersistentDict/user_file machinery). This feature is
ordinary read-only web-app business logic computed over the EXISTING habit/record
model and exposed over the EXISTING HTTP API — nothing below that line.

TESTING CONSTRAINTS (hard requirements — the regression gate depends on them):
- Put ALL of your new tests in a brand-new, dedicated file: tests/test_habit_history.py.
- Do NOT modify, append to, or import wholesale any of the application's
  pre-existing test files (e.g. tests/test_storage.py, tests/test_apis.py,
  tests/test_gui.py). Those exercise the app's storage backends and other
  infrastructure that is OUT OF SCOPE here; editing them drags backend-storage
  smoke tests into this feature's gate, which is wrong.
- Your tests must target the FEATURE itself: the history HTTP API endpoint and
  the per-day status business logic — the substance a user cares about. Test it
  the way you would test any typical web application: drive the HTTP API and
  assert behavior. Do not write tests about disk files, JSON serialization
  formats, or storage-backend internals.

Acceptance: the feature must be verifiable through the API. Provide tests (in
tests/test_habit_history.py) demonstrating that the timeline labels each day
done/rest/none correctly across a range that mixes all three; that an inverted
range returns an empty timeline; and that calling the history endpoint does not
mutate the habit.
"""

payload = {
    "brief": BRIEF,
    "project_name": "habit-history",
    "feature_name": "habit-history",
    "skip_po": False,
    "stop_on_failure": True,
    "run_acceptance": True,        # drives the regression_checkpoint (A64 seal target)
    "run_doctrine_meta": True,     # writes doctrine_efficacy.json — confirm the row
    "run_acceptance_followup": True,
    "warm_retrieval": True,
    "timeout_per_role": 2400,
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
