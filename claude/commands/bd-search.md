---
allowed-tools: ["Bash", "Read"]
description: Search braindump entries
argument-hint: "<query> [type]"
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

2. **Run the search** using the search script or jq directly:

```bash
BD="$HOME/braindump"
QUERY="$ARGUMENTS"

# Search all indexes
for type in todos til thoughts prompts; do
  [ -f "$BD/$type/index.jsonl" ] && \
  jq -c "select(
    (.title | test(\"$QUERY\"; \"i\")) or
    (.summary // \"\" | test(\"$QUERY\"; \"i\")) or
    (.tags // [] | map(test(\"$QUERY\"; \"i\")) | any)
  )" "$BD/$type/index.jsonl" 2>/dev/null
done
```

Or use the search script:
```bash
"$HOME/braindump/scripts/search.sh" "QUERY"
```

3. **Format results** - show matching entries in a readable format:
   - Date, type, title
   - Brief summary
   - File path for reference

If no results found, say so and suggest broadening the search.
