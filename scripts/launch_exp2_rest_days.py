"""Launch Experiment 2 — Rest Days (streak freeze) on the real third-party
brownfield target `beaverhabits`. POSTs the brief to the orchestrator's
/run-brief SSE endpoint and tees the event stream to stdout (redirect to a log).

Run detached:
  cd webapp/backend && nohup ../../scripts/launch_exp2_rest_days.py \
      > logs/harness/exp2_rest_days_<ts>.log 2>&1 &

Design of record: EXPERIMENT_beaverhabits_rest_days.md
"""
import json
import sys
import time
import urllib.request

REPO = "beaverhabits"
URL = f"http://127.0.0.1:8000/api/projects/{REPO}/run-brief"

BRIEF = """Add "Rest Days" so planned breaks don't break a habit streak.

Context: Users want to take a planned day off from a habit (a "rest day")
without losing their streak. Today the only thing recordable for a habit on a
given day is "done" or nothing, and a missed day breaks the streak. We want
first-class rest-day support.

Requirements (product behavior — the implementation approach is yours to design
from the actual codebase):
1. A user can mark a specific calendar day for a habit as a rest day, and can
   later un-mark it. This must work for PAST days too (e.g. marking last
   Wednesday as a rest day).
2. A rest day is NOT a completion: it must not appear in the habit's completion
   history, must not count toward any periodic target (e.g. a "3x per week"
   habit), and must not be reported as "done".
3. A day cannot be both completed AND a rest day at the same time — the two are
   mutually exclusive; setting one clears the other.
4. Streak behavior: a rest day must neither extend nor break a streak — it
   BRIDGES it. If a user completes a habit Monday and Tuesday, takes a rest day
   Wednesday, and completes it again Thursday, their current streak is 3 (the
   three completed days) and is unbroken. A genuinely missed day (no completion,
   no rest day) still breaks the streak as it does today.
5. The app must be able to report a habit's current streak length (correctly
   accounting for rest days) so the user can see it.
6. Existing behavior must be preserved exactly for habits that use no rest days.
   All existing tests must continue to pass.

Out of scope: UI styling polish, bulk import, notifications. Do NOT touch,
extend, or "improve" the application's storage backends, persistence layer, or
any infrastructure plumbing (file/disk storage, database session wiring, the
FilePersistentDict/user_file machinery). This feature is ordinary web-app
business logic over the EXISTING habit/record model and the EXISTING HTTP API —
nothing below that line.

TESTING CONSTRAINTS (hard requirements — the regression gate depends on them):
- Put ALL of your new tests in a brand-new, dedicated file: tests/test_rest_days.py.
- Do NOT modify, append to, or import wholesale any of the application's
  pre-existing test files (e.g. tests/test_storage.py, tests/test_apis.py,
  tests/test_gui.py). Those exercise the app's storage backends and other
  infrastructure that is OUT OF SCOPE here; editing them drags backend-storage
  smoke tests into this feature's gate, which is wrong.
- Your tests must target the FEATURE itself: the rest-day HTTP API endpoints and
  the rest-aware streak/completion business logic — the substance a user cares
  about. Test it the way you would test any typical web application: drive the
  HTTP API and assert behavior. Do not write tests about disk files, JSON
  serialization formats, or storage-backend internals.

Acceptance: the feature must be verifiable through the API. Provide tests (in
tests/test_rest_days.py) demonstrating that a rest day bridges a streak across a
gap; that a rest day is not counted as a completion; that done/rest are mutually
exclusive; and that a normal missed day still breaks the streak.
"""

payload = {
    "brief": BRIEF,
    "project_name": "rest-days-streak-freeze",
    "feature_name": "rest-days-streak-freeze",
    "skip_po": False,             # fresh PO so the new testing constraints land in each BL spec
    "stop_on_failure": True,      # halt at first escalation → capture any wall cleanly
    "run_acceptance": True,       # whole-feature API E2E + the one full-suite regression checkpoint
    "run_doctrine_meta": True,    # post-sprint self-hardening analysis
    "run_acceptance_followup": True,  # A60 — crew auto-resolves high-confidence acceptance product_bugs in-loop
    "warm_retrieval": True,       # A56 — first real PO-grounding test on a fresh target
    "timeout_per_role": 2400,     # 40 min/role
    "acceptance_timeout": 3600,
}

data = json.dumps(payload).encode()
req = urllib.request.Request(URL, data=data,
                             headers={"Content-Type": "application/json"})

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
