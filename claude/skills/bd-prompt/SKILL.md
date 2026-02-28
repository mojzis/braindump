---
description: Store a prompt for later use
allowed-tools: Bash, Write, Read, Skill
argument-hint: <prompt content>
---

# Braindump Prompt

## Input

$ARGUMENTS

## Step 0: Load braindump conventions

**Before doing anything else**, load the `braindump` skill for full system conventions (processing levels, tag rules, schemas, file format).

## Instructions

1. **Process the input** according to doneness level (raw:/well:/default)
2. **Infer metadata:**
   - `title`: concise title (max 60 chars)
   - `summary`: one-line summary
   - `tags`: 1-5 relevant tags (check existing with `~/braindump/scripts/tags.sh stats`)
   - `project`: from current git repo name or working directory
   - `prompt_type`: inferred type (system, user, template, example, etc.)
   - `model_target`: if a specific model is mentioned

3. **Create entry using script** (pipe content via stdin):
   ```bash
   cat << 'CONTENT_EOF' | ~/braindump/scripts/create-entry.sh prompts "Your Title" '{"type":"prompt","title":"Your Title","summary":"...","tags":["tag1"],"project":"project-name"}'
   [Authored content based on doneness level]

   ---

   <details>
   <summary>Original input</summary>

   [Original user input verbatim]

   </details>
   CONTENT_EOF
   ```

## Output

`done: <file_path>` (the path returned by create-entry.sh)
