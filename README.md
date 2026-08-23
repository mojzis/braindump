# Braindump

A portable Claude Code-integrated personal knowledge management system. Capture todos, TILs, thoughts, prompts, and a daily journal. Everything is plain markdown on disk with JSONL indexes for fast structured search, a `bd` CLI, a local web UI, and a set of `/bd-*` Claude slash-skills — all driven by a single shared Python core.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — used to install the `bd` CLI
- [ripgrep](https://github.com/BurntSushi/ripgrep) — optional, enables full-text fallback in `bd search`

## Installation

Braindump is **not published to PyPI** — you install it from a local checkout.

```bash
git clone <this-repo> ~/git/braindump
cd ~/git/braindump
./install.sh
```

This will:
1. `uv tool install` the `bd` CLI (with the `web` extra for the local UI)
2. Copy Claude skills to `~/.claude/skills/`
3. Seed the data directory at `~/braindump/` with empty indexes for each type
4. Drop optional session-tracking scripts into `~/braindump/scripts/`

### How the `uv tool` install works

`bd` is installed as a [uv tool](https://docs.astral.sh/uv/concepts/tools/): uv
builds the package from this directory and drops it into its **own isolated
environment** under `~/.local/share/uv/tools/braindump/`, then puts a `bd`
shim on your `PATH` at `~/.local/bin/bd`.

Two consequences worth internalizing:

- **The installed `bd` is a copy, not a live link to this checkout.** Editing
  files here does not change the `bd` on your `PATH` until you reinstall.
- **The tool environment is isolated from system site-packages.** Anything `bd`
  needs at runtime has to come from an extra (see `[project.optional-dependencies]`
  in `pyproject.toml`), not from a distro package.

Reinstall from the repo directory to pick up local changes (or fix a broken
install) — the trailing `.` is the local path, and the bracketed part picks the
extras:

```bash
cd ~/git/braindump
uv tool install --force --reinstall --no-cache ".[web]"      # CLI + bd serve
uv tool install --force --reinstall --no-cache ".[app]"      # + bd app desktop window
```

Extras are not cumulative across installs — each `uv tool install` replaces the
environment, so pass every extra you want in one go (`".[app]"` already pulls in
`[web]`). Missing extras show up as import errors at run time:
`ModuleNotFoundError: No module named 'uvicorn'` means a `bd` installed without
`[web]`. Running `./install.sh` does the `[web]` install for you.

Useful uv tool commands:

```bash
uv tool list                 # what's installed, and which commands each provides
uv tool uninstall braindump  # remove bd entirely
uv tool dir                  # where the tool environments live
```

## Usage

### CLI

```bash
bd --help                             # overview
bd list                               # recent entries
bd search auth login --status open    # multi-word AND search
bd create todo "Fix auth" --tag auth  # create (body from stdin)
bd done 42                            # mark todo done
bd update 42 --tags a,b --project foo # patch metadata
bd project focus braindump            # scope all queries to a project
bd journal today                      # today's journal state
bd serve                              # local web UI at http://127.0.0.1:8765/
bd app                                # same UI in a native desktop window (detached)
```

### Web UI

`bd serve` opens a local FastAPI + htmx server with:

- Dashboard (today's journal preview, open todos, recent activity, top tags, projects)
- Daily journal editor with yesterday's content in a side panel, autosave, and a "finish the day" button (honors a configurable day cutoff, default `04:00`)
- Quick-capture form
- Searchable entry list with type/project/status/tag/date filters
- Inline-edit for title, tags, project, status, and body
- Per-project dashboards with open todos, recent activity, and tag counts
- Active-project focus mode applied across every view

Keyboard shortcuts: `g d`, `g j`, `g c`, `g e`, `g p`, `/` to focus search, `?` for help.

### Desktop window

`bd app` runs the exact same web UI, but inside a native [pywebview](https://pywebview.flet.dev/)
window instead of a browser tab — a lightweight way to keep braindump open as its
own app locally. It's not a packaged/bundled build: it just starts the server and
points a window at it.

It **detaches by default** — the command returns immediately, the window keeps
running after you close the terminal, and anything the process prints goes to
`~/braindump/.bd-app.log`:

```bash
bd app                  # detach, print the pid, hand the shell back
bd app --foreground     # stay attached (use this when debugging a crash)
```

If something is already serving on the port (a running `bd serve`, or another
`bd app`), the window attaches to that server instead of starting a second one.
The server belongs to whichever process started it, so closing *that* window
also stops the server for any window that attached to it.

Requires the `[app]` extra:

```bash
uv tool install --force --reinstall --no-cache ".[app]"
```

Without it, `bd app` prints an install hint and falls back to suggesting `bd serve`.

The `[app]` extra pulls `pywebview[qt]`, i.e. a Qt webview backend (`qtpy` +
PyQt6 WebEngine, ~200 MB of wheels), rather than relying on the host's GTK/WebKit
bindings. pywebview has no renderer of its own, and system GTK bindings
(`python-gobject` + `webkit2gtk`) are invisible to an isolated uv tool
environment — and are built against the system Python, which needn't match the
one uv picked. Bundling Qt makes `bd app` work without any distro packages.

Note that PyQt6 is GPL-3/commercial-licensed while braindump itself is MIT. It's
an optional extra you install yourself and nothing is distributed together, so
this is not a problem in practice — but if you'd rather not have it, skip `[app]`
and use `bd serve` in a browser.

Start a new Claude Code session after installation. Available:

| Command | Purpose |
|---------|---------|
| `/bd-dump <content>` | Quick capture with auto-categorization |
| `/bd-todo <task>` | Create a todo |
| `/bd-til <learning>` | Record a TIL |
| `/bd-thought <idea>` | Capture a thought |
| `/bd-prompt <content>` | Store a prompt |
| `/bd-search <query>` | Search entries |
| `/bd-list [type] [n]` | List recent entries |
| `/bd-tags [command]` | Tag analytics |
| `/bd-done <id or query>` | Mark a todo as done |
| `/bd-digest [date]` | Digest a journal day into structured per-project entries |

All of them delegate to the same `bd` CLI, so what you see in the web UI is exactly what the skills produce.

## Data layout

```
~/braindump/
├── todos/      index.jsonl + YYYY/MM/<slug>--<timestamp>.md
├── til/        …
├── thoughts/   …
├── prompts/    …
├── journal/    index.jsonl + YYYY/MM/<YYYY-MM-DD>.md  (one file per day)
├── sessions/   Claude Code session hooks output
├── scripts/    session hooks only
├── .next_id    shared ID counter (flock-guarded)
├── .state.json active project etc.
└── .trash/     soft-deleted entries
```

### JSONL index

```json
{"id":42,"type":"todo","title":"Fix auth bug","summary":"...","tags":["auth"],"project":"braindump","status":"pending","input":"...","created_at":"2026-04-11T14:15:02Z","file_path":"2026/04/fix-auth-bug--2026-04-11-1415.md"}
```

### Markdown frontmatter

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

[verbatim user input]

</details>
```

## Development

```bash
uv venv
uv pip install -e ".[dev,web]"
pytest                   # core test suite
bd serve --reload        # local UI with autoreload
```

The `braindump.core` package has no I/O except through `store.py`, and every mutation is atomic (`fcntl.flock` + temp-file rename). See `tests/` for the round-trip coverage.

## Design

- **Plain markdown on disk** — browsable and backup-able; the JSONL indexes are a cache, not the source of truth
- **Single shared core** — CLI, web UI, and Claude skills all call the same Python functions, so behavior stays consistent
- **Projects are first class** — `project` is indexed, filterable everywhere, and has its own dashboards; the active-project focus is persisted so every query stays scoped
- **Journal with a sane day cutoff** — late-night writes go to the previous day's file by default; "finish the day" button seals today manually
- **Soft delete** — removing an entry moves it to `.trash/` so nothing is ever lost accidentally
