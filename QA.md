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
uv run bd show "$handoff_id" | grep -q 'branch: release/auth'

printf 'Alpha project\n' | uv run bd create project Alpha >/dev/null
printf 'Beta project\n' | uv run bd create project Beta >/dev/null
printf 'Alpha feature body\n' | uv run bd create handoff 'Alpha feature' --project Alpha --branch feature/auth >/dev/null
printf 'Alpha release body\n' | uv run bd create handoff 'Alpha release' --project Alpha --branch release/auth >/dev/null
printf 'Beta feature body\n' | uv run bd create handoff 'Beta feature' --project Beta --branch feature/auth >/dev/null
printf 'Beta release body\n' | uv run bd create handoff 'Beta release' --project Beta --branch release/auth >/dev/null

uv run bd project focus Alpha >/dev/null
uv run bd list handoff --branch feature/auth --json | tee "$qa_root/alpha-feature.jsonl"
test "$(wc -l < "$qa_root/alpha-feature.jsonl" | tr -d ' ')" = 1
grep -q 'Alpha feature' "$qa_root/alpha-feature.jsonl"
! grep -q 'Beta feature' "$qa_root/alpha-feature.jsonl"
uv run bd list handoff --branch release/auth --json | tee "$qa_root/alpha-release.jsonl"
test "$(wc -l < "$qa_root/alpha-release.jsonl" | tr -d ' ')" = 1
grep -q 'Alpha release' "$qa_root/alpha-release.jsonl"
! grep -q 'Beta release' "$qa_root/alpha-release.jsonl"

uv run bd project focus Beta >/dev/null
uv run bd list handoff --branch feature/auth --json | tee "$qa_root/beta-feature.jsonl"
test "$(wc -l < "$qa_root/beta-feature.jsonl" | tr -d ' ')" = 1
grep -q 'Beta feature' "$qa_root/beta-feature.jsonl"
! grep -q 'Alpha feature' "$qa_root/beta-feature.jsonl"
uv run bd project focus --clear >/dev/null

old_line="$(printf 'Older explicit-ID body\n' | uv run bd create handoff 'Older explicit ID' --project Alpha --branch feature/limit)"
old_id="${old_line#*#}"
old_id="${old_id%% *}"
sleep 1
printf 'Newer limited body\n' | uv run bd create handoff 'Newer limited' --project Alpha --branch feature/limit >/dev/null
uv run bd list handoff --project Alpha --branch feature/limit --limit 1 --json | tee "$qa_root/limited.jsonl"
test "$(wc -l < "$qa_root/limited.jsonl" | tr -d ' ')" = 1
grep -q 'Newer limited' "$qa_root/limited.jsonl"
! grep -q 'Older explicit ID' "$qa_root/limited.jsonl"
uv run bd show --json "$old_id" | grep -q 'Older explicit-ID body'

uv run python - "$handoff_id" <<'PY'
import asyncio
import sys

import httpx

from braindump.core import entries
from braindump.core.config import load_config
from braindump.web.app import app


async def main() -> None:
    entry_id = int(sys.argv[1])
    cfg = load_config()
    found = entries.find_by_id(cfg, entry_id)
    assert found is not None
    type_dir, entry = found
    index_path = cfg.index_path(type_dir)
    markdown_path = cfg.type_dir(type_dir) / entry.file_path
    before = (index_path.read_bytes(), markdown_path.read_bytes())

    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        viewed = await client.get(f"/entries/{entry_id}")
        assert viewed.status_code == 200
        assert "Auth session" in viewed.text
        assert "branch release/auth" in viewed.text

        assert (index_path.read_bytes(), markdown_path.read_bytes()) == before

        removed = await client.post(
            f"/api/entries/{entry_id}", data={"branch": ""}
        )
        assert removed.status_code == 200
        cleared = entries.find_by_id(cfg, entry_id)
        assert cleared is not None
        assert cleared[1].branch is None
        detail_after_clear = await client.get(f"/entries/{entry_id}")
        assert "branch release/auth" not in detail_after_clear.text


asyncio.run(main())
PY

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
