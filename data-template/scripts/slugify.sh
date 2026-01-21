#!/bin/bash
# slugify.sh - Create filename slug from title
# Usage: slugify.sh "My Title Here"
# Output: my-title-here

set -e

TITLE="${1:?Usage: slugify.sh \"Title Here\"}"

echo "$TITLE" | \
  tr '[:upper:]' '[:lower:]' | \
  tr -cs 'a-z0-9' '-' | \
  sed 's/^-//' | \
  sed 's/-$//' | \
  head -c 50 | \
  sed 's/-$//'
