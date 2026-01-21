#!/bin/bash
# session-start.sh - Log session start to braindump
# Called by Claude Code SessionStart hook
# Input: JSON via stdin with session_id, transcript_path, source, cwd, etc.

set -e

BD="${BRAINDUMP_DIR:-$HOME/braindump}"
SESSIONS_DIR="$BD/sessions"
mkdir -p "$SESSIONS_DIR"

# Read hook input from stdin
INPUT=$(cat)

# Extract fields from hook input
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // empty')
SOURCE=$(echo "$INPUT" | jq -r '.source // "unknown"')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')

# Use CWD from input or fallback to PWD
DIRECTORY="${CWD:-$PWD}"

# Get current timestamp
STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
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

# Determine context (local vs remote)
if [ "$CLAUDE_CODE_REMOTE" = "true" ]; then
  CONTEXT="remote"
else
  CONTEXT="local"
fi

# Build JSON entry
ENTRY=$(jq -n \
  --arg session_id "$SESSION_ID" \
  --arg started_at "$STARTED_AT" \
  --arg user "$USER_NAME" \
  --arg project "$PROJECT" \
  --arg directory "$DIRECTORY" \
  --arg branch "$BRANCH" \
  --arg context "$CONTEXT" \
  --arg source "$SOURCE" \
  --arg transcript_path "$TRANSCRIPT_PATH" \
  '{
    session_id: $session_id,
    started_at: $started_at,
    user: $user,
    project: $project,
    directory: $directory,
    branch: $branch,
    context: $context,
    source: $source,
    transcript_path: $transcript_path
  }'
)

# Append to daily started file
echo "$ENTRY" >> "$SESSIONS_DIR/started-$TODAY.jsonl"

exit 0
