---
model: haiku
allowed-tools: ["Bash", "Write", "Read"]
description: Capture a thought or idea
---

# Braindump Thought

Capture a thought, idea, or reflection.

## Input

$ARGUMENTS

## Instructions

1. **Parse the input** for optional flags:
   - `--mood=curious|excited|frustrated|reflective|...` (optional)
   - `--related=project-or-topic` (optional)

2. **Generate metadata:**
   - `title`: concise title capturing the thought (max 60 chars)
   - `summary`: one-line summary
   - `tags`: 1-3 relevant tags

3. **Create the entry:**

```bash
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
DATE_PATH=$(date +"%Y/%m")
FILE_DATE=$(date +"%Y-%m-%d-%H%M")
SLUG=$(echo "YOUR_TITLE" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//' | sed 's/-$//' | head -c 50 | sed 's/-$//')

BD="$HOME/braindump"
mkdir -p "$BD/thoughts/$DATE_PATH"
```

4. **Write markdown file** at `$BD/thoughts/$DATE_PATH/$SLUG--$FILE_DATE.md`:

```markdown
---
type: thought
title: Your Title
tags: [tag1, tag2]
created_at: 2026-01-21T14:30:00Z
---

# Your Title

The thought or idea...
```

5. **Append to index.jsonl:**

```bash
echo '{"type":"thought","title":"...","summary":"...","tags":[...],"created_at":"...","file_path":"..."}' >> "$BD/thoughts/index.jsonl"
```

After creating, confirm with the title and file path.
