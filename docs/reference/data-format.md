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

## Planning entries and imported pitches

Initiatives live in initiatives/ and use status active or done plus
project_ids, a list of numeric IDs that must point to project entries. Pitches
live in pitches/ and use status active or done, project_ids, initiative_ids,
and source_path for an imported source's absolute resolved path. Todos may
carry one initiative_id and one pitch_id. Relations are IDs, not titles or
tags, so renames do not break them.

Pitch import reads optional source frontmatter. The source title field wins;
otherwise the first level-one heading wins, then the filename stem. The
generated entry owns the title heading, while the rest of the body is retained
verbatim. Meaningful fields (title, summary, tags, status, project_ids, and
initiative_ids) are preserved; command-line relation IDs override source
values. Source identity fields and timestamps are generated locally.

The import workflow is explicit and bounded:

    bd pitch import selected/pitch.md --dry-run
    bd pitch import selected/pitch.md --project-id 7 --initiative-id 12
    bd pitch remove-source selected/pitch.md --confirm-source-removal

There is no directory scan, relationship inference, or implicit source
deletion. Verification compares the persisted body, title, frontmatter, and
source_path before a requested removal.

QA receipts on todos contain qa_result (pass or fail), UTC qa_verified_at, and
optional qa_run_ref. pass transitions in-qa to done; fail transitions it to
in-progress. Detailed run history stays outside braindump.

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
