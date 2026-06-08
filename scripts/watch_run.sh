#!/usr/bin/env bash
# Babysit watcher for an Exp-2 run. Waits up to ~8.5 min, polling every 30s,
# and returns EARLY when a new orchestrator milestone or BL outcome appears, or
# when a terminal event (sprint_complete / escalated / aborted) is seen.
# Usage: watch_run.sh <logfile>
# Exit 42 = terminal event reached; exit 0 = progressed or timed out (keep going).
set -u
LOG="$1"
STATE="/tmp/exp2_watch_state"
sig() {
  # progress signature: ONLY real orchestrator-phase milestones (distinct set).
  # Deliberately excludes raw BL mention counts so mid-role streaming bursts
  # don't trigger a false "progress" break — only true phase transitions do.
  grep -oE '"phase": "orchestrator\.[^"]*"' "$LOG" 2>/dev/null | sort -u | md5 2>/dev/null || true
}
terminal() { grep -qiE '"phase": "orchestrator\.(sprint_complete|escalated|aborted)"|"type": "_terminal"|sprint_complete|"escalated"|"aborted"' "$LOG" 2>/dev/null; }

base="$(sig)"
for i in $(seq 1 17); do
  if terminal; then echo "TERMINAL reached"; break; fi
  cur="$(sig)"
  if [ "$cur" != "$base" ] && [ "$i" -gt 1 ]; then echo "PROGRESS at +$((i*30))s"; break; fi
  sleep 30
done

echo "=== distinct orchestrator phases ==="
grep -oE '"phase": "orchestrator\.[^"]*"' "$LOG" 2>/dev/null | sort | uniq -c | sed 's/"phase": //'
echo "=== BL / outcome / acceptance / terminal markers ==="
grep -oiE '(BL-[0-9]+|merged_full|escalated|qa_fail|no_tests|regression_checkpoint|acceptance[._][a-z]+|doctrine_meta[._][a-z]+|sprint_complete|aborted)' "$LOG" 2>/dev/null | sort | uniq -c | tail -25
echo "=== last meaningful line ==="
grep -oE '"phase": "[^"]*"[^}]*orchestrator_step": "[^"]*"' "$LOG" 2>/dev/null | tail -1
pgrep -f launch_exp2_rest_days >/dev/null && echo "launcher: alive" || echo "launcher: EXITED"

if terminal; then exit 42; fi
exit 0
