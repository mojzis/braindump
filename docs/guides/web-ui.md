# Web UI

`bd serve` starts a local FastAPI + Jinja2 + htmx server, by default at
[http://127.0.0.1:8765/](http://127.0.0.1:8765/).

```bash
bd serve                         # default host/port
bd serve --host 0.0.0.0 --port 9000
bd app                           # same UI in a native pywebview window ([app] extra)
```

`bd app` starts the same server in a background thread and points a native
[pywebview](https://pywebview.flet.dev/) window at it — a convenience wrapper,
not a packaged build.

## Copying text out

The desktop window has no browser chrome, and pywebview turns the native
right-click menu off, so the UI brings its own copy affordances:

- **`copy` buttons** on an entry, on today's journal editor, and on every past
  day — they copy the **markdown source**, not the rendered HTML, so what you
  paste round-trips back into braindump.
- **Selection + `⌘/Ctrl + C`** works as usual; in a webview whose own copy
  handler never fires, the page copies the selection itself.
- **Right-click** in the `bd app` window gives copy / cut / paste / select-all.

The window also has to grant JavaScript clipboard access on the Qt backend,
which `bd app` does when the window is created. If that fails (an unfamiliar
backend, say), the log at `~/braindump/.bd-app.log` says so and everything but
the right-click menu still works.

## Pages

| Route | What it is |
|-------|------------|
| `/` | Dashboard — today's journal preview, open todos, recent activity, top tags, projects |
| `/journal` | The running doc: today's editor on top, the last ~7 days rendered below with lazy-load-on-scroll, autosave, `✳ parse`, and a "finish the day" button |
| `/journal/<YYYY-MM-DD>` | Read-only permalink for a single past day |
| `/capture` | Quick-capture form (type, title, body, tags, project) |
| `/entries` | Searchable / filterable list |
| `/entries/<id>` | View + edit-in-place (title, tags, project, status, body) |
| `/projects`, `/projects/<name>` | Project inventory and per-project dashboards |
| `/tags` | Tag analytics |

## Keyboard shortcuts

| Keys | Action |
|------|--------|
| `g d` | Dashboard |
| `g j` | Journal |
| `g c` | Capture |
| `g e` | Entries |
| `g p` | Projects |
| `/` | Focus search |
| `⌘ / Ctrl + Enter` | Parse (on the journal page) |
| `⌘ / Ctrl + C` | Copy the selection |
| `?` | Help |

## The journal parse pipeline

`✳ parse` on the running doc turns free-form journal writing into structured
braindump entries without leaving the page. In outline:

1. **Flush + queue.** `POST /api/journal/<day>/parse` flushes the editor's
   current buffer to disk, then hands the day to `braindump.core.digest.run_parse`
   as a background task tracked in a single in-memory slot — **only one parse can
   run at a time**; a second `parse` while one is in flight gets `409`.
2. **Two-pass Claude pipeline.** Pass 1 (no tools) groups journal lines into
   per-project sections and proposes entries; Python-side validation never trusts
   the model with the anchoring line indexes. Pass 2 (read-only tools, cwd = the
   project's local checkout) lightly polishes wording when a local directory
   exists. Entries are created through the real `entries.create_entry` path, and
   the journal is annotated with `[→type#id]` marks one section at a time — so a
   crash only risks duplicating whatever section was in flight.
3. **Poll + unlock.** The client polls a status fragment every 2s; the editor is
   locked (read-only) for the duration. When the job finishes the endpoint
   returns HTTP **286** + `HX-Trigger: parse-done`, which stops htmx's polling and
   tells the editor to unlock and refetch the now-annotated body.
4. **Chip links.** `[→type#id]` marks render as clickable `.ref-chip` pills in
   past-day / permalink views.

!!! note "Requires the `claude` CLI"

    If the `claude` CLI isn't on `PATH` (or `BRAINDUMP_CLAUDE_BIN` points
    nowhere), the parse endpoint reports a friendly inline error instead of
    queuing a job. Everything else in the UI works without it.

See the [Journal guide](journal.md) for the day-cutoff behavior, and the
[Architecture reference](../reference/architecture.md) for how the web layer sits
on top of the shared core.
