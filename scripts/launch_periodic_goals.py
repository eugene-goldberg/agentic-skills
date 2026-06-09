#!/usr/bin/env python3
"""Launch the "Periodic Habit Goals" sprint on beaverhabits — a deliberately
HIGHER-COMPLEXITY brownfield feature to stress the crew beyond the small,
single-concern features in this series (notes, rest-days, insights, history).

Why it's harder (the falsifiable difficulties — NOT telegraphed in the brief):
  - persisted per-habit config added to the existing model WITHOUT touching the
    storage backend / FilePersistentDict machinery (the storage-test landmine);
  - current-period window math (Mon–Sun week, calendar month) with the classic
    boundary off-by-one risk;
  - cross-feature interaction: goal progress must honor the EXISTING rest-day
    semantics (a rest day is not a completion, doesn't count toward/against a
    goal) — the crew must connect to core/streak.py + the rest-days work;
  - a goal-STREAK across consecutive met periods (subtle: which periods count,
    how the in-progress period is handled) — built on top of current_streak;
  - multi-BL with genuine dependencies (progress depends on the goal model;
    goal-met depends on progress; goal-streak depends on goal-met; UI depends on
    all of it);
  - a UI surface (first UI-touching feature in the series) → exercises the
    acceptance Playwright path.

Run detached:
  cd webapp/backend && nohup ../../scripts/launch_periodic_goals.py \
      > logs/harness/periodic_goals_<ts>.log 2>&1 &
"""
import json
import time
import urllib.request

REPO = "beaverhabits"
URL = f"http://127.0.0.1:8000/api/projects/{REPO}/run-brief"

