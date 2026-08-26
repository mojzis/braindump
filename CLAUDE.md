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
│   │   ├── errors.py          # expected failures (missing id, unwritable store)
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
bd project list|unregistered|show <name>|focus <name>|focus --clear
bd journal today|append|close|show <YYYY-MM-DD>
bd tags stats|show <tag>
bd doctor                                # validate indexes
bd serve [--host 127.0.0.1] [--port 8765]
bd app   [--host 127.0.0.1] [--port 8765] [-f]   # same UI in a native pywebview window (detached unless -f)
```

## Web UI

`bd serve` starts a local FastAPI server (default `http://127.0.0.1:8765/`). `bd app`
starts the same server in a background thread and points a native pywebview window at
it (see `braindump/web/desktop.py`) — a convenience wrapper, not a packaged build;
needs the `[app]` extra (which pins a Qt backend, since an isolated uv tool env
can't see system GTK bindings). `bd app` detaches by default, re-execing itself
as `bd app --foreground` in a new session with output redirected to
`~/braindump/.bd-app.log`; it attaches to an already-running server on the port
rather than starting a second one. Pages:

- `/` — dashboard (today's journal preview, open todos, recent activity, top tags, projects)
- `/journal` — the running doc: today's editor on top, the last ~7 days rendered below with lazy-load-on-scroll for older days, autosave, `✳ parse`, and a "finish the day" button
- `/journal/<YYYY-MM-DD>` — read-only permalink for a single past day (redirects to `/journal` for today)
- `/capture` — quick-capture form (type, title, body, tags, project)
- `/entries` — searchable/filterable list
- `/entries/<id>` — view + edit-in-place (title, tags, project, status, body)
- `/projects`, `/projects/<name>` — project inventory and per-project dashboards
- `/tags` — tag analytics

Keyboard shortcuts: `g d` dashboard, `g j` journal, `g c` capture, `g e` entries, `g p` projects, `/` focus search, `⌘/ctrl+enter` parse (on the journal page), `?` help.

### Journal parse pipeline

`✳ parse` on the running doc turns free-form journal writing into structured
braindump entries without leaving the page:

1. `POST /api/journal/<day>/parse` flushes the editor's current buffer to disk
   (`journal.replace_body`), then hands the day off to
   `braindump.core.digest.run_parse` as a background `asyncio.Task`, tracked
   in a single in-memory slot (`app.state.parse_job`) — only one parse can run
   at a time; a second `parse` while one is in flight gets `409`.
2. `run_parse` is a two-pass Claude pipeline (see `digest.py`'s module
   docstring for the full contract): pass 1 (no tools) groups journal lines
   into per-project sections and proposes entries; Python-side validation
   (`validate_pass1`) never trusts the model with the anchoring line indexes;
   pass 2 (read-only tools, cwd = the project's local checkout) lightly
   polishes wording when a local dir exists. Entries are created via the real
   `entries.create_entry` path, and the journal is annotated with
   `[→type#id]` marks and rewritten one section at a time, so a crash only
   risks duplicating whatever section was in flight.
3. The client polls `GET /journal/<day>/parse-status` every 2s for a status
   fragment; the editor is locked (read-only) for the duration
   (`document.body.dataset.parseRunning`, which also tells `live-refresh.js`
   to ignore the SSE reload that the newly-written entry files would
   otherwise trigger). The endpoint returns HTTP **286** + `HX-Trigger:
   parse-done` once the job finishes, which stops htmx's polling and tells
   the editor to unlock and refetch the (now-annotated) body from
   `GET /api/journal/<day>/body`.
4. `[→type#id]` marks render as clickable `.ref-chip` pills in past-day/
   permalink views via the `journal_markdown` Jinja filter — chip-linking
   runs as a regex pass *after* nh3 sanitizing, since nh3 strips `class`
   attributes.

If the `claude` CLI isn't on `PATH` (or `BRAINDUMP_CLAUDE_BIN` points nowhere),
the parse endpoint reports a friendly inline error instead of queuing a job.

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
- **project**: `description`, `state` (active/paused/archived), `area` (free-form grouping, reused like a tag — e.g. `dev-tools`, `cad-3d`), `local_dir`, `tech_stack`

## Key Conventions

- `bd create` / `bd done` / `bd update` echo `#<id>` alongside the file path; creation skills output only that line (`created: #<id> <file_path>`) on success, so the id survives into the transcript for later sessions
- All timestamps are UTC ISO 8601
- Tags are lowercase with hyphens
- A tag equal to the entry's own `project` is stripped on create/update (`entries.drop_self_project_tag`) — the field already says it, and project names otherwise dominate tag analytics; a tag naming a *different* project is a deliberate cross-reference and is kept
- The `input` field in JSONL always stores original user input verbatim
- Index mutations rewrite the file atomically under `fcntl.flock`
- Expected failures raise a `BraindumpError` from `core/errors.py` — a missing id, or a data directory this process can't write to (a sandbox, a read-only mount). `store.py` guards every filesystem call and translates the `OSError`; the `bd` root group prints `error:` + `hint:` and exits 1, the web UI answers 403/404. A traceback out of `bd` means braindump has a bug
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

When you finish a coding task in this repo, commit the change first, then run
the `python-review` skill over the changed Python (cml-style: commit, then
review the committed diff). Act on anything it flags — as a follow-up commit —
before reporting done.
