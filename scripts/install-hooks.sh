#!/usr/bin/env bash
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
git -C "$repo_root" config core.hooksPath hooks
chmod +x "$repo_root/hooks/pre-commit"
echo "Git hooks enabled from hooks/."
