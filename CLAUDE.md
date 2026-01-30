# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Braindump is a portable Claude Code-integrated personal knowledge management system. It captures todos, TILs (Today I Learned), thoughts, and prompts with JSONL indexing for fast search.

## Installation

```bash
./install.sh
```

Installs Claude commands/skills to `~/.claude/` and initializes data directory at `~/braindump/`.

## Architecture

```
braindump/
├── claude/
│   ├── commands/      # Claude Code slash commands (bd-*.md)
│   └── skills/        # Skill definitions with SKILL.md
├── data-template/     # Template copied to ~/braindump/ on install
│   ├── scripts/       # Shell utilities (create-entry.sh, search.sh, list.sh, tags.sh, session-*.sh)
│   └── {type}/        # Type directories with index.jsonl
└── install.sh         # Installer script
```

**Runtime data location:** `~/braindump/`

## Commands

All commands are markdown files in `claude/commands/`:

| Command | Purpose |
|---------|---------|
| `/bd-dump` | Auto-categorizing quick capture |
| `/bd-todo` | Create todo |
| `/bd-til` | Record TIL |
| `/bd-thought` | Capture thought |
| `/bd-prompt` | Store prompt |
| `/bd-search` | Search entries |
| `/bd-list` | List recent entries |
| `/bd-tags` | Tag management and analytics |

## Data Format

**JSONL index** (`index.jsonl` per type):
```json
{"type":"todo","title":"...","summary":"...","tags":[...],"project":"project-name","input":"original input","created_at":"ISO8601","file_path":"YYYY/MM/slug--YYYY-MM-DD-HHmm.md"}
```

**Markdown files** (`~/braindump/{type}/YYYY/MM/slug--timestamp.md`):
```markdown
---
type: todo
title: Title
tags: [tag1, tag2]
project: project-name
created_at: ISO8601
---

# Title

Content...

---

<details>
<summary>Original input</summary>

[Original user input verbatim]

</details>
```

**File naming:** `slugified-title--YYYY-MM-DD-HHmm.md` (double-dash separator for easy title selection)

## Type-Specific Fields

- **todo**: `subtype`, `status` (pending/in-progress/done), `priority`, `due_date`
- **til**: `category`, `source`
- **thought**: `mood`, `related_to`
- **prompt**: `prompt_type`, `model_target`

## Key Conventions

- Commands output only `done: <file_path>` on success
- All timestamps are UTC ISO 8601
- Tags are lowercase with hyphens
- The `input` field in JSONL always stores original user input verbatim
- Indexes are append-only

## Session Tracking

Optional hooks track Claude Code sessions via `SessionStart`/`SessionEnd`. Session data stored in `~/braindump/sessions/started-YYYY-MM-DD.jsonl`.

Scripts: `session-start.sh`, `session-end.sh`, `forgotten-sessions.sh`
