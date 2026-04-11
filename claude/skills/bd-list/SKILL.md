---
description: List recent braindump entries
allowed-tools: Bash, Read
argument-hint: [type] [limit]
---

# Braindump List

List recent braindump entries.

> For data format details, load the `braindump` skill.

## Input

$ARGUMENTS

## Instructions

1. **Parse arguments:**
   - No args: all types, last 10
   - Type name: `todo`, `til`, `thought`, `prompt`, `journal`
   - Number: limit results (e.g., `todo 5`)

2. **Run the list command:**

   ```bash
   bd list [type] --limit N
   ```

   Add `--project NAME` to scope to a specific project, or `--all` to override the active project filter.

3. **Display results** in the format produced by `bd list`:
   - `#id date [type] [status] title (project)`
   - Sorted newest first
   - Include the ID so users can reference entries (e.g., `/bd-done 42`)
