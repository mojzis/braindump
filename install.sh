#!/bin/bash
# Braindump Installation Script
# Installs commands/skills to ~/.claude/ and data template to ~/braindump/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
BRAINDUMP_DIR="$HOME/braindump"

echo "Braindump Installer"
echo "==================="
echo ""

# Install Claude commands and skills
echo "Installing Claude commands and skills to $CLAUDE_DIR..."

mkdir -p "$CLAUDE_DIR/commands"
mkdir -p "$CLAUDE_DIR/skills"

# Copy commands
if [ -d "$SCRIPT_DIR/claude/commands" ]; then
    cp -r "$SCRIPT_DIR/claude/commands/"* "$CLAUDE_DIR/commands/"
    echo "  - Commands installed"
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
    # Only copy scripts if they don't exist or are older
    if [ -d "$SCRIPT_DIR/data-template/scripts" ]; then
        mkdir -p "$BRAINDUMP_DIR/scripts"
        cp -n "$SCRIPT_DIR/data-template/scripts/"* "$BRAINDUMP_DIR/scripts/" 2>/dev/null || true
        chmod +x "$BRAINDUMP_DIR/scripts/"*.sh 2>/dev/null || true
        echo "  - Scripts updated"
    fi
    # Create any missing type directories
    for type in todos til thoughts prompts; do
        mkdir -p "$BRAINDUMP_DIR/$type"
        [ -f "$BRAINDUMP_DIR/$type/index.jsonl" ] || touch "$BRAINDUMP_DIR/$type/index.jsonl"
    done
else
    cp -r "$SCRIPT_DIR/data-template" "$BRAINDUMP_DIR"
    chmod +x "$BRAINDUMP_DIR/scripts/"*.sh
    echo "  - Data directory created"
fi

echo ""
echo "Installation complete!"
echo ""
echo "Available commands:"
echo "  /bd-dump <content>    - Quick capture with auto-categorization"
echo "  /bd-todo <task>       - Create a todo"
echo "  /bd-til <learning>    - Record something learned"
echo "  /bd-thought <idea>    - Capture a thought"
echo "  /bd-prompt <content>  - Store a prompt"
echo "  /bd-search <query>    - Search entries"
echo "  /bd-list [type] [n]   - List recent entries"
echo ""
echo "Data stored in: $BRAINDUMP_DIR"
