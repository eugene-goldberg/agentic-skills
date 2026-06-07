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

Out of scope: UI styling polish, bulk import, notifications.

Acceptance: the feature must be verifiable through the API. Provide tests
demonstrating that a rest day bridges a streak across a gap; that a rest day is
not counted as a completion; that done/rest are mutually exclusive; and that a
normal missed day still breaks the streak.
"""

payload = {
    "brief": BRIEF,
    "project_name": "rest-days-streak-freeze",
    "feature_name": "rest-days-streak-freeze",
    "stop_on_failure": True,      # halt at first escalation → capture any wall cleanly
    "run_acceptance": True,       # whole-feature API E2E + the one full-suite regression checkpoint
    "run_doctrine_meta": True,    # post-sprint self-hardening analysis
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
