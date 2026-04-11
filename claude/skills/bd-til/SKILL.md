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
!`bd tags stats 2>/dev/null || echo "(no tags yet)"`
</existing-tags>

<existing-projects>
!`bd project list 2>/dev/null || echo "(no projects yet)"`
</existing-projects>

## Input

$ARGUMENTS

## Instructions

1. **Process the input** according to doneness level (raw:/well:/default)
2. **Infer metadata:**
   - `title`: concise title (max 60 chars)
   - `summary`: one-line summary
   - `tags`: 1-5 relevant tags from <existing-tags> (prefer reuse)
   - `project`: use <current-project> value (or an existing project if more relevant)
   - `category`: topic area (programming, tools, concepts, debugging, etc.)
   - `source`: if a source is mentioned

3. **Create entry via the bd CLI:**

   ```bash
   OI=$(mktemp) && cat > "$OI" << 'OI_EOF'
   [Original user input verbatim]
   OI_EOF

   cat << 'BODY_EOF' | bd create til "Your Title" \
     --tag tag1 --tag tag2 \
     --project project-name \
     --summary "one-line summary" \
     --category debugging \
     --original-input-file "$OI"
   [Authored content based on doneness level]
   BODY_EOF

   rm -f "$OI"
   ```

## Output

`done: <file_path>`
