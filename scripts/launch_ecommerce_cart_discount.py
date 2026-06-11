#!/usr/bin/env python3
"""Live-prove ABL-0002 Stage 1 (the Architect's adjudicate/rescue) on the C#/.NET
ecommerce target. Brief: briefs/ecommerce_cart_discount_brief.md.

The deliberate hard core is the per-line discount allocation (B.4+B.5): the
proportional + whole-cent + exact-sum requirement is SOLVABLE via the
largest-remainder method, but a naive "round each line independently" implementation
leaves a residual cent and FAILS the exact-sum invariant. That failure is pure
service-layer arithmetic → it fails the engineer's OWN xUnit/Moq unit test (no DB/DI)
→ reliable per-BL gate exhaustion. The Architect (run_architect=True) then comes to
the rescue: it reads the PO's BL spec, root-causes the failure from the trace + the
failed diff, and hands the engineer the actual fix (the largest-remainder algorithm)
as a directive (model (A)); the engineer applies it in one bounded re-run and the BL
merges. THAT is the full rescue loop we are proving.

Watch for:  architect.start → architect.retry_reframed (root_cause cited) →
            architect.resolved (the engineer's reframed re-run merged) — and the
            Stage-0 escalated_bls/deferred_bls roll-up in sprint_complete.
Honest caveat: the proof is probabilistic — if the engineer discovers
largest-remainder on its own, it succeeds and the Architect never fires (a valid,
if less informative, outcome).

Flags: run_architect=True (the capability under test); cross-target transfer DORMANT
(inject_global_lessons=False); run_acceptance=True; followup OFF.

Run detached:
  cd webapp/backend && nohup ../../scripts/launch_ecommerce_cart_discount.py \
      > logs/harness/ecommerce_cart_discount_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 &
"""
import json
import pathlib
import time
import urllib.request

REPO = "fullstack-ecommerce-app"
URL = f"http://127.0.0.1:8000/api/projects/{REPO}/run-brief"

BRIEF_PATH = pathlib.Path(__file__).resolve().parent.parent / "briefs" / "ecommerce_cart_discount_brief.md"
BRIEF = BRIEF_PATH.read_text()

payload = {
    "brief": BRIEF,
    "project_name": "ecommerce-cart-discount",
    "feature_name": "ecommerce-cart-discount",
    "skip_po": False,
    "stop_on_failure": True,
    "run_acceptance": True,
    "run_doctrine_meta": True,
    "run_acceptance_followup": False,
    "inject_lessons": True,
    "inject_global_lessons": False,   # Stage 3 cross-target transfer is DORMANT
    "run_architect": True,            # ABL-0002 Stage 1 — the capability under test
    "warm_retrieval": True,
    "timeout_per_role": 3000,
    "acceptance_timeout": 3000,
}

data = json.dumps(payload).encode()
req = urllib.request.Request(URL, data=data, headers={"Content-Type": "application/json"})

print(f"[launch] brief: {BRIEF_PATH} ({len(BRIEF)} chars)", flush=True)
print(f"[launch] POST {URL}", flush=True)
print(f"[launch] run_architect={payload['run_architect']} (ABL-0002 Stage 1 under test)", flush=True)
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
