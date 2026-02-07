---
allowed-tools: ["Bash", "Read"]
description: Search braindump entries
argument-hint: "<query> [type] [--open|--done]"
---

# Braindump Search

Search across all braindump entries.

## Input

$ARGUMENTS

## Instructions

1. **Parse the query** - the user may provide:
   - A simple search term: `auth`
   - A type filter: `todo:auth` or `--type=todo auth`
   - Multiple terms: `auth login`
   - Status filter: `--open` (exclude done), `--done` (only done), `--all` (default)

2. **Run the search** using the search script:

```bash
"$HOME/braindump/scripts/search.sh" "QUERY" [TYPE] [--open|--done]
```

The script searches JSONL indexes (title, summary, tags) first, then falls back to full-text search through markdown file content via ag.

3. **Format results** - show matching entries in a readable format:
   - **#id** date [type] title
   - Brief summary
   - Include the ID so users can reference entries (e.g., `/bd-done 42`)

If no results found, say so and suggest broadening the search.
