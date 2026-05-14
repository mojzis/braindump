#!/bin/bash
# Braindump Installation Script
# Installs:
#   - the `bd` CLI (Python package) via uv tool install
#   - Claude skills to ~/.claude/skills
#   - data directory layout at ~/braindump/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
BRAINDUMP_DIR="${BRAINDUMP_DIR:-$HOME/braindump}"

echo "Braindump Installer"
echo "==================="
echo ""

# --- 1. Install the bd CLI via uv tool install ----------------------------

if ! command -v uv >/dev/null 2>&1; then
    echo "Error: uv is required. Install it from https://docs.astral.sh/uv/" >&2
    exit 1
fi

echo "Installing bd CLI via uv tool..."
uv tool install --force --reinstall --no-cache "${SCRIPT_DIR}[web]" >/dev/null
echo "  - bd CLI installed (run 'bd --help' to verify)"

# --- 2. Install Claude skills ---------------------------------------------

echo ""
echo "Installing Claude skills to $CLAUDE_DIR/skills..."
mkdir -p "$CLAUDE_DIR/skills"

# Clean up stale commands from previous installations
if [ -d "$CLAUDE_DIR/commands" ]; then
    for cmd in bd-dump bd-todo bd-til bd-thought bd-prompt bd-search bd-list bd-tags bd-done; do
        rm -f "$CLAUDE_DIR/commands/$cmd.md"
    done
fi

if [ -d "$SCRIPT_DIR/claude/skills" ]; then
    cp -r "$SCRIPT_DIR/claude/skills/"* "$CLAUDE_DIR/skills/"
    echo "  - Skills installed"
fi

# --- 3. Seed data directory -----------------------------------------------

echo ""
echo "Initializing data directory at $BRAINDUMP_DIR..."

mkdir -p "$BRAINDUMP_DIR"
for type in todos til thoughts prompts journal; do
    mkdir -p "$BRAINDUMP_DIR/$type"
    [ -f "$BRAINDUMP_DIR/$type/index.jsonl" ] || touch "$BRAINDUMP_DIR/$type/index.jsonl"
done
mkdir -p "$BRAINDUMP_DIR/sessions"

# Session tracking scripts are still plain bash — drop them in ~/braindump/scripts/
mkdir -p "$BRAINDUMP_DIR/scripts"
for s in session-start.sh session-end.sh forgotten-sessions.sh; do
    if [ -f "$SCRIPT_DIR/data-template/scripts/$s" ]; then
        cp "$SCRIPT_DIR/data-template/scripts/$s" "$BRAINDUMP_DIR/scripts/"
        chmod +x "$BRAINDUMP_DIR/scripts/$s"
    fi
done
echo "  - Data directories and session hooks ready"

echo ""
echo "Installation complete!"
echo ""
echo "Try it out:"
echo "  bd --help                    # CLI overview"
echo "  bd list                      # list recent entries"
echo "  bd project list              # show projects"
echo "  bd serve                     # local web UI at http://127.0.0.1:8765/"
echo ""
echo "Claude skills available:"
echo "  /bd-dump /bd-todo /bd-til /bd-thought /bd-prompt"
echo "  /bd-search /bd-list /bd-tags /bd-done"
echo ""
echo "Data stored in: $BRAINDUMP_DIR"
echo ""
echo "========================================"
echo "SESSION TRACKING SETUP (Optional)"
echo "========================================"
echo ""
echo "To enable automatic Claude Code session tracking, add to ~/.claude/settings.json:"
echo ""
echo '{'
echo '  "hooks": {'
echo '    "SessionStart": [{"hooks": [{"type": "command", "command": "'"$BRAINDUMP_DIR"'/scripts/session-start.sh"}]}],'
echo '    "SessionEnd":   [{"hooks": [{"type": "command", "command": "'"$BRAINDUMP_DIR"'/scripts/session-end.sh"}]}]'
echo '  }'
echo '}'
