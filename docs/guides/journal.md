# Journal

Braindump keeps a **daily journal** — one markdown file per day at
`journal/YYYY/MM/YYYY-MM-DD.md`. It's the running doc you dump into during the
day; the [parse pipeline](web-ui.md#the-journal-parse-pipeline) can later turn
those lines into structured entries.

## From the CLI

```bash
bd journal today                 # show today's journal state
echo "shipped the parse pipeline" | bd journal append
bd journal close                 # seal today, open tomorrow
bd journal show 2026-01-21       # render a specific past day
```

## From the web UI

The `/journal` page is the primary journaling surface: today's editor on top
with autosave, the last ~7 days rendered below (older days lazy-load as you
scroll), an `✳ parse` button, and a **"finish the day"** button that seals today
and opens tomorrow immediately.

## The day cutoff

Journaling honors a configurable **daily cutoff hour** (default `04:00` local).
Writes *before* the cutoff still go to the **previous** day's file — so
"finish the day when I go to bed" just works, even when "bed" is 1am.

Override the cutoff with an environment variable:

```bash
export BRAINDUMP_DAY_CUTOFF=03:00
```

The web UI's "finish the day" button is the explicit escape hatch: it seals
today and opens tomorrow right now, regardless of the clock.

## How entries link back

When the parse pipeline creates a structured entry from a journal line, it
annotates that line in place with a backref mark like `[→todo#42]`. In past-day
and permalink views those marks render as clickable `.ref-chip` pills that jump
to the created entry, so it's always clear which lines have already been
digested.
