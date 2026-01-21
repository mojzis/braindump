# Braindump Skill

You have access to the Braindump personal knowledge management system.

## Overview

Braindump is a system for capturing todos, TILs (Today I Learned), thoughts, and prompts. All data is stored in `~/braindump/` with JSONL indexes for fast search.

## Data Location

- **Base directory:** `~/braindump/`
- **Types:** `todos/`, `til/`, `thoughts/`, `prompts/`
- **Each type has:** `index.jsonl` + `YYYY/MM/` folders with markdown files
- **Scripts:** `~/braindump/scripts/` (search.sh, slugify.sh, list.sh)

## Commands Available

| Command | Purpose |
|---------|---------|
| `/bd-dump <content>` | Quick capture with auto-categorization |
| `/bd-todo <task>` | Create a todo |
| `/bd-til <learning>` | Record something learned |
| `/bd-thought <idea>` | Capture a thought |
| `/bd-prompt <content>` | Store a prompt |
| `/bd-search <query>` | Search entries |
| `/bd-list [type] [n]` | List recent entries |

## JSONL Index Schema

Each line in `index.jsonl` is a JSON object:

```json
{
  "type": "todo",
  "title": "Short title",
  "summary": "One-line summary",
  "tags": ["tag1", "tag2"],
  "input": "original user input verbatim",
  "created_at": "2026-01-21T14:30:00Z",
  "file_path": "2026/01/slug--2026-01-21-1430.md"
}
```

The `input` field always contains the original user input exactly as provided.

### Type-specific fields:

- **todo**: `subtype` (code/think/read/write/call/general), `status` (pending/in-progress/done), `priority` (high/medium/low), `due_date`
- **til**: `category` (programming/tools/concepts/debugging/general), `source`
- **thought**: `mood`, `related_to`
- **prompt**: `prompt_type` (system/user/template/example), `model_target`

## File Naming Convention

Files are named: `slugified-title--YYYY-MM-DD-HHmm.md`

- Title slugified (lowercase, hyphens, max 50 chars)
- `--` separator (double-click selects just title)
- Date and time for uniqueness

Example: `fix-auth-bug--2026-01-21-1430.md`

## Markdown File Format

```markdown
---
type: todo
title: Fix auth bug
tags: [auth, bug]
created_at: 2026-01-21T14:30:00Z
---

# Fix auth bug

Content here...
```

## Working with Braindump

When you need to:

1. **Create an entry**: Use the appropriate `/bd-*` command or manually:
   - Create markdown file in `~/braindump/{type}/YYYY/MM/`
   - Append JSON line to `~/braindump/{type}/index.jsonl`

2. **Search**: Use `/bd-search` or:
   ```bash
   ~/braindump/scripts/search.sh "query"
   ```

3. **List recent**: Use `/bd-list` or:
   ```bash
   ~/braindump/scripts/list.sh [type] [limit]
   ```

4. **Read an entry**: Read the markdown file directly from the path in the index

## Output Style

After successfully creating an entry, respond only with:
```
done: <file_path>
```

No extra text, summaries, or commentary unless:
- There's an error to report
- You need to ask a clarifying question

## Tips

- All timestamps are UTC ISO 8601 format
- Tags are lowercase, no spaces (use hyphens)
- Summaries should be one line, under 100 chars
- The index is append-only; to update, you'd need to rewrite the line
