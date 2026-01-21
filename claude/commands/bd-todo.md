---
model: haiku
allowed-tools: ["Bash", "Write", "Read"]
description: Create a todo entry
argument-hint: "<task>"
---

# Braindump Todo

Create a todo entry in the braindump system.

## Input

$ARGUMENTS

## Instructions

1. **Analyze the content** and generate metadata (all inferred):
   - `title`: concise title (max 60 chars)
   - `summary`: one-line summary of the task
   - `tags`: 1-3 relevant tags
   - `subtype`: what kind of task (coding, planning, reading, etc.)
   - `priority`: if urgency is implied in the content

2. **Create the entry:**

```bash
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
DATE_PATH=$(date +"%Y/%m")
FILE_DATE=$(date +"%Y-%m-%d-%H%M")
SLUG=$(echo "YOUR_TITLE" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//' | sed 's/-$//' | head -c 50 | sed 's/-$//')

BD="$HOME/braindump"
mkdir -p "$BD/todos/$DATE_PATH"
```

3. **Write markdown file** at `$BD/todos/$DATE_PATH/$SLUG--$FILE_DATE.md`:

```markdown
---
type: todo
title: Your Title
tags: [tag1, tag2]
status: pending
created_at: 2026-01-21T14:30:00Z
---

# Your Title

Task description here...
```

4. **Append to index.jsonl** (include `input` field with original content):

```bash
echo '{"type":"todo","title":"...","summary":"...","tags":[...],"input":"original user input","status":"pending","created_at":"...","file_path":"..."}' >> "$BD/todos/index.jsonl"
```

## Output

CRITICAL: Your ONLY output must be exactly `done: <file_path>`. No confirmations, no summaries, no explanations. Just those two words and the path.
