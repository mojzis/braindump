#!/bin/bash
# tags.sh - Tag management and analytics for braindump
# Usage: tags.sh <command> [args]
# Commands:
#   stats          - Show tag frequency across all entries
#   similar        - Find potential duplicate tags
#   show <tag>     - List entries with a specific tag

set -e

BD="${BRAINDUMP_DIR:-$HOME/braindump}"
COMMAND="${1:-stats}"
ARG="$2"

# Collect all tags from all indexes
get_all_tags() {
  for t in todos til thoughts prompts; do
    [ -f "$BD/$t/index.jsonl" ] && cat "$BD/$t/index.jsonl"
  done | jq -r '.tags // [] | .[]' 2>/dev/null
}

case "$COMMAND" in
  stats)
    echo "Tag frequency:"
    echo "=============="
    get_all_tags | sort | uniq -c | sort -rn
    ;;

  similar)
    echo "Potential duplicate tags:"
    echo "========================="
    # Find tags that differ only by suffix like s, ing, ed, or similar prefixes
    get_all_tags | sort -u | while read -r tag; do
      # Check for common variations
      base="${tag%s}"  # remove trailing s
      [ "$base" != "$tag" ] && get_all_tags | sort -u | grep -x "$base" && echo "  $tag ~ $base"

      base="${tag%ing}"  # remove trailing ing
      [ "$base" != "$tag" ] && get_all_tags | sort -u | grep -x "$base" && echo "  $tag ~ $base"

      base="${tag%ed}"  # remove trailing ed
      [ "$base" != "$tag" ] && get_all_tags | sort -u | grep -x "$base" && echo "  $tag ~ $base"

      base="${tag%tion}"  # remove trailing tion
      [ "$base" != "$tag" ] && get_all_tags | sort -u | grep -x "$base" && echo "  $tag ~ $base"
    done 2>/dev/null | sort -u

    # Also check for hyphen vs no-hyphen
    echo ""
    echo "Hyphen variations:"
    get_all_tags | sort -u | while read -r tag; do
      if [[ "$tag" == *-* ]]; then
        nohyphen="${tag//-/}"
        get_all_tags | sort -u | grep -x "$nohyphen" && echo "  $tag ~ $nohyphen"
      fi
    done 2>/dev/null | sort -u
    ;;

  show)
    if [ -z "$ARG" ]; then
      echo "Usage: tags.sh show <tag>"
      exit 1
    fi
    echo "Entries tagged '$ARG':"
    echo "======================"
    for t in todos til thoughts prompts; do
      [ -f "$BD/$t/index.jsonl" ] || continue
      jq -r "select(.tags // [] | map(. == \"$ARG\") | any) | \"[\(.type)] \(.title) - $t/\(.file_path)\"" "$BD/$t/index.jsonl" 2>/dev/null
    done
    ;;

  *)
    echo "Usage: tags.sh <command> [args]"
    echo ""
    echo "Commands:"
    echo "  stats          - Show tag frequency"
    echo "  similar        - Find potential duplicate tags"
    echo "  show <tag>     - List entries with a specific tag"
    exit 1
    ;;
esac
