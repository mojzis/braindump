---
description: Capture a thought or idea
allowed-tools: ["Bash", "Write", "Read", "Skill"]
argument-hint: "<idea or reflection>"
---

# Braindump Thought

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
   - `mood`: if evident from the content
   - `related_to`: if about something specific

3. **Write content to temp file** (body only, with original input section):
   ```bash
   cat > /tmp/bd-content.md << 'CONTENT_EOF'
   [Authored content based on doneness level]

   ---

   <details>
   <summary>Original input</summary>

   [Original user input verbatim]

   </details>
   CONTENT_EOF
   ```

4. **Create entry using script:**
   ```bash
   ~/braindump/scripts/create-entry.sh thoughts "Your Title" /tmp/bd-content.md '{"type":"thought","title":"Your Title","summary":"...","tags":["tag1"],"project":"project-name"}'
   ```

## Output

`done: <file_path>` (the path returned by create-entry.sh)
