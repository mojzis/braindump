---
model: haiku
allowed-tools: ["Bash", "Write", "Read"]
description: Record a Today I Learned entry
---

# Braindump TIL (Today I Learned)

Record something you learned today.

## Input

$ARGUMENTS

## Instructions

1. **Parse the input** for optional flags:
   - `--category=programming|tools|concepts|debugging|general` (default: infer)
   - `--source=URL or description` (optional)

2. **Generate metadata:**
   - `title`: concise title describing what was learned (max 60 chars)
   - `summary`: one-line summary
   - `tags`: 1-3 relevant tags
   - `category`: infer if not specified

3. **Create the entry:**

```bash
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
DATE_PATH=$(date +"%Y/%m")
FILE_DATE=$(date +"%Y-%m-%d-%H%M")
SLUG=$(echo "YOUR_TITLE" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//' | sed 's/-$//' | head -c 50 | sed 's/-$//')

BD="$HOME/braindump"
mkdir -p "$BD/til/$DATE_PATH"
```

4. **Write markdown file** at `$BD/til/$DATE_PATH/$SLUG--$FILE_DATE.md`:

```markdown
---
type: til
category: programming
title: Your Title
tags: [tag1, tag2]
created_at: 2026-01-21T14:30:00Z
---

# Your Title

What I learned...
```

5. **Append to index.jsonl:**

```bash
echo '{"type":"til","category":"programming","title":"...","summary":"...","tags":[...],"created_at":"...","file_path":"..."}' >> "$BD/til/index.jsonl"
```

After creating, confirm with the title and a brief note about what category was chosen.
