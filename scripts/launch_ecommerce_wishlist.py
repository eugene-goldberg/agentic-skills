#!/usr/bin/env python3
"""Launch the "Wishlist / Favorites" sprint on fullstack-ecommerce-app —
the FIRST crew sprint ever run against a non-Python (C#/.NET 8 + EF Core +
Postgres) target. See EXPERIMENT_ecommerce_wishlist.md for the full rationale.

This is a deliberate LANGUAGE-LOOP SHAKEDOWN, not a hard-correctness discovery
test. The question under test is U1: does the language-agnostic crew loop drive a
C# sprint end-to-end? The feature is a low-ambiguity near-mirror of the existing
Cart aggregate so the harness/loop is the variable, not the feature.

Acceptance config (TRACED, EXPERIMENT §4):
  - run_acceptance=True is REQUIRED: the app-boot-free `regression_checkpoint`
    (which re-runs `dotnet test` baseline-vs-merged) is nested inside it and IS the
    U1 proof.
  - The acceptance AGENT's app-boot is compose-centric; this target has no compose
    stack, so the agent is EXPECTED to flail/error. Acceptance is advisory and
    NEVER aborts the sprint — that flail is the expected TIER-3 gap signal (feeds
    the native-boot generalization follow-up), not a crew defect.
  - run_acceptance_followup=False: do NOT auto-dispatch fixes on a target whose
    acceptance can't boot yet.

Run detached:
  cd webapp/backend && nohup ../../scripts/launch_ecommerce_wishlist.py \
      > logs/harness/ecommerce_wishlist_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 &
"""
import json
import pathlib
import time
import urllib.request

REPO = "fullstack-ecommerce-app"
URL = f"http://127.0.0.1:8000/api/projects/{REPO}/run-brief"

BRIEF_PATH = pathlib.Path(__file__).resolve().parent.parent / "briefs" / "ecommerce_wishlist_brief.md"
BRIEF = BRIEF_PATH.read_text()

payload = {
    "brief": BRIEF,
    "project_name": "ecommerce-wishlist",
    "feature_name": "ecommerce-wishlist",
    "skip_po": False,
    "stop_on_failure": True,          # capture any wall cleanly
    "run_acceptance": True,           # REQUIRED — carries the app-boot-free regression_checkpoint (U1 proof)
    "run_doctrine_meta": True,
    "run_acceptance_followup": False, # don't auto-dispatch on a target whose acceptance can't boot yet
    "warm_retrieval": True,
    "timeout_per_role": 3000,         # 50 min/role — first C# run, give the engineer room
    "acceptance_timeout": 3000,       # 50 min — bounded; the agent will flail on no-compose (advisory)
}

data = json.dumps(payload).encode()
req = urllib.request.Request(
    URL, data=data, headers={"Content-Type": "application/json"}
)

print(f"[launch] brief: {BRIEF_PATH} ({len(BRIEF)} chars)", flush=True)
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
