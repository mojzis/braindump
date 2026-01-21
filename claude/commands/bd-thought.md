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

1. **Analyze the content** and generate metadata (all inferred):
   - `title`: concise title capturing the thought (max 60 chars)
   - `summary`: one-line summary
   - `tags`: 1-3 relevant tags
   - `mood`: if evident from the content
   - `related_to`: if about something specific

2. **Create the entry:**

```bash
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
DATE_PATH=$(date +"%Y/%m")
FILE_DATE=$(date +"%Y-%m-%d-%H%M")
SLUG=$(echo "YOUR_TITLE" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//' | sed 's/-$//' | head -c 50 | sed 's/-$//')

BD="$HOME/braindump"
mkdir -p "$BD/thoughts/$DATE_PATH"
```

3. **Write markdown file** at `$BD/thoughts/$DATE_PATH/$SLUG--$FILE_DATE.md`:

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

4. **Append to index.jsonl** (include `input` field with original content):

```bash
echo '{"type":"thought","title":"...","summary":"...","tags":[...],"input":"original user input","created_at":"...","file_path":"..."}' >> "$BD/thoughts/index.jsonl"
```

After creating, confirm with the title and file path.
