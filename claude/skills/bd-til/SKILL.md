---
description: Record a Today I Learned entry
allowed-tools: Bash, Write, Read
argument-hint: <what you learned>
---

# Braindump TIL

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
   - `category`: topic area (programming, tools, concepts, debugging, etc.)
   - `source`: if a source is mentioned

3. **Create entry using script** (pipe content via stdin):
   ```bash
   cat << 'CONTENT_EOF' | ~/braindump/scripts/create-entry.sh til "Your Title" '{"type":"til","title":"Your Title","summary":"...","tags":["tag1"],"project":"project-name"}'
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
