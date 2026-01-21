#!/bin/bash
# list.sh - List recent braindump entries (token-efficient output)
# Usage: list.sh [type] [limit]
# Examples:
#   list.sh           - all types, last 10
#   list.sh todo      - todos only, last 10
#   list.sh til 5     - tils, last 5

TYPE="${1:-all}"
LIMIT="${2:-10}"
BD="${BRAINDUMP_DIR:-$HOME/braindump}"

list_type() {
  local t="$1"
  [ -f "$BD/$t/index.jsonl" ] || return 0
  tail -n "$LIMIT" "$BD/$t/index.jsonl" | \
    jq -r '"\(.created_at | .[0:10]) [\(.type)] \(.title)"' 2>/dev/null || true
}

if [ "$TYPE" = "all" ]; then
  for t in todos til thoughts prompts; do
    list_type "$t"
  done | sort -r | head -n "$LIMIT"
else
  list_type "$TYPE"
fi
