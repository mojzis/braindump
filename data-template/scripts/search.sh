#!/bin/bash
# search.sh - Search braindump entries using jq + full-text ag fallback
# Usage: search.sh <query...> [type] [--open|--done|--all]
# Examples:
#   search.sh auth              - search all types, all statuses
#   search.sh auth todo         - search only todos
#   search.sh auth --open       - search all types, exclude done
#   search.sh auth todo --done  - search todos, only done items
#   search.sh "auth system"     - exact phrase match
#   search.sh deploy k8s        - AND match: entries with both words
#   search.sh deploy k8s todo   - AND match in todos only
#
# Multiple unquoted words are AND-matched (all must appear in the entry).
# Quote words for exact phrase matching.
#
# Searches JSONL indexes first (title, summary, tags), then falls back
# to ag (silver searcher) through markdown file content for matches missed by metadata.

set -e

BD="${BRAINDUMP_DIR:-$HOME/braindump}"

# Normalize type aliases to directory names
normalize_type() {
  case "$1" in
    todo|todos) echo "todos" ;;
    thought|thoughts) echo "thoughts" ;;
    til) echo "til" ;;
    prompt|prompts) echo "prompts" ;;
    *) echo "" ;;
  esac
}

# Parse arguments: flags (--open/--done/--all), known types, and query words
QUERY_WORDS=()
TYPE=""
STATUS_FILTER=""
FIRST_POSITIONAL=true

for arg in "$@"; do
  case "$arg" in
    --open|--pending) STATUS_FILTER="open" ;;
    --done) STATUS_FILTER="done" ;;
    --all) STATUS_FILTER="" ;;
    *)
      if $FIRST_POSITIONAL; then
        # First positional arg is always a query word
        QUERY_WORDS+=("$arg")
        FIRST_POSITIONAL=false
      else
        normalized=$(normalize_type "$arg")
        if [ -n "$normalized" ] && [ -z "$TYPE" ]; then
          TYPE="$normalized"
        else
          QUERY_WORDS+=("$arg")
        fi
      fi
      ;;
  esac
done

[ ${#QUERY_WORDS[@]} -eq 0 ] && { echo "Usage: search.sh <query...> [type] [--open|--done|--all]" >&2; exit 1; }

# Build jq status filter clause
case "$STATUS_FILTER" in
  open) STATUS_JQ=' and ((.status // "") | test("^done$") | not)' ;;
  done) STATUS_JQ=' and (.status // "") == "done"' ;;
  *)    STATUS_JQ='' ;;
esac

# Build jq query filter - AND across all query words
# Each word must match somewhere in title, summary, or tags
build_jq_query() {
  local parts=()
  for word in "${QUERY_WORDS[@]}"; do
    local escaped="${word//\"/\\\"}"
    parts+=("((.title | test(\"$escaped\"; \"i\")) or (.summary // \"\" | test(\"$escaped\"; \"i\")) or (.tags // [] | map(test(\"$escaped\"; \"i\")) | any))")
  done
  local IFS=" and "
  echo "${parts[*]}"
}

JQ_QUERY=$(build_jq_query)

# Temp file to track file_paths already found via index search
FOUND_FILES=$(mktemp)
trap "rm -f $FOUND_FILES" EXIT

type_label() {
  case "$1" in
    todos) echo "todo" ;;
    thoughts) echo "thought" ;;
    *) echo "$1" ;;
  esac
}

search_index() {
  local index="$1"
  [ -f "$index" ] || return 0
  jq -c "select($JQ_QUERY $STATUS_JQ)" "$index" 2>/dev/null | while IFS= read -r line; do
    echo "$line"
    echo "$line" | jq -r '.file_path // empty' >> "$FOUND_FILES"
  done
}

search_fulltext() {
  local dir="$1"
  local type_dir="$2"
  local type_name
  type_name=$(type_label "$type_dir")
  [ -d "$dir" ] || return 0

  # Search for first word with ag, then filter by remaining words (AND)
  local files
  files=$(ag -il --md "${QUERY_WORDS[0]}" "$dir" 2>/dev/null) || return 0

  local i
  for ((i=1; i<${#QUERY_WORDS[@]}; i++)); do
    files=$(echo "$files" | xargs grep -li "${QUERY_WORDS[$i]}" 2>/dev/null) || return 0
  done

  echo "$files" | while IFS= read -r file; do
    [ -z "$file" ] && continue
    # Get relative path for dedup (strip BD/type_dir/ prefix -> YYYY/MM/slug.md)
    local rel_path="${file#$BD/$type_dir/}"
    # Skip if already found in index search
    if grep -qF "$rel_path" "$FOUND_FILES" 2>/dev/null; then
      continue
    fi
    # Extract basic info from frontmatter
    local title created fstatus
    title=$(sed -n 's/^title: *//p' "$file" | head -1)
    created=$(sed -n 's/^created_at: *//p' "$file" | head -1)
    fstatus=$(sed -n 's/^status: *//p' "$file" | head -1)
    # Apply status filter to fulltext matches too
    case "$STATUS_FILTER" in
      open) [ "$fstatus" = "done" ] && continue ;;
      done) [ "$fstatus" != "done" ] && continue ;;
    esac
    # Output as JSON for consistent format
    jq -n -c \
      --arg type "$type_name" \
      --arg title "${title:-Untitled}" \
      --arg fp "$rel_path" \
      --arg created "${created:-}" \
      --arg st "${fstatus:-}" \
      '{type: $type, title: $title, file_path: $fp, created_at: $created, summary: "(matched in content)", _source: "fulltext"} + (if $st != "" then {status: $st} else {} end)'
  done
}

if [ -n "$TYPE" ]; then
  search_index "$BD/$TYPE/index.jsonl"
  search_fulltext "$BD/$TYPE" "$TYPE"
else
  for t in todos til thoughts prompts; do
    search_index "$BD/$t/index.jsonl"
  done
  for t in todos til thoughts prompts; do
    search_fulltext "$BD/$t" "$t"
  done
fi
