#!/bin/bash
# session-end.sh - Log session end to braindump
# Called by Claude Code SessionEnd hook
# Input: JSON via stdin with session_id, reason, cwd, etc.

set -e

BD="${BRAINDUMP_DIR:-$HOME/braindump}"
SESSIONS_DIR="$BD/sessions"
mkdir -p "$SESSIONS_DIR"

# Read hook input from stdin
INPUT=$(cat)

# Extract fields from hook input
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
REASON=$(echo "$INPUT" | jq -r '.reason // "unknown"')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')

# Use CWD from input or fallback to PWD
DIRECTORY="${CWD:-$PWD}"

# Get current timestamp
FINISHED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
TODAY=$(date +"%Y-%m-%d")

# Get user
USER_NAME="${USER:-$(whoami)}"

# Determine project name and branch
if git -C "$DIRECTORY" rev-parse --git-dir > /dev/null 2>&1; then
  PROJECT=$(basename "$(git -C "$DIRECTORY" rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null)
  BRANCH=$(git -C "$DIRECTORY" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
else
  PROJECT=$(basename "$DIRECTORY")
  BRANCH=""
fi

# Determine context
if [ "$CLAUDE_CODE_REMOTE" = "true" ]; then
  CONTEXT="remote"
else
  CONTEXT="local"
fi

# Find the original start time by searching recent started files
STARTED_AT=""
DURATION_SECONDS=""

# Search last 7 days of started files for this session_id
for i in $(seq 0 6); do
  # Try GNU date first, then BSD date
  CHECK_DATE=$(date -d "-$i days" +"%Y-%m-%d" 2>/dev/null || date -v-${i}d +"%Y-%m-%d" 2>/dev/null)
  STARTED_FILE="$SESSIONS_DIR/started-$CHECK_DATE.jsonl"
  if [ -f "$STARTED_FILE" ]; then
    MATCH=$(grep "\"session_id\":\"$SESSION_ID\"" "$STARTED_FILE" 2>/dev/null | tail -1 || true)
    if [ -n "$MATCH" ]; then
      STARTED_AT=$(echo "$MATCH" | jq -r '.started_at // empty')
      break
    fi
  fi
done

# Calculate duration if we found start time
if [ -n "$STARTED_AT" ]; then
  # Convert to epoch seconds for calculation (try GNU date first, then BSD)
  START_EPOCH=$(date -d "$STARTED_AT" +%s 2>/dev/null || date -jf "%Y-%m-%dT%H:%M:%SZ" "$STARTED_AT" +%s 2>/dev/null || echo "")
  END_EPOCH=$(date -d "$FINISHED_AT" +%s 2>/dev/null || date -jf "%Y-%m-%dT%H:%M:%SZ" "$FINISHED_AT" +%s 2>/dev/null || echo "")
  if [ -n "$START_EPOCH" ] && [ -n "$END_EPOCH" ]; then
    DURATION_SECONDS=$((END_EPOCH - START_EPOCH))
  fi
fi

# Build JSON entry
ENTRY=$(jq -n \
  --arg session_id "$SESSION_ID" \
  --arg finished_at "$FINISHED_AT" \
  --arg user "$USER_NAME" \
  --arg project "$PROJECT" \
  --arg directory "$DIRECTORY" \
  --arg branch "$BRANCH" \
  --arg context "$CONTEXT" \
  --arg reason "$REASON" \
  --arg started_at "$STARTED_AT" \
  --argjson duration_seconds "${DURATION_SECONDS:-null}" \
  '{
    session_id: $session_id,
    finished_at: $finished_at,
    user: $user,
    project: $project,
    directory: $directory,
    branch: $branch,
    context: $context,
    reason: $reason,
    duration_seconds: $duration_seconds,
    started_at: $started_at
  }'
)

# Append to daily finished file
echo "$ENTRY" >> "$SESSIONS_DIR/finished-$TODAY.jsonl"

exit 0
