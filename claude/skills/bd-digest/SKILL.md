---
description: Digest a daily journal into structured entries per project with backref marks
allowed-tools: Bash, Read, Edit
argument-hint: [YYYY-MM-DD]
---

# Braindump Journal Digest

Sweep a day's journal, group lines by their heading/label, turn each unmarked actionable line into a structured entry (todo / til / thought / prompt), then annotate the journal line in place with a backref like `[→todo#42]` so it's clear that line has already been digested.

## Conventions

!`awk '/^---$/{n++;next}n>1' ~/.claude/skills/braindump/SKILL.md`

## Context

<current-project>
!`git rev-parse --show-toplevel 2>/dev/null | xargs basename || basename "$PWD"`
</current-project>

<existing-tags>
!`bd tags stats 2>/dev/null || echo "(no tags yet)"`
</existing-tags>

<existing-projects>
!`bd project list 2>/dev/null || echo "(no projects yet)"`
</existing-projects>

<today>
!`bd journal today 2>/dev/null || echo "(no journal today)"`
</today>

## Input

$ARGUMENTS

## Instructions

### 1. Resolve the date and file path

- If `$ARGUMENTS` is empty, parse the date from `<today>` (the line looks like `day: 2026-04-11 id: 3 words: 72`).
- Otherwise treat `$ARGUMENTS` as a `YYYY-MM-DD` string.
- The journal file lives at `~/braindump/journal/<YYYY>/<MM>/<YYYY-MM-DD>.md`.

### 2. Read the journal file

Use the Read tool on the resolved path. The body sits below the YAML frontmatter (`type: journal`, `date:`, `word_count:`, …).

### 3. Group lines into sections

- A section is introduced by a heading-ish line: a top-level bullet, a markdown heading, or a single-token label like `bd web` or `instrospect`.
- Lines indented under that label belong to the section. Inline notes after the label (`bd web - can the editor ...`) make the label itself the actionable line.

### 3a. Map each section to a project — the section label IS the project

This is the rule that matters most. Get it wrong and entries land in the wrong bucket forever.

1. Slugify the section label (lowercase, hyphens, strip punctuation). `bd web` → `bd-web`, `instrospect` → `instrospect`.
2. Fix obvious typos against `<existing-projects>` only — e.g. `instrospect` → `introspect` *if* `introspect` already exists. Use a tight similarity bar (one or two character edits at most).
3. If the slug (post-typo-correction) matches an existing project exactly → use it.
4. **Otherwise, use the slug as a NEW project name.** `bd` will create it on first use. Do NOT fold the section into `<current-project>` just because there's no existing project with that name — that silently destroys the user's intent.
5. Only fall back to `<current-project>` when there is genuinely no section label (an unstructured journal that's just a flat list of bullets).

When in doubt between "new project" and "fold into existing", **prefer creating a new project**. Stray projects are easy to merge later; misfiled entries are hard to find.

### 4. Decide which lines to digest

For each candidate line:
- **Skip** if the line already contains `[→` anywhere (it's been digested before — idempotent).
- **Skip** empty lines, pure section labels with no content of their own, and meta-lines you wouldn't want as a separate entry.
- For lines with sub-bullets, treat the parent line as the entry and fold the sub-bullets into the body of that entry.

### 5. Classify and create

For each line you decided to digest:

- Pick a **type**: `todo` (actionable / has a verb / question about doing something), `til` (something learned), `thought` (idea / observation / open question), `prompt` (a reusable prompt).
- Infer **title** (≤60 chars), **tags** (1-5, prefer reuse from `<existing-tags>`), and **project** (from step 3).
- Create the entry, passing the raw line as the original input:

  ```bash
  OI=$(mktemp) && cat > "$OI" << 'OI_EOF'
  [The exact original journal line, verbatim]
  OI_EOF

  cat << 'BODY_EOF' | bd create <type> "Your Title" \
    --tag tag1 --tag tag2 \
    --project project-name \
    --summary "one-line summary" \
    --original-input-file "$OI"
  [Lightly cleaned-up body — fix typos, expand context from the line + any sub-bullets, but stay close to what the user actually wrote]
  BODY_EOF

  rm -f "$OI"
  ```

  Add type-specific flags as needed (`--status`, `--subtype`, `--priority`, `--category`, `--source`, `--mood`, `--related-to`, `--prompt-type`, `--model-target`).

### 6. Look up the new entry id and mark the journal line

After each successful `bd create`, fetch the id from the type's index. The type→dir map is `todo→todos`, `til→til`, `thought→thoughts`, `prompt→prompts`:

```bash
NEW_ID=$(tail -1 ~/braindump/<type-dir>/index.jsonl | python3 -c "import sys,json;print(json.loads(sys.stdin.readline())['id'])")
```

Then use the **Edit** tool to append `` [→<type>#<NEW_ID>]`` (a single space, then the bracket-arrow-type-hash-id) to the end of the exact original line in the journal file. Use the journal line verbatim as `old_string` so the match is unique.

### 7. Output

Print a short summary grouped by project, then nothing else:

```
digest 2026-04-11:
  bd web: 1 todo
  introspect: 2 todos, 1 thought
  (2 lines already marked, skipped)
```

If there were no unmarked actionable lines at all, just print:

```
digest 2026-04-11: nothing to do
```
