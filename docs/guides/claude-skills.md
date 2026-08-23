# Claude skills

Braindump ships a set of `/bd-*` **Claude Code slash-skills**. They're thin
wrappers that shell out to the `bd` CLI from inside a Claude session, so what you
see in the web UI is exactly what the skills produce — one code path, three
surfaces.

The installer copies them to `~/.claude/skills/`. Start a fresh Claude Code
session after installing so they're picked up.

## Available skills

| Skill | Purpose |
|-------|---------|
| `/bd-dump <content>` | Quick capture with auto-categorization |
| `/bd-todo <task>` | Create a todo |
| `/bd-til <learning>` | Record a TIL (Today I Learned) |
| `/bd-thought <idea>` | Capture a thought |
| `/bd-prompt <content>` | Store a prompt |
| `/bd-project <name>` | Create a project entry |
| `/bd-search <query>` | Search entries |
| `/bd-list [type] [n]` | List recent entries |
| `/bd-tags [command]` | Tag management and analytics |
| `/bd-done <id or query>` | Mark a todo as done |
| `/bd-digest [date]` | Digest a journal day into structured per-project entries |

## Conventions the creation skills follow

Creation skills load a shared `braindump` skill for conventions and surface both
`<existing-tags>` (via `bd tags stats`) and `<existing-projects>` (via
`bd project list`) so Claude prefers **reuse over drift**.

### Content processing levels

Input is handled at one of three levels, chosen by prefix or context:

| Prefix | Level | Behavior |
|--------|-------|----------|
| `raw:` | Raw | Store verbatim. Title from the first 50 chars. Tags still inferred. |
| *(none)* | Medium | Light formatting and structure. The default. |
| `well:` | Well-done | Full elaboration, including relevant conversation context. |

If input references prior conversation ("that feature", "what we discussed"), a
skill may auto-upgrade to well-done mode; if it's unclear whether the surrounding
context is relevant, it asks.

### Project context

Every non-project entry captures the project it was created in — detected from
the current git repo name (or the working directory name if not a repo), and
overridable. `project` is separate from tags and is a by-name reference to the
title of a first-class `project` entry. Bare names with no entry show up as
"unregistered" until you create a matching project.

Because `project` is its own field, an entry is never tagged with its own
project name — `bd create` and `bd update` strip such a tag. Otherwise project
names pile up in `bd tags stats` and crowd out the tags that say what an entry
is actually *about*. A tag naming a **different** project survives: that's a
cross-reference, not a duplicate.

### Output contract

On success, creation skills output only the line `bd create` printed:

```text
created: #<id> <file_path>
```

The id is deliberately in that one line: it's how you reference the entry from a
later session (`bd show 42`, `bd done 42`), and the skill's output is the only
place it appears in the transcript.

## The digest skill

`/bd-digest [YYYY-MM-DD]` sweeps a day's journal, groups lines by their
heading/label, turns each unmarked actionable line into a structured entry
(todo / til / thought / prompt), then annotates the journal line in place with a
backref like `[→todo#42]`. It's the CLI-session equivalent of the web UI's
`✳ parse` button — see the [parse pipeline](web-ui.md#the-journal-parse-pipeline).
