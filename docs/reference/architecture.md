# Architecture

Braindump is built around a **single shared Python core**. The CLI, the web UI,
and the Claude skills are all thin surfaces over the same functions in
`braindump/core/`, so behavior stays consistent — change the core and all three
inherit the fix.

## Package layout

```text
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
│   │   ├── digest.py          # journal → structured entries (two-pass Claude parse)
│   │   └── tags.py            # tag analytics
│   ├── cli/main.py            # `bd` Typer entrypoint
│   └── web/                   # FastAPI + Jinja2 + htmx UI
│       ├── app.py
│       ├── templates/
│       └── static/
├── claude/skills/             # /bd-* skills — all shell out to `bd`
│   ├── braindump/             # shared conventions (loaded by creation skills)
│   ├── bd-dump, bd-todo, bd-til, bd-thought, bd-prompt, bd-project
│   ├── bd-search, bd-list, bd-tags, bd-done, bd-digest
├── data-template/
│   └── scripts/               # session hooks only (session-start, session-end, forgotten-sessions)
├── tests/                     # pytest suite for braindump.core
├── pyproject.toml
└── install.sh
```

## Design principles

- **Plain markdown on disk** — browsable and backup-able; the JSONL indexes are
  a cache, not the source of truth.
- **Single shared core** — one code path for every operation. The `braindump.core`
  package has no I/O except through `store.py`.
- **Atomic mutations** — every index write is a temp-file rename under
  `fcntl.flock`, so concurrent writers never corrupt an index.
- **Projects are first class** — `project` is indexed and filterable everywhere,
  with its own dashboards and a persisted active-project focus.
- **Soft delete** — deletions move to `.trash/` rather than vanishing.
- **Expected failures are messages** — a missing id or a data directory this
  process can't write to is a normal thing to hit, not a bug. Those raise a
  `BraindumpError` (`braindump/core/errors.py`); a traceback means braindump
  is broken.

## Running where you can't write

Sandboxes (codex, seatbelt, a container) and read-only mounts hand `bd` a
`~/braindump` it can only read. Every filesystem call in `store.py` runs inside
a guard that turns the `OSError` into a `StorageError` naming the path, and the
`bd` root command group prints it as `error:` plus a hint and exits 1 — no
traceback. The web UI answers 403 with the same message. Reads are untouched,
so `bd list`, `bd search`, and `bd show` keep working; `bd doctor` probe-writes
the directory up front and reports `NOT WRITABLE` before anything else.

## The three surfaces

| Surface | Entry point | Notes |
|---------|-------------|-------|
| CLI | `braindump/cli/main.py` (`bd`) | Typer app; installed as a uv tool |
| Web UI | `braindump/web/app.py` (`bd serve` / `bd app`) | FastAPI + Jinja2 + htmx; `bd app` wraps it in pywebview |
| Claude skills | `claude/skills/bd-*` | Slash-skills that shell out to `bd` |

## Session tracking (optional)

Hooks can track Claude Code sessions via `SessionStart` / `SessionEnd`. Session
data lives in `~/braindump/sessions/started-YYYY-MM-DD.jsonl`. The scripts
(`session-start.sh`, `session-end.sh`, `forgotten-sessions.sh`) are plain bash
and unrelated to the `bd` CLI.

## Testing and quality

```bash
uv pip install -e ".[dev,web]"
pytest                   # core round-trip suite
```

The repo also wires up `ruff`, `ty`, `vulture`, and `deptry` via
[poethepoet](https://poethepoet.natn.io/) tasks (`poe check`, `poe fix`,
`poe lint`, …) defined in `poe_tasks.toml`.
