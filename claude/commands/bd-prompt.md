---
model: haiku
allowed-tools: ["Bash", "Write", "Read"]
description: Store a prompt for later use
argument-hint: "<prompt content>"
---

# Braindump Prompt

Store a prompt for later reference or reuse.

## Input

$ARGUMENTS

## Instructions

1. **Analyze the content** and generate metadata (all inferred):
   - `title`: concise title for the prompt (max 60 chars)
   - `summary`: one-line description of what the prompt does
   - `tags`: 1-3 relevant tags
   - `prompt_type`: inferred type (system prompt, user message, template, example, etc.)
   - `model_target`: if a specific model is mentioned

2. **Create the entry:**

```bash
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
DATE_PATH=$(date +"%Y/%m")
FILE_DATE=$(date +"%Y-%m-%d-%H%M")
SLUG=$(echo "YOUR_TITLE" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//' | sed 's/-$//' | head -c 50 | sed 's/-$//')

BD="$HOME/braindump"
mkdir -p "$BD/prompts/$DATE_PATH"
```

3. **Write markdown file** at `$BD/prompts/$DATE_PATH/$SLUG--$FILE_DATE.md`:

```markdown
---
type: prompt
title: Your Title
tags: [tag1, tag2]
created_at: 2026-01-21T14:30:00Z
---

# Your Title

The prompt content...
```

4. **Append to index.jsonl** (include `input` field with original content):

```bash
echo '{"type":"prompt","title":"...","summary":"...","tags":[...],"input":"original user input","created_at":"...","file_path":"..."}' >> "$BD/prompts/index.jsonl"
```

## Output

CRITICAL: Your ONLY output must be exactly `done: <file_path>`. No confirmations, no summaries, no explanations. Just those two words and the path.
