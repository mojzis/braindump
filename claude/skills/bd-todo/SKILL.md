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
!`bd tags stats 2>/dev/null || echo "(no tags yet)"`
</existing-tags>

<existing-projects>
!`bd project list 2>/dev/null || echo "(no projects yet)"`
</existing-projects>

Todo lifecycle vocabulary is pending, in-progress, in-qa, done, and cancelled.
Done is settled; use the QA command when Cockpit verified the work.

## Input

$ARGUMENTS

## Instructions

1. **Process the input** according to doneness level (raw:/well:/default)
2. **Infer metadata:**
   - `title`: concise title (max 60 chars)
   - `summary`: one-line summary
   - `tags`: 1-5 relevant tags from <existing-tags> (prefer reuse). Never tag
     an entry with its own project name — `project` already records that, and
     `bd create` strips it. Tag the subject, not the location.
   - `project`: use <current-project> value, or pick an existing project from <existing-projects> if the task clearly belongs to one
   - `subtype`: kind of task (code, think, read, write, call, general)
   - `status`: "pending"
   - `priority`: only if urgency is implied

3. **Create entry via the bd CLI.** Body goes through stdin; long original input goes through a temp file:

   ```bash
   OI=$(mktemp) && cat > "$OI" << 'OI_EOF'
   [Original user input verbatim]
   OI_EOF

   cat << 'BODY_EOF' | bd create todo "Your Title" \
     --tag tag1 --tag tag2 \
     --project project-name \
     --summary "one-line summary" \
     --status pending \
     --subtype code \
     --original-input-file "$OI"
   [Authored content based on doneness level]
   BODY_EOF

   rm -f "$OI"
   ```

   Repeat `--tag` per tag. Add `--priority` only if relevant.

## Output

`created: #<id> <file_path>` — echo the line `bd create` printed, verbatim (the id included; see the shared braindump skill for why).
