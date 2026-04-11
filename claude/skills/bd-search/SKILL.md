---
description: Search braindump entries
allowed-tools: Bash, Read
argument-hint: <query...> [type] [--open|--done]
---

# Braindump Search

Search across all braindump entries.

> For data format details, load the `braindump` skill.

## Input

$ARGUMENTS

## Instructions

1. **Parse the query.** The user may provide:
   - A simple search term: `auth`
   - Multiple words: `auth login` (AND-matched across title/summary/tags + body)
   - An exact phrase: `"auth login flow"` (quote for phrase matching)
   - Filters (pass directly to `bd search`): `--type todo`, `--project NAME`, `--tag TAG`, `--status open|done|all`, `--since YYYY-MM-DD`, `--until YYYY-MM-DD`

2. **Run the search:**

   ```bash
   bd search word1 word2 [--type todo] [--project name] [--status open] [--tag foo] --human
   ```

   Drop `--human` if you want JSONL output to parse programmatically. Two-stage strategy: metadata scan first, ripgrep fallback for matches in markdown bodies. The active project filter (set via `bd project focus`) is applied automatically unless `--all` is passed.

3. **Format results** for the user — the `--human` output already shows `#id date [type] title (project)`. Include the ID so the user can reference entries (e.g., `/bd-done 42`).

If no results, say so and suggest broadening the search or clearing the active project filter.
