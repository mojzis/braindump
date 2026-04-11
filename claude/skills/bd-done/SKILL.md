---
description: Mark a todo as done
allowed-tools: Bash, Read
argument-hint: <id or query>
---

# Braindump Done

Mark a todo as done by ID, file path, or search query.

## Input

$ARGUMENTS

## Instructions

1. **Parse the input.** The user may provide:
   - A numeric ID: `42`
   - A search query: `auth bug`
   - A file path: `2026/01/fix-auth-bug--2026-01-21-1430.md`

2. **Run the done command:**

   ```bash
   bd done "$ARGUMENTS"
   ```

3. **Handle results:**
   - If it succeeds, report which todo was marked done (the command prints `done: <file_path>`).
   - If multiple matches are found, `bd done` lists them on stderr and exits non-zero — show that list to the user and ask them to pick one by ID.
   - If no matches, say so and suggest `/bd-search` to find the right entry.

## Output

`done: <file_path>`
