#!/bin/bash
# search.sh - Search braindump entries using jq
# Usage: search.sh <query> [type]
# Examples:
#   search.sh auth          - search all types
#   search.sh auth todo     - search only todos

set -e

QUERY="${1:?Usage: search.sh <query> [type]}"
TYPE="${2:-}"
BD="${BRAINDUMP_DIR:-$HOME/braindump}"

search_index() {
  local index="$1"
  [ -f "$index" ] || return 0
  jq -c "select(
    (.title | test(\"$QUERY\"; \"i\")) or
    (.summary // \"\" | test(\"$QUERY\"; \"i\")) or
    (.tags // [] | map(test(\"$QUERY\"; \"i\")) | any)
  )" "$index" 2>/dev/null || true
}

if [ -n "$TYPE" ]; then
  search_index "$BD/$TYPE/index.jsonl"
else
  for t in todos til thoughts prompts; do
    search_index "$BD/$t/index.jsonl"
  done
fi