BRIEF = """Add "Periodic Habit Goals" so a user can commit to completing a habit a
target number of times per week or per month, and see how they are tracking
against that goal.

Context: Today a habit is either completed on a day or not, the app tracks a
current streak (which already honors rest days), and there are read-only stats.
Many users don't do a habit every single day — they aim for a frequency, e.g.
"exercise 4 times a week" or "deep-clean 2 times a month". We want first-class,
configurable periodic goals with live progress, without changing how habits or
records are stored at the persistence-backend level.

Requirements (product behavior — design the implementation from the actual
codebase; the points below are WHAT must be true and testable, not HOW):

A. Setting a goal
   1. A user can give a habit an optional periodic goal via the API: a positive
      integer target count N and a period of either "week" or "month". A habit
      may also have NO goal (the default for every existing habit).
   2. The goal is a persisted setting on the habit — it survives a reload and is
      returned when the habit is read. Setting a new goal replaces the old one;
      a user can also clear a habit's goal entirely.
   3. Invalid goals are rejected with a client error and no state change: N < 1,
      a non-integer N, or a period other than "week"/"month".

B. Current-period progress
   4. For a habit with a goal, the API reports the CURRENT period's progress:
      the number of completions that fall inside the current period window and
      the target N (e.g. 3 of 4). "Current period" is relative to today.
   5. Period windows are: a WEEK runs Monday 00:00 through Sunday (Monday is the
      first day); a MONTH is the calendar month. Only completions whose date
      falls inside the current window count toward progress — a completion in a
      previous week/month must not leak into the current period's count.
   6. Rest days must be honored exactly as the rest of the app honors them: a
      rest day is NOT a completion, so it does not count toward the goal and
      does not count against it. It is simply neither.
   7. A habit with no goal reports no progress (and no error).

C. Goal met + goal streak
   8. The current period's goal is "met" when the number of completions inside
      the current window is greater than or equal to N.
   9. The API reports a goal STREAK: the number of consecutive most-recent
      FULLY-ELAPSED periods (immediately preceding the current one) in which the
      goal was met, extended by the current period only once it is itself met. A
      fully-elapsed period in which the goal was NOT met breaks the streak. A
      habit with no goal has no goal streak.
   10. The goal streak must be internally consistent with progress: if the
       current period is met and every prior period back to some point was met,
       the streak reflects exactly that count; a single missed past period
       stops it.

D. Preservation (non-negotiable)
   11. Habits with no goal must behave EXACTLY as they do today — every existing
       endpoint, response shape, streak, and stat is unchanged for them. Goal
       fields are absent/null for a goal-less habit.
   12. The existing current-streak / completion / rest-day behavior must not
       change. All existing tests must continue to pass.

E. UI
   13. Wherever the app shows a habit to the user, surface that habit's
       current-period goal progress when it has a goal (for example a compact
       "3/4 this week" style indicator). A habit with no goal shows no goal
       indicator and looks exactly as it does today. Keep it simple and
       consistent with the existing habit display — no new pages required.

Out of scope: changing the rest-day or completion rules themselves; bulk goal
editing; reminders/notifications; historical goal analytics beyond the streak in
(C); charts. You MAY add the minimal persisted field(s) the goal needs to the
EXISTING habit record via the app's EXISTING serialization mechanism (the same
way an existing per-habit setting like the "star" flag is stored), but do NOT
modify, refactor, rewrite, or "improve" the storage backends, the
FilePersistentDict / user_file machinery, database/session wiring, or any other
persistence/infrastructure plumbing. This is ordinary web-app business logic +
one small persisted setting + a UI indicator over the EXISTING model and HTTP
API — nothing below that line.

TESTING CONSTRAINTS (hard requirements — the regression gate depends on them):
- Put ALL of your new backend tests in brand-new, dedicated files under tests/
  named for this feature (e.g. tests/test_habit_goals.py). You may add more than
  one new test file, but every new test file must be NEW and feature-specific.
- Do NOT modify, append to, or import wholesale any of the application's
  pre-existing test files (e.g. tests/test_storage.py, tests/test_apis.py,
  tests/test_gui.py). Editing them drags backend-storage smoke tests into this
  feature's gate, which is wrong.
- Backend tests must target the FEATURE: the goal HTTP API (set/clear/get +
  progress/met/streak) and the period/rest-aware/goal-streak business logic.
  Drive the HTTP API and assert behavior the way you'd test any web app. Do NOT
  write tests about disk files, JSON serialization formats, or storage-backend
  internals.

Acceptance: the feature must be verifiable end-to-end. Through the API,
demonstrate: a weekly and a monthly goal each report correct current-period
progress; completions in a prior period do not leak into the current count; a
rest day inside the window is excluded from progress; an invalid goal (N<1 or a
bad period) is rejected; the goal is "met" at exactly N; the goal streak counts
consecutive met periods and a single missed prior period breaks it; and a
goal-less habit is byte-for-byte unchanged. If the habit display surfaces the
goal indicator in the UI, verify it shows the correct current-period progress
for a habit with a goal and is absent for one without.
"""

payload = {
    "brief": BRIEF,
    "project_name": "periodic-habit-goals",
    "feature_name": "periodic-habit-goals",
    "skip_po": False,
    "stop_on_failure": True,        # capture any wall cleanly
    "run_acceptance": True,         # whole-feature E2E (API + Playwright iff UI journeys) + regression checkpoint
    "run_doctrine_meta": True,
    "run_acceptance_followup": True,  # A60 — crew auto-resolves high-confidence acceptance product_bugs in-loop
    "warm_retrieval": True,
    "timeout_per_role": 3000,       # 50 min/role — harder BLs get more room
    "acceptance_timeout": 4500,     # 75 min — UI E2E is heavier
}

data = json.dumps(payload).encode()
req = urllib.request.Request(
    URL, data=data, headers={"Content-Type": "application/json"}
)

print(f"[launch] POST {URL}", flush=True)
print(f"[launch] payload keys: {sorted(payload)}", flush=True)
print(f"[launch] start {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}", flush=True)

try:
    with urllib.request.urlopen(req, timeout=8 * 3600) as resp:
        for raw in resp:
            line = raw.decode(errors="replace").rstrip("\n")
            if line:
                print(line, flush=True)
except Exception as e:  # noqa: BLE001
    print(f"[launch] stream ended/error: {e!r}", flush=True)

print(f"[launch] done {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}", flush=True)
