#!/usr/bin/env bash
# Wire ~/.claude/projects/<encoded>/memory → <repo>/.claude/memory so
# Claude Code's auto-memory system finds the version-controlled files
# at the canonical path it expects.
#
# Idempotent: safe to re-run. Refuses to clobber a real directory.
#
# Usage:
#   scripts/setup_memory_symlink.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO_MEMORY="$PROJECT_ROOT/.claude/memory"

if [[ ! -d "$REPO_MEMORY" ]]; then
  echo "error: $REPO_MEMORY does not exist — nothing to link" >&2
  exit 1
fi

# Claude Code encodes the absolute project path by replacing / with -.
# e.g. /Users/foo/dev/agentic-skills  →  -Users-foo-dev-agentic-skills
ENCODED="${PROJECT_ROOT//\//-}"
TARGET_DIR="$HOME/.claude/projects/$ENCODED"
SYMLINK="$TARGET_DIR/memory"

mkdir -p "$TARGET_DIR"

if [[ -L "$SYMLINK" ]]; then
  current="$(readlink "$SYMLINK")"
  if [[ "$current" == "$REPO_MEMORY" ]]; then
    echo "ok: $SYMLINK already points to $REPO_MEMORY"
    exit 0
  fi
  echo "info: replacing existing symlink ($current → $REPO_MEMORY)"
  rm "$SYMLINK"
elif [[ -e "$SYMLINK" ]]; then
  echo "error: $SYMLINK exists and is NOT a symlink." >&2
  echo "       Move or merge it manually, then re-run this script." >&2
  echo "       Suggested: cp -r '$SYMLINK'/* '$REPO_MEMORY'/ && rm -rf '$SYMLINK'" >&2
  exit 1
fi

ln -s "$REPO_MEMORY" "$SYMLINK"
echo "ok: linked $SYMLINK"
echo "         → $REPO_MEMORY"
