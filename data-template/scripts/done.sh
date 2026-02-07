#!/bin/bash
# done.sh - Mark a todo as done
# Usage: done.sh <id>             - mark todo by numeric ID
#        done.sh <file_path>      - mark by file path (relative to todos/)
#        done.sh <query>          - search pending todos, mark if single match
#        done.sh --list-done [n]  - list recently completed todos
#
# Examples:
#   done.sh 42
#   done.sh 2026/01/fix-auth-bug--2026-01-21-1430.md
#   done.sh "auth bug"
#   done.sh --list-done 5

set -e

BD="${BRAINDUMP_DIR:-$HOME/braindump}"
INDEX="$BD/todos/index.jsonl"

# List done todos
if [ "${1:-}" = "--list-done" ]; then
  N="${2:-10}"
  jq -c 'select(.status == "done") | {id, title, file_path}' "$INDEX" 2>/dev/null | tail -n "$N"
  exit 0
fi

ARG="${1:?Usage: done.sh <id|file_path|query>}"

# Determine if arg is a numeric ID, file path, or search query
if [[ "$ARG" =~ ^[0-9]+$ ]]; then
  # Numeric ID lookup
  MATCH=$(jq -c "select(.id == $ARG)" "$INDEX" 2>/dev/null)
  if [ -z "$MATCH" ]; then
    echo "No todo found with id: $ARG" >&2
    exit 1
  fi
  FILE_PATH=$(echo "$MATCH" | jq -r '.file_path')
  TITLE=$(echo "$MATCH" | jq -r '.title')
  STATUS=$(echo "$MATCH" | jq -r '.status // "pending"')
  if [ "$STATUS" = "done" ]; then
    echo "Already done: #$ARG $TITLE" >&2
    exit 0
  fi
  echo "Marking as done: #$ARG $TITLE" >&2
elif [[ "$ARG" == *.md ]] || [[ "$ARG" == */* ]]; then
  FILE_PATH="$ARG"
else
  # Search pending todos
  MATCHES=$(jq -c "select(
    (.status != \"done\") and
    ((.title | test(\"$ARG\"; \"i\")) or
     (.summary // \"\" | test(\"$ARG\"; \"i\")) or
     (.tags // [] | map(test(\"$ARG\"; \"i\")) | any))
  )" "$INDEX" 2>/dev/null || true)

  COUNT=$(echo "$MATCHES" | grep -c '^' 2>/dev/null || echo 0)

  if [ "$COUNT" -eq 0 ]; then
    echo "No open todos found for: $ARG" >&2
    exit 1
  elif [ "$COUNT" -eq 1 ]; then
    FILE_PATH=$(echo "$MATCHES" | jq -r '.file_path')
    TITLE=$(echo "$MATCHES" | jq -r '.title')
    ID=$(echo "$MATCHES" | jq -r '.id // empty')
    echo "Marking as done: #${ID:-?} $TITLE" >&2
  else
    echo "Multiple matches:" >&2
    echo "$MATCHES" | jq -r '"  #\(.id // "?") [\(.status // "pending")] \(.title)"' >&2
    echo "" >&2
    echo "Specify the ID, e.g.: done.sh <id>" >&2
    exit 1
  fi
fi

# Resolve full and relative paths (handle both abs and rel in index)
if [[ "$FILE_PATH" == /* ]]; then
  FULL_PATH="$FILE_PATH"
  REL_PATH="${FILE_PATH#$BD/todos/}"
else
  REL_PATH="$FILE_PATH"
  FULL_PATH="$BD/todos/$FILE_PATH"
fi

# Verify file exists
if [ ! -f "$FULL_PATH" ]; then
  echo "File not found: $FULL_PATH" >&2
  exit 1
fi

# Update markdown frontmatter
sed -i '' 's/^status: .*/status: done/' "$FULL_PATH"

# Update JSONL index (match by file_path, handle both abs and rel forms)
TEMP=$(mktemp)
jq -c "if (.file_path == \"$REL_PATH\" or .file_path == \"$FULL_PATH\") then .status = \"done\" else . end" "$INDEX" > "$TEMP"
mv "$TEMP" "$INDEX"

echo "done: $REL_PATH"
