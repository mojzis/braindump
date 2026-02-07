# Braindump Skill

You have access to the Braindump personal knowledge management system.

## Overview

Braindump is a system for capturing todos, TILs (Today I Learned), thoughts, and prompts. All data is stored in `~/braindump/` with JSONL indexes for fast search.

## Data Location

- **Base directory:** `~/braindump/`
- **Types:** `todos/`, `til/`, `thoughts/`, `prompts/`
- **Each type has:** `index.jsonl` + `YYYY/MM/` folders with markdown files
- **Scripts:** `~/braindump/scripts/` (create-entry.sh, search.sh, list.sh, tags.sh, done.sh)
- **ID counter:** `~/braindump/.next_id` (auto-incremented on entry creation)

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
| `/bd-tags [command]` | Tag management and analytics |
| `/bd-done <id or query>` | Mark a todo as done |

## Content Processing Levels

Three modes based on input prefix or context:

| Prefix | Level | Behavior |
|--------|-------|----------|
| `raw:` | Raw | Store verbatim. Title from first 50 chars. Tags still inferred. |
| *(none)* | Medium | Light formatting, structure. Default mode |
| `well:` | Well-done | Full elaboration, include relevant conversation context |

Detection order:
1. Input starts with "raw:" → raw mode, strip prefix
2. Input starts with "well:" → well-done mode, strip prefix
3. **Auto-well detection:** If input references prior conversation (e.g., "that feature", "what we discussed", "the thing from earlier"), auto-upgrade to well mode
4. If unclear whether context is relevant → ask the user
5. Otherwise → medium mode

## Project Context

Every entry captures the project context it was created in:

- **Field:** `project` (separate from tags)
- **Detection:** From current git repo name, or working directory name if not a git repo
- **Value:** lowercase project name (e.g., `braindump`, `my-app`)
- **Override:** User can specify explicitly if needed

This allows filtering/searching entries by the project they were created in.

## Tag Guidelines

- **Format:** lowercase, hyphens for multi-word (e.g., `gitlab-ci`)
- **Limit:** 1-5 tags per entry
- **Specificity:** Prefer specific over generic (`gitlab-ci` > `ci`)
- **Consistency:** Avoid duplicates (`docs` OR `documentation`, not both)

Check existing tags before creating new ones: `~/braindump/scripts/tags.sh stats`

## JSONL Index Schema

Each line in `index.jsonl` is a JSON object:

```json
{
  "id": 42,
  "type": "todo",
  "title": "Short title",
  "summary": "One-line summary",
  "tags": ["tag1", "tag2"],
  "project": "braindump",
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
project: braindump
created_at: 2026-01-21T14:30:00Z
---

# Fix auth bug

[Authored content based on doneness level]

---

<details>
<summary>Original input</summary>

[Original user input verbatim]

</details>
```

For raw mode: body IS the original input (no authoring), still include original section for consistency.

## Working with Braindump

When you need to:

1. **Create an entry**: Use the appropriate `/bd-*` command or use the script:
   ```bash
   # Write content to temp file (body only, no frontmatter)
   cat > /tmp/bd-content.md << 'EOF'
   Content here...
   EOF

   # Create entry (handles paths, timestamps, frontmatter, index)
   ~/braindump/scripts/create-entry.sh <type> "Title" /tmp/bd-content.md '{"type":"...","title":"...","tags":[...],...}'
   ```
   Types: `todos`, `til`, `thoughts`, `prompts`

2. **Search**: Use `/bd-search` or:
   ```bash
   ~/braindump/scripts/search.sh "query"
   ```

3. **List recent**: Use `/bd-list` or:
   ```bash
   ~/braindump/scripts/list.sh [type] [limit]
   ```

4. **Read an entry**: Read the markdown file directly from the path in the index

5. **Mark a todo done**: Use `/bd-done` or:
   ```bash
   ~/braindump/scripts/done.sh 42        # by ID
   ~/braindump/scripts/done.sh "query"   # by search
   ```

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
- Every entry has a numeric `id` field, auto-assigned on creation from `~/braindump/.next_id`
- Use IDs to reference entries (e.g., `done.sh 42`)
- Search supports status filtering: `search.sh "query" --open` or `--done`
