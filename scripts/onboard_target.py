#!/usr/bin/env python3
"""Onboard a brand-new brownfield target — invoke the crew's Onboarder
(the Janitor/Ops-Steward in ONBOARDING MODE) to fulfil the ENVIRONMENT
prerequisites a `git clone` doesn't bring, so the crew can begin brownfield
feature work.

What it does (the onboarder, autonomously): detect the stack; install/restore
dependencies + runtime; provision services the app needs (e.g. a database
container); materialise gitignored config from a template; generate
required-but-absent artifacts (migrations/schema); derive the gate config
(`test_cmd`/`test_env`/`test_file_globs`); add harness `.gitignore` hygiene;
write `.agentic-skills.json`; fork the `integration` branch; verify the target
builds, boots, and that `test_cmd` executes. It PROVISIONS THE ENVIRONMENT — it
never edits the target's committed source to fix pre-existing defects (those are
flagged in the verdict, not rectified).

PREREQUISITES
  - The harness server is running (uvicorn on 127.0.0.1:8000):
        cd webapp/backend && .venv/bin/python -m uvicorn app.main:app \
            --host 127.0.0.1 --port 8000
  - The target repo is symlinked under webapp/backend/repos/<repo> (the same
    place run-brief discovers targets). The repo must NOT already be onboarded
    (no .agentic-skills.json) — onboarding is the step that creates it.

USAGE
  # minimal — onboard a freshly-symlinked repo:
  python scripts/onboard_target.py <repo>

  # with the upcoming feature brief as context (helps the onboarder anticipate
  # which services/deps the work will need — it still only prepares the env):
  python scripts/onboard_target.py <repo> --brief-file path/to/brief.txt

  # longer per-agent budget (default 3600s) for heavy installs/DB boots:
  python scripts/onboard_target.py <repo> --timeout 7200

Detached (recommended for long onboardings):
  nohup python scripts/onboard_target.py <repo> \
      > webapp/backend/logs/harness/onboard_<repo>.log 2>&1 &

RESULT
  Streams onboarding events to stdout. The terminal event is either
  `onboarding.done` (status=onboarded — the orchestrator's OWN postcondition
  verification passed, not just the agent's self-report) or
  `onboarding.escalated` (a prerequisite couldn't be satisfied — see the
  `missing` list and the report under
  <repo>/_brownfield/_onboarding/ONBOARDING_REPORT-<run_id>.md).
"""
import argparse
import json
import sys
import urllib.request

HOST = "http://127.0.0.1:8000"


def main() -> int:
    ap = argparse.ArgumentParser(description="Onboard a brownfield target repo.")
    ap.add_argument("repo", help="repo name as symlinked under webapp/backend/repos/")
    ap.add_argument("--brief-file", help="optional: file with the upcoming feature brief (context only)")
    ap.add_argument("--timeout", type=int, default=3600, help="per-agent wall-clock budget, seconds (default 3600)")
    args = ap.parse_args()

    brief = None
    if args.brief_file:
        with open(args.brief_file, encoding="utf-8") as f:
            brief = f.read()

    payload = {"timeout": args.timeout}
    if brief:
        payload["brief"] = brief

    url = f"{HOST}/api/projects/{args.repo}/onboard"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")

    print(f"[onboard] → {url}  (timeout={args.timeout}s, brief={'yes' if brief else 'no'})", flush=True)
    final = None
    try:
        with urllib.request.urlopen(req, timeout=args.timeout + 600) as resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").rstrip("\n")
                if not line.startswith("data:"):
                    continue
                try:
                    evt = json.loads(line[len("data:"):].strip())
                except json.JSONDecodeError:
                    continue
                etype = evt.get("type") or evt.get("phase") or "?"
                # Surface the milestone events prominently; echo the rest tersely.
                if etype in ("onboarding.start", "onboarding.verify",
                             "onboarding.done", "onboarding.escalated",
                             "onboarding.error", "onboarding.verdict.error",
                             "onboard.outcome", "onboard.accepted"):
                    print(f"[{etype}] " + json.dumps({k: v for k, v in evt.items()
                          if k not in ('type', 'phase')})[:600], flush=True)
                    if etype in ("onboarding.done", "onboarding.escalated", "onboard.outcome"):
                        final = evt
                elif evt.get("type") == "_error":
                    print(f"[error] {evt.get('error')}", flush=True)
    except urllib.error.URLError as exc:
        print(f"[onboard] connection failed: {exc}\n"
              f"          is the harness server running on {HOST}?", file=sys.stderr)
        return 2

    if final and (final.get("status") == "onboarded"):
        print("\n[onboard] ✅ ONBOARDED — repo is ready for brownfield work "
              "(.agentic-skills.json written, integration branch forked, "
              "test_cmd executes). You can now /run-brief against it.", flush=True)
        return 0
    print("\n[onboard] ⚠️  NOT fully onboarded — see the escalation / missing list "
          "above and the ONBOARDING_REPORT under the repo's _brownfield/_onboarding/.",
          flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
