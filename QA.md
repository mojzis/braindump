# Handoff QA

Run this journey from the final tree. It uses a disposable store and never
reads or writes `~/braindump`.

```bash
set -eu
qa_root="$(mktemp -d)"
trap 'rm -rf "$qa_root"' EXIT
export BRAINDUMP_DIR="$qa_root/braindump"

handoff_line="$(printf 'Resume the auth work.\n' | uv run bd create handoff 'Auth session' --branch feature/auth)"
handoff_id="${handoff_line#*#}"
handoff_id="${handoff_id%% *}"
test -n "$handoff_id"

uv run bd list handoff --branch feature/auth --json | tee "$qa_root/list.jsonl"
test "$(wc -l < "$qa_root/list.jsonl" | tr -d ' ')" = 1
uv run bd search --type handoff --branch feature/auth --json | grep -q 'Auth session'
uv run bd show --json "$handoff_id" | grep -q 'Resume the auth work.'
uv run bd update "$handoff_id" --branch release/auth
uv run bd show "$handoff_id" | grep -q 'branch release/auth'

uv run python -c 'import asyncio; from braindump.mcp import mcp; print(asyncio.run(mcp.call_tool("create", {"entry_type": "handoff", "title": "MCP handoff", "body": "MCP body", "branch": "release/auth"})))'
```

Expected evidence: a `handoffs/index.jsonl` record, authored bodies in their
Markdown files, exact branch filtering, CLI show/update output, and a public
MCP create call using the same isolated store. Automated generic web
list/view/edit coverage is included here:

```bash
uv run pytest -q tests/test_entries.py tests/test_query.py tests/test_cli.py \
  tests/test_service.py tests/test_mcp.py tests/test_web_graph.py
```
