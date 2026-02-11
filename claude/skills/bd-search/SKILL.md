---
description: Search braindump entries
allowed-tools: ["Bash", "Read"]
argument-hint: "<query...> [type] [--open|--done]"
---

# Braindump Search

Search across all braindump entries.

> For data format details, load the `braindump` skill.

## Input

$ARGUMENTS

## Instructions

1. **Parse the query** - the user may provide:
   - A simple search term: `auth`
   - A type filter: `auth todo` (known types: todo, til, thought, prompt)
   - Multiple words: `auth login` — AND-matched (all words must appear)
   - Exact phrase: `"auth login flow"` — quoted for phrase matching
   - Status filter: `--open` (exclude done), `--done` (only done), `--all` (default)

2. **Run the search** using the search script:

```bash
# Single word
"$HOME/braindump/scripts/search.sh" "QUERY" [TYPE] [--open|--done]

# Multiword AND search — pass each word as a separate argument
"$HOME/braindump/scripts/search.sh" word1 word2 [TYPE] [--open|--done]

# Exact phrase — pass as a single quoted argument
"$HOME/braindump/scripts/search.sh" "exact phrase" [TYPE] [--open|--done]
```

The script searches JSONL indexes (title, summary, tags) first, then falls back to full-text search through markdown file content via ag.

3. **Format results** - show matching entries in a readable format:
   - **#id** date [type] title
   - Brief summary
   - Include the ID so users can reference entries (e.g., `/bd-done 42`)

If no results found, say so and suggest broadening the search.
