---
description: Quick capture with auto-categorization
allowed-tools: Bash, Write, Read
argument-hint: <content>
---

# Braindump Quick Capture

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

1. **Determine the type** based on content:
   - `todos` - actionable task
   - `til` - something learned
   - `thoughts` - idea, reflection, or random thought
   - `prompts` - a prompt to save

2. **Process the input** according to doneness level (raw:/well:/default)

3. **Infer metadata:**
   - `title`: concise title (max 60 chars)
   - `summary`: one-line summary
   - `tags`: 1-5 relevant tags from <existing-tags> (prefer reuse)
   - `project`: use <current-project> value
   - Type-specific fields based on chosen type

4. **Create entry using script** (pipe content via stdin):
   ```bash
   cat << 'CONTENT_EOF' | ~/braindump/scripts/create-entry.sh <type> "Your Title" '{"type":"<singular-type>","title":"Your Title","summary":"...","tags":["tag1"],"project":"project-name"}'
   [Authored content based on doneness level]

   ---

   <details>
   <summary>Original input</summary>

   [Original user input verbatim]

   </details>
   CONTENT_EOF
   ```

   Note: Script type is plural (todos, thoughts, prompts) but JSON type field is singular (todo, thought, prompt). Exception: til stays as til.

## Output

`done: <file_path>` (the path returned by create-entry.sh)
