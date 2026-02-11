#!/bin/bash
# Braindump Installation Script
# Installs skills to ~/.claude/ and data template to ~/braindump/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
BRAINDUMP_DIR="$HOME/braindump"

echo "Braindump Installer"
echo "==================="
echo ""

# Install Claude skills
echo "Installing Claude skills to $CLAUDE_DIR..."

mkdir -p "$CLAUDE_DIR/skills"

# Clean up stale commands from previous installations
if [ -d "$CLAUDE_DIR/commands" ]; then
    for cmd in bd-dump bd-todo bd-til bd-thought bd-prompt bd-search bd-list bd-tags bd-done; do
        rm -f "$CLAUDE_DIR/commands/$cmd.md"
    done
    echo "  - Cleaned up stale commands"
fi

# Copy skills
if [ -d "$SCRIPT_DIR/claude/skills" ]; then
    cp -r "$SCRIPT_DIR/claude/skills/"* "$CLAUDE_DIR/skills/"
    echo "  - Skills installed"
fi

# Initialize data directory
echo ""
echo "Initializing data directory at $BRAINDUMP_DIR..."

if [ -d "$BRAINDUMP_DIR" ]; then
    echo "  - Data directory already exists, preserving existing data"
    # Always update scripts (user data is in type directories, not scripts)
    if [ -d "$SCRIPT_DIR/data-template/scripts" ]; then
        mkdir -p "$BRAINDUMP_DIR/scripts"
        cp "$SCRIPT_DIR/data-template/scripts/"* "$BRAINDUMP_DIR/scripts/" 2>/dev/null || true
        chmod +x "$BRAINDUMP_DIR/scripts/"*.sh 2>/dev/null || true
        echo "  - Scripts updated"
    fi
    # Create any missing type directories
    for type in todos til thoughts prompts; do
        mkdir -p "$BRAINDUMP_DIR/$type"
        [ -f "$BRAINDUMP_DIR/$type/index.jsonl" ] || touch "$BRAINDUMP_DIR/$type/index.jsonl"
    done
    # Create sessions directory
    mkdir -p "$BRAINDUMP_DIR/sessions"
else
    cp -r "$SCRIPT_DIR/data-template" "$BRAINDUMP_DIR"
    chmod +x "$BRAINDUMP_DIR/scripts/"*.sh
    echo "  - Data directory created"
fi

echo ""
echo "Installation complete!"
echo ""
echo "Available skills:"
echo "  /bd-dump <content>    - Quick capture with auto-categorization"
echo "  /bd-todo <task>       - Create a todo"
echo "  /bd-til <learning>    - Record something learned"
echo "  /bd-thought <idea>    - Capture a thought"
echo "  /bd-prompt <content>  - Store a prompt"
echo "  /bd-search <query>    - Search entries"
echo "  /bd-list [type] [n]   - List recent entries"
echo "  /bd-tags [command]    - Tag management and analytics"
echo "  /bd-done <id|query>   - Mark a todo as done"
echo ""
echo "Session tracking utilities:"
echo "  ~/braindump/scripts/forgotten-sessions.sh [days]  - Find unfinished sessions"
echo ""
echo "Data stored in: $BRAINDUMP_DIR"
echo ""
echo "========================================"
echo "SESSION TRACKING SETUP (Optional)"
echo "========================================"
echo ""
echo "To enable automatic session tracking, add the following to ~/.claude/settings.json:"
echo ""
echo '{'
echo '  "hooks": {'
echo '    "SessionStart": [{"hooks": [{"type": "command", "command": "'"$BRAINDUMP_DIR"'/scripts/session-start.sh"}]}],'
echo '    "SessionEnd": [{"hooks": [{"type": "command", "command": "'"$BRAINDUMP_DIR"'/scripts/session-end.sh"}]}]'
echo '  }'
echo '}'
echo ""
echo "This tracks when you start/stop Claude Code sessions."
echo "Run forgotten-sessions.sh to find sessions you may have abandoned."
