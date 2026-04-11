---
description: Core braindump system conventions, schemas, and guidelines
---

# Braindump Skill

You have access to the Braindump personal knowledge management system.

## Overview

Braindump captures todos, TILs (Today I Learned), thoughts, prompts, and a daily journal. All data lives under `~/braindump/` with per-type JSONL indexes. Every data operation — from skills, the CLI, and the local web UI — goes through one shared Python core via the `bd` command.

## Data Location

- **Base directory:** `~/braindump/` (override with `BRAINDUMP_DIR`)
- **Types:** `todos/`, `til/`, `thoughts/`, `prompts/`, `journal/`
- **Each type has:** `index.jsonl` + `YYYY/MM/` folders with markdown files
- **CLI:** `bd` (installed via `uv tool install` or editable install; source lives in `claude/skills/../braindump` package)
- **ID counter:** `~/braindump/.next_id` (flock-guarded, auto-incremented)
- **Active project state:** `~/braindump/.state.json` (`{"active_project": "..."}`)

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
| `/bd-digest [date]` | Digest a journal day into structured per-project entries |

All of these invoke the `bd` CLI under the hood.

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
- **Active project filter:** `bd project focus <name>` sets a persistent filter; subsequent `bd list` / `bd search` calls scope to that project until `bd project focus --clear`

This allows filtering/searching entries by the project they were created in.

## Tag Guidelines

- **Format:** lowercase, hyphens for multi-word (e.g., `gitlab-ci`)
- **Limit:** 1-5 tags per entry
- **Specificity:** Prefer specific over generic (`gitlab-ci` > `ci`)
- **Consistency:** Avoid duplicates (`docs` OR `documentation`, not both)

**Available tags:**

<existing-tags>
!`bd tags stats 2>/dev/null || echo "(no tags yet)"`
</existing-tags>

**Available projects:**

<existing-projects>
!`bd project list 2>/dev/null || echo "(no projects yet)"`
</existing-projects>

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
  "updated_at": "2026-01-22T09:10:00Z",
  "file_path": "2026/01/slug--2026-01-21-1430.md"
}
```

The `input` field always contains the original user input exactly as provided. `updated_at` is set whenever the entry is mutated via `bd update` / `bd done`.

### Type-specific fields:

- **todo**: `subtype` (code/think/read/write/call/general), `status` (pending/in-progress/done), `priority` (high/medium/low), `due_date`
- **til**: `category` (programming/tools/concepts/debugging/general), `source`
- **thought**: `mood`, `related_to`
- **prompt**: `prompt_type` (system/user/template/example), `model_target`
- **journal**: `date` (YYYY-MM-DD), `word_count` — one entry per day, file is `journal/YYYY/MM/YYYY-MM-DD.md`

## File Naming Convention

Files are named: `slugified-title--YYYY-MM-DD-HHmm.md`

- Title slugified (lowercase, hyphens, max 50 chars)
- `--` separator (double-click selects just title)
- Date and time for uniqueness

Example: `fix-auth-bug--2026-01-21-1430.md`

Journal files are an exception: `journal/YYYY/MM/YYYY-MM-DD.md`, one per day.

**Important:** `file_path` in JSONL is always relative to the type directory, e.g., `2026/01/slug.md`.

## Markdown File Format

```markdown
---
type: todo
title: Fix auth bug
tags: ["auth", "bug"]
project: braindump
status: pending
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

All commands go through the `bd` CLI.

1. **Create an entry.** Body comes from stdin (piped) or a file. Original input can be passed inline or via a file:

   ```bash
   cat << 'BODY_EOF' | bd create todo "Fix auth bug" \
     --tag auth --tag bug \
     --project braindump \
     --summary "Session tokens are corrupted on refresh" \
     --status pending \
     --subtype code \
     --original-input "the raw user text verbatim"
   Authored body content here.
   BODY_EOF
   ```

   Types: `todo`, `til`, `thought`, `prompt`. For long multi-line original input, use `--original-input-file <path>` with a temp file.

2. **Search:** `bd search <words> [--type todo] [--project name] [--status open|done|all] [--tag foo]`. Defaults to JSONL output; pass `--human` for a readable list.

3. **List recent:** `bd list [type] --limit 10`. Human-readable by default.

4. **Read an entry:** Read the markdown file directly at `~/braindump/<type_dir>/<file_path>`.

5. **Mark a todo done:** `bd done <id|query|file_path>`.

6. **Edit an entry:** `bd update <id> [--title ...] [--tags a,b] [--project p] [--status s] [--body]` (use `--body` with stdin to replace the authored body).

7. **Projects:** `bd project list`, `bd project show <name>`, `bd project focus <name>` / `--clear`.

8. **Journal:** `bd journal today`, `bd journal append "some text"`, `bd journal close` (open tomorrow's file now), `bd journal show YYYY-MM-DD`.

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
- Every entry has a numeric `id` field, auto-assigned on creation
- Use IDs to reference entries (e.g., `bd done 42`)
- Search supports `--status open` / `--done` / `--all`
- Honor active project: if `bd project focus` is set, `bd list` and `bd search` scope to it unless you pass `--all`
