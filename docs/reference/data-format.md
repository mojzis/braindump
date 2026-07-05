# Data format

Everything braindump stores is **plain markdown on disk**, with per-type JSONL
indexes acting as a fast, rebuildable cache — not the source of truth.

## On-disk layout

```text
~/braindump/
├── todos/      index.jsonl + YYYY/MM/<slug>--<timestamp>.md
├── til/        …
├── thoughts/   …
├── prompts/    …
├── projects/   …
├── journal/    index.jsonl + YYYY/MM/<YYYY-MM-DD>.md   (one file per day)
├── sessions/   Claude Code session hooks output
├── scripts/    session hooks only
├── .next_id    shared ID counter (flock-guarded)
├── .state.json active project etc.
└── .trash/     soft-deleted entries
```

Override the base directory with `BRAINDUMP_DIR`.

## JSONL index

Each `~/braindump/<type_dir>/index.jsonl` line is one entry:

```json
{"id":42,"type":"todo","title":"Fix auth bug","summary":"...","tags":["auth","bug"],"project":"braindump","status":"pending","input":"...","created_at":"2026-04-11T14:15:02Z","file_path":"2026/04/fix-auth-bug--2026-04-11-1415.md"}
```

- The `input` field always stores the **original user input verbatim**.
- Index mutations rewrite the whole file **atomically** under `fcntl.flock`.

## Markdown file

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

## File naming

`slugified-title--YYYY-MM-DD-HHmm.md`

The **double-dash** separator (not `_`) means a double-click selects just the
title. Journal files are the exception: one file per day at
`journal/YYYY/MM/YYYY-MM-DD.md`.

## Type-specific fields

| Type | Fields |
|------|--------|
| **todo** | `subtype`, `status` (pending / in-progress / done), `priority`, `due_date` |
| **til** | `category`, `source` |
| **thought** | `mood`, `related_to` |
| **prompt** | `prompt_type`, `model_target` |
| **journal** | `date` (YYYY-MM-DD), `word_count` |
| **project** | `description`, `state` (active / paused / archived), `area` (free-form grouping, reused like a tag — e.g. `dev-tools`, `cad-3d`), `local_dir`, `tech_stack` |

## Key conventions

- All timestamps are **UTC ISO 8601**.
- Tags are **lowercase with hyphens**.
- A `project` entry's own `project` field is always `null` — a project cannot
  belong to itself.
- Removing an entry **soft-deletes** it into `~/braindump/.trash/`; nothing is
  lost accidentally.
- The active-project focus lives in `~/braindump/.state.json` and is applied
  automatically until cleared with `bd project focus --clear`.

## Validating the indexes

The JSONL indexes are a cache. If they ever drift from the markdown on disk:

```bash
bd doctor
```
