---
description: Create a project entry
allowed-tools: Bash, Write, Read
argument-hint: <name or description>
---

# Braindump Project

## Conventions

!`awk '/^---$/{n++;next}n>1' ~/.claude/skills/braindump/SKILL.md`

## Context

<current-dir>
!`pwd`
</current-dir>

<current-repo>
!`git rev-parse --show-toplevel 2>/dev/null || true`
</current-repo>

<existing-tags>
!`bd tags stats 2>/dev/null || echo "(no tags yet)"`
</existing-tags>

<existing-projects>
!`bd project list 2>/dev/null || echo "(no projects yet)"`
</existing-projects>

## Input

$ARGUMENTS

## Instructions

1. **Process the input.** A project entry describes a first-class project: its
   name (becomes the title), a short description, an initial state, and
   optionally a local directory and tech stack. Do **not** introspect package
   files (`pyproject.toml`, `package.json`, etc.) — take tech stack only from
   what the user said.

2. **Infer metadata:**
   - `title`: the project name (short, lowercase with hyphens preferred, e.g.
     `braindump`, `my-app`). **Reject `(none)`** — it is a reserved sentinel
     and `bd create project` will refuse it.
   - `description`: one-line summary (< 100 chars). Falls back to the user's
     own phrasing if they already wrote one.
   - `state`: default `active`. Use `paused` or `archived` only if the user
     explicitly said so.
   - `local_dir`: if `<current-repo>` is non-empty and the project title
     clearly matches the current repo, use the repo root path. Otherwise, if
     `<current-dir>` is under `~/git/` and matches, use that. Otherwise leave
     it unset.
   - `tech_stack`: zero or more tech names the user mentioned (e.g. `python`,
     `fastapi`, `htmx`). One `--tech` flag per item. Do **not** guess.
   - `tags`: 1-3 relevant tags from `<existing-tags>` (prefer reuse). Tags on
     a project entry are metadata about the project itself (e.g. `web`,
     `tool`), not replacements for the fields above.
   - **Never pass `--project`.** A project entry does not belong to itself;
     `bd create project` forces the `project` field to `None`.

3. **Create entry via the bd CLI.** Body goes through stdin; long original
   input goes through a temp file:

   ```bash
   OI=$(mktemp) && cat > "$OI" << 'OI_EOF'
   [Original user input verbatim]
   OI_EOF

   cat << 'BODY_EOF' | bd create project "project-name" \
     --description "one-line description" \
     --state active \
     --local-dir "/home/you/git/project-name" \
     --tech python --tech fastapi \
     --tag web \
     --summary "one-line summary" \
     --original-input-file "$OI"
   [Authored content based on doneness level]
   BODY_EOF

   rm -f "$OI"
   ```

   Omit `--local-dir` / `--tech` / `--tag` / `--description` entirely when
   they're unknown. Repeat `--tech` once per tech name — it is **not**
   comma-separated. `--state` must be one of `active`, `paused`, `archived`.

## Output

`done: <file_path>` (the path printed by `bd create`)
