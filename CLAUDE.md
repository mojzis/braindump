# BRAINDUMP


## Overview

Braindump is a portable personal knowledge management system. It captures todos, TILs (Today I Learned), thoughts, prompts, and a daily journal. Everything is stored as plain markdown with JSONL indexes.

There are **three ways to use it**, all backed by the same Python core in `braindump/core/` so every operation goes through one code path:

1. **`bd` CLI** — direct shell access (`bd create`, `bd search`, `bd journal`, …).
2. **Claude Code skills** (`/bd-dump`, `/bd-todo`, `/bd-search`, …) — thin wrappers that shell out to `bd` from inside a Claude session.
3. **Local web UI** (`bd serve`, default `http://127.0.0.1:8765/`) — FastAPI + Jinja2 + htmx app for browsing, editing, and the daily journal.

When changing data behavior, change `braindump/core/` and all three surfaces inherit the fix.

## Installation

```bash
./install.sh
```

Requires [uv](https://docs.astral.sh/uv/). The installer runs `uv tool install` to put the `bd` command on your PATH, copies the Claude skills to `~/.claude/skills/`, and seeds the data directory at `~/braindump/`.

## Architecture

```
braindump/
├── braindump/                 # Python package — source of truth for all data ops
│   ├── core/
│   │   ├── config.py          # ~/braindump path, day cutoff, active project state
│   │   ├── schema.py          # pydantic models and type<->dir maps
│   │   ├── store.py           # slugs, fcntl-guarded IDs, atomic JSONL + markdown IO
│   │   ├── entries.py         # create / update / set_status / delete
│   │   ├── query.py           # search with filters + ripgrep full-text fallback
│   │   ├── projects.py        # project inventory, active-project focus
│   │   ├── journal.py         # daily journal with configurable day cutoff
│   │   └── tags.py            # tag analytics
│   ├── cli/main.py            # `bd` Typer entrypoint
│   └── web/                   # FastAPI + Jinja2 + htmx UI
│       ├── app.py
│       ├── templates/
│       └── static/
├── claude/skills/             # /bd-* skills — all shell out to `bd`
│   ├── braindump/             # shared conventions (loaded by creation skills)
│   ├── bd-dump, bd-todo, bd-til, bd-thought, bd-prompt
│   ├── bd-search, bd-list, bd-tags, bd-done
├── data-template/
│   └── scripts/               # session hooks only (session-start, session-end, forgotten-sessions)
├── tests/                     # pytest suite for braindump.core
├── pyproject.toml
└── install.sh
```

**Runtime data location:** `~/braindump/` (override with `BRAINDUMP_DIR`).

## CLI: `bd`

All data operations go through `bd`. Skills invoke it under the hood.

```
bd create <type> "<title>" [options]   # type: todo|til|thought|prompt
bd list [type] [--project] [--limit]
bd search <words...> [--type] [--project] [--status open|done|all] [--tag] [--since] [--until]
bd done <id|query|file_path>
bd update <id> [--title ...] [--tags a,b] [--project p] [--status s] [--body]
bd delete <id>
bd project list|show <name>|focus <name>|focus --clear
bd journal today|append|close|show <YYYY-MM-DD>
bd tags stats|show <tag>
bd doctor                                # validate indexes
bd serve [--host 127.0.0.1] [--port 8765]
```

## Web UI

`bd serve` starts a local FastAPI server (default `http://127.0.0.1:8765/`). Pages:

- `/` — dashboard (today's journal preview, open todos, recent activity, top tags, projects)
- `/journal/<YYYY-MM-DD>` — day editor with yesterday's content in a side panel, autosave, and a "finish the day" button
- `/capture` — quick-capture form (type, title, body, tags, project)
- `/entries` — searchable/filterable list
- `/entries/<id>` — view + edit-in-place (title, tags, project, status, body)
- `/projects`, `/projects/<name>` — project inventory and per-project dashboards
- `/tags` — tag analytics

Keyboard shortcuts: `g d` dashboard, `g j` journal, `g c` capture, `g e` entries, `g p` projects, `/` focus search, `?` help.

## Claude Skills

| Skill | Purpose |
|-------|---------|
| `/bd-dump` | Auto-categorizing quick capture |
| `/bd-todo` | Create todo |
| `/bd-til` | Record TIL |
| `/bd-thought` | Capture thought |
| `/bd-prompt` | Store prompt |
| `/bd-search` | Search entries |
| `/bd-list` | List recent entries |
| `/bd-tags` | Tag management and analytics |
| `/bd-done` | Mark a todo as done |
| `/bd-digest` | Digest a journal day into structured per-project entries |

Creation skills surface both `<existing-tags>` (via `bd tags stats`) and `<existing-projects>` (via `bd project list`) so Claude prefers reuse over drift.

## Data Format

**JSONL index** (`~/braindump/<type_dir>/index.jsonl`):
```json
{"id":42,"type":"todo","title":"Fix auth bug","summary":"...","tags":["auth","bug"],"project":"braindump","status":"pending","input":"...","created_at":"2026-04-11T14:15:02Z","file_path":"2026/04/fix-auth-bug--2026-04-11-1415.md"}
```

**Markdown files** (`~/braindump/<type_dir>/YYYY/MM/slug--timestamp.md`):
```markdown
---
type: todo
title: Fix auth bug
tags: ["auth", "bug"]
project: braindump
status: pending
created_at: 2026-04-11T14:15:02Z
---

# Fix auth bug

Authored content…

---

<details>
<summary>Original input</summary>

[Original user input verbatim]

</details>
```

**File naming:** `slugified-title--YYYY-MM-DD-HHmm.md` (double-dash separator for easy title selection). Journal files are the exception: one file per day at `journal/YYYY/MM/YYYY-MM-DD.md`.

## Type-Specific Fields

- **todo**: `subtype`, `status` (pending/in-progress/done), `priority`, `due_date`
- **til**: `category`, `source`
- **thought**: `mood`, `related_to`
- **prompt**: `prompt_type`, `model_target`
- **journal**: `date` (YYYY-MM-DD), `word_count`

## Key Conventions

- Creation skills output only `done: <file_path>` on success
- All timestamps are UTC ISO 8601
- Tags are lowercase with hyphens
- The `input` field in JSONL always stores original user input verbatim
- Index mutations rewrite the file atomically under `fcntl.flock`
- The `~/braindump/.state.json` holds the active project focus; it's applied automatically by `bd list` / `bd search` / the web UI until cleared with `bd project focus --clear`

## Journal day cutoff

Journaling honors a configurable daily cutoff hour (default `04:00` local, override via `BRAINDUMP_DAY_CUTOFF`). Writes before the cutoff still go to the previous day's file, so "finish the day when I go to bed" just works. The web UI also has an explicit "finish the day" button that seals today and opens tomorrow immediately.

## Session Tracking

Optional hooks track Claude Code sessions via `SessionStart`/`SessionEnd`. Session data lives in `~/braindump/sessions/started-YYYY-MM-DD.jsonl`.

Scripts: `~/braindump/scripts/session-start.sh`, `session-end.sh`, `forgotten-sessions.sh` (still plain bash; unrelated to the `bd` CLI).

## Development

```bash
uv venv
uv pip install -e ".[dev,web]"
pytest                 # run the core test suite
bd serve               # local web UI
```

When you finish a coding task in this repo, run the `python-review` skill over the changed Python before reporting done.
