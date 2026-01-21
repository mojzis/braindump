---
model: haiku
allowed-tools: ["Bash", "Write", "Read"]
description: Record a Today I Learned entry
argument-hint: "<what you learned>"
---

# Braindump TIL (Today I Learned)

Record something you learned today.

## Input

$ARGUMENTS

## Instructions

1. **Analyze the content** and generate metadata (all inferred):
   - `title`: concise title describing what was learned (max 60 chars)
   - `summary`: one-line summary
   - `tags`: 1-3 relevant tags
   - `category`: topic area (inferred from content)
   - `source`: if a source is mentioned

2. **Create the entry:**

```bash
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
DATE_PATH=$(date +"%Y/%m")
FILE_DATE=$(date +"%Y-%m-%d-%H%M")
SLUG=$(echo "YOUR_TITLE" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//' | sed 's/-$//' | head -c 50 | sed 's/-$//')

BD="$HOME/braindump"
mkdir -p "$BD/til/$DATE_PATH"
```

3. **Write markdown file** at `$BD/til/$DATE_PATH/$SLUG--$FILE_DATE.md`:

```markdown
---
type: til
title: Your Title
tags: [tag1, tag2]
created_at: 2026-01-21T14:30:00Z
---

# Your Title

What I learned...
```

4. **Append to index.jsonl** (include `input` field with original content):

```bash
echo '{"type":"til","title":"...","summary":"...","tags":[...],"input":"original user input","created_at":"...","file_path":"..."}' >> "$BD/til/index.jsonl"
```

## Output

CRITICAL: Your ONLY output must be exactly `done: <file_path>`. No confirmations, no summaries, no explanations. Just those two words and the path.
