---
allowed-tools: ["Bash", "Read"]
description: List recent braindump entries
argument-hint: "[type] [limit]"
---

# Braindump List

List recent braindump entries.

## Input

$ARGUMENTS

## Instructions

1. **Parse arguments:**
   - No args: list all types, last 10
   - Type name: `todo`, `til`, `thought`, `prompt` - list that type only
   - Number: limit results (e.g., `todo 5`)

2. **Run the list script:**

```bash
BD="$HOME/braindump"
TYPE="${1:-all}"
LIMIT="${2:-10}"

# Using the list script
"$BD/scripts/list.sh" "$TYPE" "$LIMIT"
```

Or directly:
```bash
BD="$HOME/braindump"

list_type() {
  local t="$1"
  [ -f "$BD/$t/index.jsonl" ] && tail -n 10 "$BD/$t/index.jsonl" | \
    jq -r '"\(.created_at | .[0:10]) [\(.type)] \(.title)"'
}

for t in todos til thoughts prompts; do
  list_type "$t"
done | sort -r | head -n 10
```

3. **Display results** in a clean, scannable format:
   - Date [type] Title
   - One entry per line
   - Sorted by most recent first
