---
description: Create a todo entry
allowed-tools: Bash, Write, Read, Skill
argument-hint: <task>
---

# Braindump Todo

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
   - `subtype`: kind of task (coding, planning, reading, etc.)
   - `status`: "pending"
   - `priority`: if urgency is implied

3. **Create entry using script** (pipe content via stdin):
   ```bash
   cat << 'CONTENT_EOF' | ~/braindump/scripts/create-entry.sh todos "Your Title" '{"type":"todo","title":"Your Title","summary":"...","tags":["tag1"],"project":"project-name","status":"pending"}'
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
