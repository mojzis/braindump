---
description: Quick capture with auto-categorization
allowed-tools: ["Bash", "Write", "Read", "Skill"]
argument-hint: "<content>"
---

# Braindump Quick Capture

## Input

$ARGUMENTS

## Step 0: Load braindump conventions

**Before doing anything else**, load the `braindump` skill for full system conventions (processing levels, tag rules, schemas, file format).

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
   - `tags`: 1-5 relevant tags (check existing with `~/braindump/scripts/tags.sh stats`)
   - `project`: from current git repo name or working directory
   - Type-specific fields based on chosen type

4. **Write content to temp file** (body only, with original input section):
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

5. **Create entry using script:**
   ```bash
   ~/braindump/scripts/create-entry.sh <type> "Your Title" /tmp/bd-content.md '{"type":"<singular-type>","title":"Your Title","summary":"...","tags":["tag1"],"project":"project-name"}'
   ```

   Note: Script type is plural (todos, thoughts, prompts) but JSON type field is singular (todo, thought, prompt). Exception: til stays as til.

## Output

`done: <file_path>` (the path returned by create-entry.sh)
