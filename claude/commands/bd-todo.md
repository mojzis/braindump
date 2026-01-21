---
model: haiku
allowed-tools: ["Bash", "Write", "Read"]
description: Create a todo entry
---

# Braindump Todo

Create a todo entry in the braindump system.

## Input

$ARGUMENTS

## Instructions

1. **Parse the input** for optional flags:
   - `--priority=high|medium|low` (default: medium)
   - `--subtype=code|think|read|write|call|general` (default: infer from content)
   - `--due=YYYY-MM-DD` (optional)

2. **Generate metadata:**
   - `title`: concise title (max 60 chars)
   - `summary`: one-line summary of the task
   - `tags`: 1-3 relevant tags
   - `subtype`: infer if not specified (code for programming tasks, think for planning, etc.)

3. **Create the entry:**

```bash
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
DATE_PATH=$(date +"%Y/%m")
FILE_DATE=$(date +"%Y-%m-%d-%H%M")
SLUG=$(echo "YOUR_TITLE" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//' | sed 's/-$//' | head -c 50 | sed 's/-$//')

BD="$HOME/braindump"
mkdir -p "$BD/todos/$DATE_PATH"
```

4. **Write markdown file** at `$BD/todos/$DATE_PATH/$SLUG--$FILE_DATE.md`:

```markdown
---
type: todo
subtype: code
title: Your Title
tags: [tag1, tag2]
status: pending
priority: medium
created_at: 2026-01-21T14:30:00Z
---

# Your Title

Task description here...
```

5. **Append to index.jsonl:**

```bash
echo '{"type":"todo","subtype":"code","title":"...","summary":"...","tags":[...],"status":"pending","priority":"medium","created_at":"...","file_path":"..."}' >> "$BD/todos/index.jsonl"
```

After creating, confirm with the title and file path.
