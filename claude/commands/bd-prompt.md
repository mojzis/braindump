---
model: haiku
allowed-tools: ["Bash", "Write", "Read"]
description: Store a prompt for later use
---

# Braindump Prompt

Store a prompt for later reference or reuse.

## Input

$ARGUMENTS

## Instructions

1. **Parse the input** for optional flags:
   - `--type=system|user|template|example` (default: infer)
   - `--model=claude|gpt|gemini|...` (optional, target model)

2. **Generate metadata:**
   - `title`: concise title for the prompt (max 60 chars)
   - `summary`: one-line description of what the prompt does
   - `tags`: 1-3 relevant tags
   - `prompt_type`: infer if not specified (system for system prompts, user for user messages, template for fill-in-the-blank, example for few-shot examples)

3. **Create the entry:**

```bash
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
DATE_PATH=$(date +"%Y/%m")
FILE_DATE=$(date +"%Y-%m-%d-%H%M")
SLUG=$(echo "YOUR_TITLE" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//' | sed 's/-$//' | head -c 50 | sed 's/-$//')

BD="$HOME/braindump"
mkdir -p "$BD/prompts/$DATE_PATH"
```

4. **Write markdown file** at `$BD/prompts/$DATE_PATH/$SLUG--$FILE_DATE.md`:

```markdown
---
type: prompt
prompt_type: system
title: Your Title
tags: [tag1, tag2]
created_at: 2026-01-21T14:30:00Z
---

# Your Title

The prompt content...
```

5. **Append to index.jsonl:**

```bash
echo '{"type":"prompt","prompt_type":"system","title":"...","summary":"...","tags":[...],"created_at":"...","file_path":"..."}' >> "$BD/prompts/index.jsonl"
```

After creating, confirm with the title, prompt type, and file path.
