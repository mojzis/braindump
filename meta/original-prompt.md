# Braindump - Personal Knowledge Management System

A portable Claude Code-integrated system for capturing todos, TILs, thoughts, and prompts with JSONL indexing for fast search.

**Decisions:**
- Portable repo structure (manually copy to `~/.claude/` and `~/braindump/`)
- Data location: `~/braindump/` (visible, easy to browse)
- No git tracking for data (keep it simple)
- Haiku in commands for auto-categorization

## Repo Structure (`/home/exedev/git/braindump/`)

```
braindump/
├── claude/                    # Copy contents to ~/.claude/
│   ├── commands/
│   │   ├── bd-dump.md         # Quick capture (auto-categorize)
│   │   ├── bd-todo.md         # Create todo
│   │   ├── bd-til.md          # Create TIL
│   │   ├── bd-thought.md      # Capture thought
│   │   ├── bd-prompt.md       # Store prompt
│   │   ├── bd-search.md       # Search entries
│   │   └── bd-list.md         # List recent
│   └── skills/
│       └── braindump/
│           └── SKILL.md       # System knowledge + rules
├── data-template/             # Copy to ~/braindump/ on first use
│   ├── todos/
│   │   └── index.jsonl        # + 2026/01/fix-auth-bug--2026-01-21-1430.md
│   ├── til/
│   │   └── index.jsonl
│   ├── thoughts/
│   │   └── index.jsonl
│   ├── prompts/
│   │   └── index.jsonl
│   └── scripts/
│       ├── search.sh
│       ├── slugify.sh
│       └── list.sh
├── meta/                      # Prompts and docs about braindump itself
│   └── original-prompt.md     # The prompt that created this system
├── install.sh                 # Installation helper
└── README.md                  # Usage instructions
```

## Installation (Manual)

```bash
# 1. Copy commands and skills to ~/.claude/
cp -r braindump/claude/* ~/.claude/

# 2. Initialize data directory
cp -r braindump/data-template ~/braindump

# Or use the install script:
./install.sh
```

## JSONL Index Schema

Each `index.jsonl` line:
```json
{
  "type": "todo",
  "subtype": "code",
  "title": "Implement search feature",
  "summary": "Add jq-based search across indexes",
  "tags": ["search", "jq"],
  "status": "pending",
  "priority": "medium",
  "created_at": "2026-01-21T14:30:00Z",
  "file_path": "2026/01/implement-search-feature--2026-01-21-1430.md"
}
```

**Filename format:** `slugified-title--YYYY-MM-DD-HHmm.md`
- Title first for easy scanning
- `--` separator (not `_`) so double-click selects just the title
- Date + time at end ensures uniqueness
- Slugified title (lowercase, hyphens, max 50 chars)
- Example: `fix-auth-bug--2026-01-21-1430.md`

### Type-specific fields:
- **todo**: `subtype` (code/think/read/write/call/general), `status`, `priority`, `due_date`
- **til**: `category` (programming/tools/concepts/debugging/general), `source`
- **thought**: `mood` (optional), `related_to` (optional)
- **prompt**: `prompt_type` (system/user/template/example), `model_target`

## Markdown File Format

```markdown
---
type: todo
title: Implement search feature
tags: [search, jq]
created_at: 2026-01-21T14:30:00Z
---

# Implement search feature

Original content here...
```

## Commands

| Command | Purpose | Model |
|---------|---------|-------|
| `/bd-dump <content>` | Quick capture with auto-categorization | haiku |
| `/bd-todo <task>` | Create todo with optional flags | haiku |
| `/bd-til <learning>` | Record TIL entry | haiku |
| `/bd-thought <idea>` | Capture unstructured thought | haiku |
| `/bd-prompt <content>` | Store a prompt | haiku |
| `/bd-search <query>` | Search via jq | default |
| `/bd-list [type]` | List recent (calls list.sh) | default |

## Auto-categorization Flow

1. User runs `/bd-dump "some content"`
2. Haiku analyzes content to determine type
3. Generates: id, title, summary, tags
4. Creates MD file in `~/braindump/{type}/YYYY/MM/`
5. Appends entry to `index.jsonl`
6. Confirms to user with categorization result

## Shell Scripts

### `search.sh` - jq-based search
```bash
jq -c 'select(
  (.title | test("QUERY"; "i")) or
  (.tags | map(test("QUERY"; "i")) | any)
)' ~/braindump/*/index.jsonl
```

### `slugify.sh` - Create filename slug from title
```bash
# Usage: slugify.sh "My Title Here"
# Output: my-title-here
echo "$1" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | head -c 50 | sed 's/-$//'
```

### `list.sh` - List recent entries (token-efficient)
```bash
#!/bin/bash
# Usage: list.sh [type] [limit]
# list.sh           - all types, last 10
# list.sh todo      - todos only, last 10
# list.sh til 5     - tils, last 5

TYPE="${1:-all}"
LIMIT="${2:-10}"
BD="${BRAINDUMP_DIR:-$HOME/braindump}"

list_type() {
  local t="$1"
  [ -f "$BD/$t/index.jsonl" ] && tail -n "$LIMIT" "$BD/$t/index.jsonl" | \
    jq -r '"\(.created_at | .[0:10]) [\(.type)] \(.title)"'
}

if [ "$TYPE" = "all" ]; then
  for t in todos til thoughts prompts; do list_type "$t"; done | sort -r | head -n "$LIMIT"
else
  list_type "$TYPE"
fi
```
