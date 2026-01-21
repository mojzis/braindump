# Braindump

A portable Claude Code-integrated system for capturing todos, TILs, thoughts, and prompts with JSONL indexing for fast search.

## Installation

```bash
# Clone/download the repo, then run:
./install.sh
```

This will:
1. Copy commands to `~/.claude/commands/`
2. Copy skills to `~/.claude/skills/`
3. Initialize `~/braindump/` with empty indexes and scripts

### Manual Installation

```bash
# Copy commands and skills to ~/.claude/
cp -r claude/* ~/.claude/

# Initialize data directory
cp -r data-template ~/braindump
chmod +x ~/braindump/scripts/*.sh
```

## Usage

Start a new Claude Code session after installation. The following commands will be available:

| Command | Purpose |
|---------|---------|
| `/bd-dump <content>` | Quick capture with auto-categorization |
| `/bd-todo <task>` | Create a todo |
| `/bd-til <learning>` | Record a TIL (Today I Learned) |
| `/bd-thought <idea>` | Capture a thought |
| `/bd-prompt <content>` | Store a prompt |
| `/bd-search <query>` | Search entries |
| `/bd-list [type] [n]` | List recent entries |

### Examples

```bash
# Quick dump - Claude auto-categorizes
/bd-dump "Need to fix the auth bug in login.ts"

# Explicit todo
/bd-todo "Implement user search --priority=high"

# Record something learned
/bd-til "jq -c outputs compact JSON, one object per line"

# Capture a thought
/bd-thought "What if we used SQLite for the cache instead?"

# Store a prompt
/bd-prompt "You are a helpful assistant that..."

# Search
/bd-search auth

# List recent
/bd-list           # all types, last 10
/bd-list todo      # todos only
/bd-list til 5     # last 5 TILs
```

## Data Structure

```
~/braindump/
├── todos/
│   ├── index.jsonl
│   └── 2026/01/fix-auth-bug--2026-01-21-1430.md
├── til/
│   ├── index.jsonl
│   └── 2026/01/jq-compact-output--2026-01-21-1435.md
├── thoughts/
│   └── index.jsonl
├── prompts/
│   └── index.jsonl
└── scripts/
    ├── search.sh
    ├── slugify.sh
    └── list.sh
```

### JSONL Index Format

Each `index.jsonl` contains one JSON object per line:

```json
{"type":"todo","title":"Fix auth bug","summary":"Fix login authentication","tags":["auth","bug"],"status":"pending","priority":"high","created_at":"2026-01-21T14:30:00Z","file_path":"2026/01/fix-auth-bug--2026-01-21-1430.md"}
```

### Markdown File Format

```markdown
---
type: todo
title: Fix auth bug
tags: [auth, bug]
status: pending
priority: high
created_at: 2026-01-21T14:30:00Z
---

# Fix auth bug

Need to fix the authentication bug in login.ts...
```

## File Naming

Files use the format: `slugified-title--YYYY-MM-DD-HHmm.md`

- Title comes first for easy scanning
- `--` separator allows double-click to select just the title
- Timestamp ensures uniqueness

## Shell Scripts

The scripts in `~/braindump/scripts/` can be used directly:

```bash
# Search
~/braindump/scripts/search.sh "auth"

# List recent
~/braindump/scripts/list.sh todo 5

# Slugify a title
~/braindump/scripts/slugify.sh "My Title Here"  # outputs: my-title-here
```

## Type-specific Fields

- **todo**: `subtype` (code/think/read/write/call/general), `status`, `priority`, `due_date`
- **til**: `category` (programming/tools/concepts/debugging/general), `source`
- **thought**: `mood`, `related_to`
- **prompt**: `prompt_type` (system/user/template/example), `model_target`

## Design Decisions

- **Portable**: Just copy files to install, no package manager needed
- **Visible data**: `~/braindump/` is easy to browse and backup
- **No git tracking**: Keeps it simple, add your own if desired
- **JSONL indexes**: Fast search with jq, easy to parse
- **Haiku for categorization**: Fast, cheap auto-categorization
