# Quickstart

The first five minutes with braindump. This assumes you've already
[installed](installation.md) the `bd` CLI.

## Capture something

Every entry has a **type** — `todo`, `til`, `thought`, or `prompt`. The body is
read from stdin, so you can pipe or type it:

```bash
bd create todo "Fix auth bug" --tag auth --tag bug
```

Not sure what type it is? Let braindump categorize it for you from a Claude
session with the [`/bd-dump`](../guides/claude-skills.md) skill, or just create a
`thought` and refine later.

## List what you've got

```bash
bd list                     # recent entries, all types
bd list todo                # just todos
bd list til 5               # the last 5 TILs
```

## Search

`bd search` does a multi-word **AND** search across titles, tags, and summaries,
with a ripgrep full-text fallback over the markdown bodies:

```bash
bd search auth login --status open       # open todos mentioning both words
bd search --tag auth --since 2026-01-01  # filter by tag and date
```

## Mark a todo done

```bash
bd done 42                   # by ID
bd done "auth bug"           # by query
```

## Scope everything to a project

`project` is a first-class, indexed field. Set an active project once and every
subsequent `bd list` / `bd search` (and the web UI) stays scoped to it:

```bash
bd project focus braindump   # scope all queries to "braindump"
bd project focus --clear      # back to everything
```

## Keep a journal

```bash
bd journal today             # show today's journal state
echo "shipped the parse pipeline" | bd journal append
bd journal close             # seal today, open tomorrow
```

The journal honors a configurable [day cutoff](../guides/journal.md) (default
`04:00`), so late-night writes land on the previous day where you'd expect them.

## Open the web UI

```bash
bd serve                     # http://127.0.0.1:8765/
```

You get a dashboard, the daily journal editor, quick capture, a filterable entry
list, and per-project dashboards. See the [Web UI guide](../guides/web-ui.md).

## Next steps

- [Full `bd` CLI reference](../guides/cli.md)
- [Claude `/bd-*` skills](../guides/claude-skills.md)
- [Data format](../reference/data-format.md) — how entries are stored on disk
