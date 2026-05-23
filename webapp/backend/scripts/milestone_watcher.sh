#!/bin/sh
# Filters orchestrator run.log to milestone-only events into milestones.log.
#
# By default tails webapp/backend/logs/orchestrator/.latest/run.log and
# appends to .latest/milestones.log. Override via $ORCH_LOG_DIR.
set -eu

if [ -n "${ORCH_LOG_DIR:-}" ]; then
  LOG_DIR="$ORCH_LOG_DIR"
else
  SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
  LOG_DIR="$SCRIPT_DIR/../logs/orchestrator/.latest"
fi

RUN_LOG="$LOG_DIR/run.log"
MILESTONES_LOG="$LOG_DIR/milestones.log"

PATTERN='orchestrator\.(po\.done|backlog_parsed|bl\.start|bl\.done|engineer\.done|qa\.done|scorer\.done|reindex_after_(engineer|qa)\.|sprint_complete|aborted)|regression_gate|merge_to_target|_error'

tail -F -n +1 "$RUN_LOG" 2>/dev/null \
  | grep --line-buffered -E "$PATTERN" \
  >> "$MILESTONES_LOG"
