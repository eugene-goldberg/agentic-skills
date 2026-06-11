#!/usr/bin/env python3
"""Launch the "Product Ratings & Reviews" sprint on fullstack-ecommerce-app —
the FIRST API+UI feature on the C#/.NET target (the wishlist was backend-only).
Proposal: PROPOSAL_FEATURE_ecommerce_reviews.md. Brief: briefs/ecommerce_reviews_brief.md.

Notable flag choices (architect, 2026-06-11):
  - inject_global_lessons=False — cross-target (Stage 3 / ABL-0018) transfer is
    DORMANT per operator directive (2026-06-11): the master STAGE3_CROSS_TARGET
    switch is OFF, so the global push/pull/graduation do not fire in any run. This
    flag is a no-op while dormant; left False.
  - inject_lessons=True — per-target lessons (default).
  - run_acceptance=True — carries the app-boot-free regression_checkpoint
    (baseline-vs-merged `dotnet test`) AND the native-boot API journeys (proven on
    this target). The UI is delivered + build-verified; automated UI click-through
    E2E needs frontend-boot (a known follow-up; the backend app_boot is backend-only).
  - run_acceptance_followup=False — don't auto-dispatch on UI findings the acceptance
    can't fully browser-verify yet.

Run detached:
  cd webapp/backend && nohup ../../scripts/launch_ecommerce_reviews.py \
      > logs/harness/ecommerce_reviews_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 &
"""
import json
import pathlib
import time
import urllib.request

REPO = "fullstack-ecommerce-app"
URL = f"http://127.0.0.1:8000/api/projects/{REPO}/run-brief"

BRIEF_PATH = pathlib.Path(__file__).resolve().parent.parent / "briefs" / "ecommerce_reviews_brief.md"
BRIEF = BRIEF_PATH.read_text()

payload = {
    "brief": BRIEF,
    "project_name": "ecommerce-reviews",
    "feature_name": "ecommerce-reviews",
    "skip_po": False,
    "stop_on_failure": True,
    "run_acceptance": True,
    "run_doctrine_meta": True,
    "run_acceptance_followup": False,
    "inject_lessons": True,
    # Cross-target (Stage 3) transfer is DORMANT (operator 2026-06-11) — the master
    # STAGE3_CROSS_TARGET switch is OFF, so this flag is a no-op. Left False.
    "inject_global_lessons": False,
    "warm_retrieval": True,
    "timeout_per_role": 3000,        # 50 min/role
    "acceptance_timeout": 3000,      # 50 min
}

data = json.dumps(payload).encode()
req = urllib.request.Request(URL, data=data, headers={"Content-Type": "application/json"})

print(f"[launch] brief: {BRIEF_PATH} ({len(BRIEF)} chars)", flush=True)
print(f"[launch] POST {URL}", flush=True)
print(f"[launch] payload keys: {sorted(payload)}", flush=True)
print(f"[launch] inject_global_lessons={payload['inject_global_lessons']} (Stage-3 smoke)", flush=True)
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
