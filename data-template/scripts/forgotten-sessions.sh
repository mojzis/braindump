#!/bin/bash
# forgotten-sessions.sh - Find sessions that started but never finished
# Usage: forgotten-sessions.sh [days]
# Example: forgotten-sessions.sh 7   # Check last 7 days (default)

set -e

DAYS="${1:-7}"
BD="${BRAINDUMP_DIR:-$HOME/braindump}"
SESSIONS_DIR="$BD/sessions"

if [ ! -d "$SESSIONS_DIR" ]; then
  echo "No sessions directory found at $SESSIONS_DIR"
  exit 0
fi

# Collect all started session IDs from the date range
STARTED_IDS=$(mktemp)
FINISHED_IDS=$(mktemp)
trap "rm -f $STARTED_IDS $FINISHED_IDS" EXIT

# Gather started sessions
for i in $(seq 0 "$DAYS"); do
  # Try GNU date first, then BSD date
  CHECK_DATE=$(date -d "-$i days" +"%Y-%m-%d" 2>/dev/null || date -v-${i}d +"%Y-%m-%d" 2>/dev/null)
  STARTED_FILE="$SESSIONS_DIR/started-$CHECK_DATE.jsonl"
  if [ -f "$STARTED_FILE" ]; then
    jq -r '.session_id' "$STARTED_FILE" >> "$STARTED_IDS" 2>/dev/null || true
  fi
done

# Gather finished sessions (check extra days in case session ended later)
for i in $(seq 0 $((DAYS + 1))); do
  CHECK_DATE=$(date -d "-$i days" +"%Y-%m-%d" 2>/dev/null || date -v-${i}d +"%Y-%m-%d" 2>/dev/null)
  FINISHED_FILE="$SESSIONS_DIR/finished-$CHECK_DATE.jsonl"
  if [ -f "$FINISHED_FILE" ]; then
    jq -r '.session_id' "$FINISHED_FILE" >> "$FINISHED_IDS" 2>/dev/null || true
  fi
done

# Sort and find unfinished (in started but not in finished)
UNFINISHED=$(comm -23 <(sort -u "$STARTED_IDS") <(sort -u "$FINISHED_IDS"))

if [ -z "$UNFINISHED" ]; then
  echo "No forgotten sessions found in the last $DAYS days."
  exit 0
fi

echo "Forgotten sessions (started but not finished) in the last $DAYS days:"
echo ""

# For each unfinished session, show details
for SESSION_ID in $UNFINISHED; do
  # Find the session details
  for i in $(seq 0 "$DAYS"); do
    CHECK_DATE=$(date -d "-$i days" +"%Y-%m-%d" 2>/dev/null || date -v-${i}d +"%Y-%m-%d" 2>/dev/null)
    STARTED_FILE="$SESSIONS_DIR/started-$CHECK_DATE.jsonl"
    if [ -f "$STARTED_FILE" ]; then
      MATCH=$(grep "\"session_id\":\"$SESSION_ID\"" "$STARTED_FILE" 2>/dev/null | tail -1 || true)
      if [ -n "$MATCH" ]; then
        echo "$MATCH" | jq -r '"[\(.started_at | .[0:16] | gsub("T"; " "))] \(.project) (\(.branch // "no-branch")) @ \(.directory)"'
        break
      fi
    fi
  done
done
