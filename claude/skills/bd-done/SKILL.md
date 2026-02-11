---
description: Mark a todo as done
allowed-tools: ["Bash", "Read"]
argument-hint: "<id or query>"
---

# Braindump Done

Mark a todo as done by ID or search query.

## Input

$ARGUMENTS

## Instructions

1. **Parse the input** - the user may provide:
   - A numeric ID: `42`
   - A search query: `auth bug`
   - A file path: `2026/01/fix-auth-bug--2026-01-21-1430.md`

2. **Run the done script:**

```bash
~/braindump/scripts/done.sh "$ARGUMENTS"
```

3. **Handle results:**
   - If the script succeeds, report which todo was marked done
   - If multiple matches are found, show the list with IDs and ask the user to pick one
   - If no matches, say so and suggest `/bd-search` to find the right entry

## Output

`done: #<id> <title>`
