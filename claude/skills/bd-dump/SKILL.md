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
!`bd tags stats 2>/dev/null || echo "(no tags yet)"`
</existing-tags>

<existing-projects>
!`bd project list 2>/dev/null || echo "(no projects yet)"`
</existing-projects>

## Input

$ARGUMENTS

## Instructions

1. **Determine the type** from the content:
   - `todo` — actionable task
   - `til` — something learned
   - `thought` — idea, reflection, or random thought
   - `prompt` — a prompt to save

2. **Process the input** according to doneness level (raw:/well:/default)

3. **Infer metadata:**
   - `title`: concise title (max 60 chars)
   - `summary`: one-line summary
   - `tags`: 1-5 relevant tags from <existing-tags> (prefer reuse)
   - `project`: use <current-project> value, or pick from <existing-projects> if the content clearly belongs elsewhere
   - Type-specific fields based on chosen type

4. **Create entry via the bd CLI** (use the chosen type singular):

   ```bash
   OI=$(mktemp) && cat > "$OI" << 'OI_EOF'
   [Original user input verbatim]
   OI_EOF

   cat << 'BODY_EOF' | bd create <type> "Your Title" \
     --tag tag1 --tag tag2 \
     --project project-name \
     --summary "one-line summary" \
     --original-input-file "$OI"
   [Authored content based on doneness level]
   BODY_EOF

   rm -f "$OI"
   ```

   Add type-specific flags as needed: `--status`, `--subtype`, `--priority`, `--category`, `--source`, `--mood`, `--related-to`, `--prompt-type`, `--model-target`.

## Output

`done: <file_path>`
