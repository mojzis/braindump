# CLI — `bd`

All data operations go through the `bd` command. The Claude skills and the web
UI are both thin surfaces over the same core, so anything you can do in them you
can do here.

Run `bd --help` for the authoritative, auto-generated list, or `bd <command>
--help` for any subcommand.

## Command overview

```text
bd create <type> "<title>" [options]   # type: todo | til | thought | prompt | project
bd list [type] [--project] [--limit]
bd search <words...> [--type] [--project] [--status open|done|all] [--tag] [--since] [--until]
bd done <id | query | file_path>
bd update <id> [--title ...] [--tags a,b] [--project p] [--status s] [--body]
bd delete <id>
bd project list | unregistered | show <name> | focus <name> | focus --clear
bd journal today | append | close | show <YYYY-MM-DD>
bd tags stats | show <tag>
bd doctor                              # validate indexes
bd serve [--host 127.0.0.1] [--port 8765]
bd app   [--host 127.0.0.1] [--port 8765]   # same UI in a native pywebview window
```

## Creating entries

```bash
bd create todo "Fix auth bug" --tag auth --tag bug --priority high
```

The **body** is read from stdin unless you pass `--body-file`:

```bash
echo "Token refresh races with logout." | bd create todo "Fix auth bug"
```

Common options:

| Option | Purpose |
|--------|---------|
| `--tag`, `-t` | Add a tag (repeatable) |
| `--project`, `-p` | Set the project (defaults to the git repo / directory name in skills) |
| `--summary`, `-s` | One-line summary |
| `--status` | For todos: `pending`, `in-progress`, `done` |
| `--priority` | For todos |
| `--due-date` | For todos (`YYYY-MM-DD`) |
| `--body-file` | Read the body from a file instead of stdin |
| `--original-input` / `--original-input-file` | Store verbatim source input |

Type-specific fields also exist (`--subtype`, `--category`, `--source`,
`--mood`, `--related-to`, `--prompt-type`, `--model-target`, and the project
fields `--description`, `--state`, `--area`, `--local-dir`, `--tech`). See
[Data format](../reference/data-format.md) for which fields belong to which type.

On success `bd create` prints exactly:

```text
created: #<id> <file_path>
```

The id is the entry's handle for everything after creation — `bd show <id>`,
`bd update <id>`, `bd done <id>` — so it's echoed at creation time rather than
left to be looked up. `bd done` and `bd update` print `#<id>` the same way.

## Listing

```bash
bd list                 # newest 10 across all types
bd list todo            # todos only
bd list til -n 5        # last 5 TILs
bd list --all           # ignore the active-project focus
bd list --json          # machine-readable output
```

## Searching

`bd search` is a multi-word **AND** search across title, tags, and summary, with
a ripgrep full-text fallback over the markdown bodies.

```bash
bd search auth login --status open        # open todos mentioning both words
bd search --tag auth --since 2026-01-01   # filter without a text query
bd search parse --type til --human        # human-readable instead of JSON
```

| Option | Purpose |
|--------|---------|
| `--type` | Restrict to one type |
| `--project`, `-p` / `--all` | Scope to a project / ignore the active focus |
| `--status` | `open`, `done`, or `all` (default `all`) |
| `--tag`, `-t` | Require a tag (repeatable) |
| `--since` / `--until` | Date bounds (`YYYY-MM-DD`) |
| `--limit`, `-n` | Max results (default 50) |
| `--no-fulltext` | Skip the ripgrep body fallback |
| `--json` / `--human` | Output format (JSON by default) |

## Updating and completing

```bash
bd done 42                       # mark a todo done by ID …
bd done "auth bug"               # … or by query …
bd done 2026/01/fix-auth-bug--2026-01-21-1430.md   # … or by file path

bd update 42 --tags a,b --project foo --status in-progress
bd update 42 --body              # replace the body from stdin
bd delete 42                     # soft-delete → moves to ~/braindump/.trash/
```

## Projects

`project` is a first-class field. Project **entries** (type `project`) carry
metadata; a bare project name that has no entry yet shows up as "unregistered".

```bash
bd project list                  # inventory with counts
bd project unregistered          # project names referenced but not yet created
bd project show braindump        # per-project dashboard
bd project focus braindump       # persist an active-project filter
bd project focus --clear         # remove it
```

The active focus is stored in `~/braindump/.state.json` and applied
automatically by `bd list`, `bd search`, and the web UI until cleared.

## Journal

```bash
bd journal today                 # today's journal state
echo "shipped it" | bd journal append
bd journal close                 # seal today, open tomorrow
bd journal show 2026-01-21       # a specific past day
```

See the [Journal guide](journal.md) for the day-cutoff behavior and the web
parse pipeline.

## Tags

```bash
bd tags stats                    # tag frequency analytics
bd tags show auth                # entries carrying a tag
```

## Maintenance

```bash
bd doctor                        # validate that JSONL indexes match the markdown on disk
```

## Serving the UI

```bash
bd serve                         # http://127.0.0.1:8765/
bd serve --host 0.0.0.0 --port 9000
bd app                           # same UI in a native desktop window (needs the [app] extra)
```
