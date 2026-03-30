---
description: Create a todo entry
allowed-tools: Bash, Write, Read
argument-hint: <task>
---

# Braindump Todo

## Conventions

!`awk '/^---$/{n++;next}n>1' ~/.claude/skills/braindump/SKILL.md`

## Context

<current-project>
!`git rev-parse --show-toplevel 2>/dev/null | xargs basename || basename "$PWD"`
</current-project>

<existing-tags>
!`~/braindump/scripts/tags.sh stats`
</existing-tags>

## Input

$ARGUMENTS

## Instructions

1. **Process the input** according to doneness level (raw:/well:/default)
2. **Infer metadata:**
   - `title`: concise title (max 60 chars)
   - `summary`: one-line summary
   - `tags`: 1-5 relevant tags from <existing-tags> (prefer reuse)
   - `project`: use <current-project> value
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
