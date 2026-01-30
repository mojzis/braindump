#!/bin/bash
# create-entry.sh - Create a braindump entry with correct structure
# Usage: create-entry.sh <type> <title> <content_file> <jsonl_data>
#
# Arguments:
#   type         - Entry type (todos, til, thoughts, prompts)
#   title        - Entry title (will be slugified)
#   content_file - Path to temp file containing markdown content (body only, no frontmatter)
#   jsonl_data   - JSON object with metadata (will have file_path and created_at added)
#
# Output: Prints the created file path on success
#
# Example:
#   echo "Task description here" > /tmp/content.md
#   create-entry.sh todos "Fix auth bug" /tmp/content.md '{"type":"todo","title":"Fix auth bug","tags":["auth"]}'

set -e

TYPE="${1:?Usage: create-entry.sh <type> <title> <content_file> <jsonl_data>}"
TITLE="${2:?Missing title}"
CONTENT_FILE="${3:?Missing content file}"
JSONL_DATA="${4:?Missing JSONL data}"

BD="${BRAINDUMP_DIR:-$HOME/braindump}"

# Validate type
case "$TYPE" in
  todos|til|thoughts|prompts) ;;
  *) echo "Error: Invalid type '$TYPE'. Must be: todos, til, thoughts, prompts" >&2; exit 1 ;;
esac

# Generate timestamps
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
DATE_PATH=$(date +"%Y/%m")
FILE_DATE=$(date +"%Y-%m-%d-%H%M")

# Slugify title (lowercase, hyphens, max 50 chars)
SLUG=$(echo "$TITLE" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//' | sed 's/-$//' | head -c 50 | sed 's/-$//')

# Ensure slug is not empty
[ -z "$SLUG" ] && SLUG="entry"

# Build paths
DIR_PATH="$BD/$TYPE/$DATE_PATH"
FILE_NAME="${SLUG}--${FILE_DATE}.md"
FILE_PATH="$DATE_PATH/$FILE_NAME"
FULL_PATH="$DIR_PATH/$FILE_NAME"

# Create directory
mkdir -p "$DIR_PATH"

# Extract frontmatter fields from JSONL_DATA
# We need: type, title, tags, project, and any type-specific fields
FRONTMATTER=$(echo "$JSONL_DATA" | jq -r --arg ts "$TIMESTAMP" '
  # Start with basic fields
  "---\ntype: \(.type // "unknown")\ntitle: \(.title // "Untitled")\n" +
  # Tags
  "tags: [\(.tags // [] | map("\"" + . + "\"") | join(", "))]\n" +
  # Project (if present)
  (if .project then "project: \(.project)\n" else "" end) +
  # Type-specific fields
  (if .status then "status: \(.status)\n" else "" end) +
  (if .priority then "priority: \(.priority)\n" else "" end) +
  (if .subtype then "subtype: \(.subtype)\n" else "" end) +
  (if .category then "category: \(.category)\n" else "" end) +
  (if .source then "source: \(.source)\n" else "" end) +
  (if .mood then "mood: \(.mood)\n" else "" end) +
  (if .related_to then "related_to: \(.related_to)\n" else "" end) +
  (if .prompt_type then "prompt_type: \(.prompt_type)\n" else "" end) +
  (if .model_target then "model_target: \(.model_target)\n" else "" end) +
  (if .due_date then "due_date: \(.due_date)\n" else "" end) +
  # Timestamp
  "created_at: \($ts)\n---"
')

# Write markdown file
{
  echo "$FRONTMATTER"
  echo ""
  echo "# $TITLE"
  echo ""
  cat "$CONTENT_FILE"
} > "$FULL_PATH"

# Add file_path and created_at to JSONL data and append to index
echo "$JSONL_DATA" | jq -c --arg fp "$FILE_PATH" --arg ts "$TIMESTAMP" '. + {file_path: $fp, created_at: $ts}' >> "$BD/$TYPE/index.jsonl"

# Output the file path
echo "$FILE_PATH"
