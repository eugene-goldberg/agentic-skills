#!/usr/bin/env python3
"""Deliver the Order Fulfillment Lifecycle feature on the C#/.NET ecommerce target
AND live-prove the parallel-wave-execution program (Phases 1-3) in one shot.

Brief: briefs/ecommerce_order_fulfillment_brief.md.

The feature decomposes into a clean dependency DAG (status model+transitions ->
admin-advance -> owner-cancel -> customer tracker UI -> admin management UI), so it is
the natural live-proof for wave_execution=True:
  - P1 (R21): the PO emits per-BL Dependencies / Exposes / Consumes; validate_po gates
    the DAG well-formedness + contract coverage.
  - P2 (scheduler): orchestrator._dep_waves groups BLs into topological waves; emits
    wave.start / wave.done (concurrency=1 -> byte-identical per-BL semantics).
  - P3 (reindex-at-barrier): per-BL reindexes guarded off; ONE reindex_after_wave.<n>
    per barrier (2/BL -> 1/wave).

Watch for (the run-level acceptance criteria):
  - PO gate ACCEPTS the R21 DAG/contracts (no validate_po deps/contracts failure).
  - orchestrator.wave.start / orchestrator.wave.done events; reindex_after_wave.* (NOT
    per-BL reindex_after_*).
  - acceptance.loop.accepted with BOTH the API journeys (admin-advance, non-admin 403,
    owner-cancel-while-Pending, cross-user cancel 403, illegal transition rejected) and
    the UI journeys (customer tracker, owner-only Cancel, admin console, admin-only
    access) green + screenshots; integrity_ok=true.
  - regression checkpoint green (existing dotnet test suite).

Falsifiable failure predictions (proposal P1-P5): no state machine / authz gap /
cancel-window / UI-only enforcement / regression. See PROPOSAL_FEATURE_order_fulfillment.md.

Fallback: if wave_execution=True misbehaves, the feature still ships by re-running with
wave_execution=False (sequential) -- do NOT let the unproven flag block the feature; then
debug the flag separately.

Flags: wave_execution=True (the program under live-proof); run_acceptance=True;
inject_lessons=True; cross-target transfer DORMANT (inject_global_lessons=False);
run_architect=False (isolate the wave proof -- not mixing two flag-proofs); followup OFF.

Run detached:
  cd webapp/backend && nohup ../../scripts/launch_ecommerce_order_fulfillment.py \
      > logs/harness/ecommerce_order_fulfillment_$(date -u +%Y%m%dT%H%M%SZ).log 2>&1 &
"""
import json
import pathlib
import time
import urllib.request

REPO = "fullstack-ecommerce-app"
URL = f"http://127.0.0.1:8000/api/projects/{REPO}/run-brief"

BRIEF_PATH = pathlib.Path(__file__).resolve().parent.parent / "briefs" / "ecommerce_order_fulfillment_brief.md"
BRIEF = BRIEF_PATH.read_text()

payload = {
    "brief": BRIEF,
    "project_name": "ecommerce-order-fulfillment",
    "feature_name": "ecommerce-order-fulfillment",
    "skip_po": False,
    "stop_on_failure": True,
    "run_acceptance": True,
    "run_doctrine_meta": True,
    "run_acceptance_followup": False,
    "inject_lessons": True,
    "inject_global_lessons": False,   # Stage 3 cross-target transfer is DORMANT
    "run_architect": False,           # isolate the wave-execution live-proof
    "wave_execution": True,           # the program under live-proof (Phases 1-3)
    "warm_retrieval": True,
    "timeout_per_role": 3000,
    "acceptance_timeout": 3000,
}

data = json.dumps(payload).encode()
req = urllib.request.Request(URL, data=data, headers={"Content-Type": "application/json"})

print(f"[launch] brief: {BRIEF_PATH} ({len(BRIEF)} chars)", flush=True)
print(f"[launch] POST {URL}", flush=True)
print(f"[launch] wave_execution={payload['wave_execution']} (parallel-wave Phases 1-3 under live-proof)", flush=True)
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
