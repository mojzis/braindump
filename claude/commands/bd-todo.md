---
allowed-tools: ["Bash", "Write", "Read"]
description: Create a todo entry
argument-hint: "<task>"
---

# Braindump Todo

Create a todo entry following the braindump skill rules.

## Input

$ARGUMENTS

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
   ~/braindump/scripts/create-entry.sh todos "Your Title" /tmp/bd-content.md '{"type":"todo","title":"Your Title","summary":"...","tags":["tag1"],"project":"project-name","status":"pending"}'
   ```

## Output

`done: <file_path>` (the path returned by create-entry.sh)
