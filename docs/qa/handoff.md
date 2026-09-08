# Handoff QA

This route exercises the CLI plus in-process FastAPI and MCP calls against an
isolated store. Those assertions are supplemental evidence: they do not prove
real browser rendering, native-window behavior, or stdio MCP transport.

Run this journey from the final tree. It uses a disposable store and never
reads or writes `~/braindump`.

```bash
set -eu
qa_root="$(mktemp -d)"
trap 'rm -rf "$qa_root"' EXIT
export BRAINDUMP_DIR="$qa_root/braindump"

handoff_line="$(printf 'Resume the auth work.\n' | uv run --frozen --no-sync bd create handoff 'Auth session' --branch feature/auth)"
handoff_id="${handoff_line#*#}"
handoff_id="${handoff_id%% *}"
test -n "$handoff_id"

uv run --frozen --no-sync bd list handoff --branch feature/auth --json | tee "$qa_root/list.jsonl"
test "$(wc -l < "$qa_root/list.jsonl" | tr -d ' ')" = 1
uv run --frozen --no-sync bd search --type handoff --branch feature/auth --json | grep -q 'Auth session'
uv run --frozen --no-sync bd show --json "$handoff_id" | grep -q 'Resume the auth work.'
uv run --frozen --no-sync bd update "$handoff_id" --branch release/auth
uv run --frozen --no-sync bd show "$handoff_id" | grep -q 'branch: release/auth'

branchless_line="$(printf 'Branchless initial body\n' | uv run --frozen --no-sync bd create handoff 'Branchless session')"
branchless_id="${branchless_line#*#}"
branchless_id="${branchless_id%% *}"
test -n "$branchless_id"

uv run --frozen --no-sync bd show --json "$branchless_id" | tee "$qa_root/branchless-show.json"
uv run --frozen --no-sync bd list handoff --all --json | tee "$qa_root/branchless-list.jsonl"
uv run --frozen --no-sync bd search 'Branchless session' --type handoff --all --json \
  | tee "$qa_root/branchless-search.jsonl"
printf 'Branchless updated body\n' \
  | uv run --frozen --no-sync bd update "$branchless_id" --title 'Branchless session updated' --body
uv run --frozen --no-sync bd show --json "$branchless_id" | tee "$qa_root/branchless-updated.json"

uv run --frozen --no-sync python - "$branchless_id" "$qa_root" <<'PY'
import json
import sys
from pathlib import Path


entry_id = int(sys.argv[1])
qa_root = Path(sys.argv[2])


def read_json(name: str) -> dict:
    return json.loads((qa_root / name).read_text())


def read_jsonl(name: str) -> list[dict]:
    return [json.loads(line) for line in (qa_root / name).read_text().splitlines()]


shown = read_json("branchless-show.json")
assert shown["id"] == entry_id
assert shown["body"] == "Branchless initial body"
assert shown.get("branch") is None

listed = read_jsonl("branchless-list.jsonl")
listed_entry = next(item for item in listed if item["id"] == entry_id)
assert listed_entry.get("branch") is None

searched = read_jsonl("branchless-search.jsonl")
assert [item["id"] for item in searched] == [entry_id]
assert searched[0].get("branch") is None

updated = read_json("branchless-updated.json")
assert updated["id"] == entry_id
assert updated["title"] == "Branchless session updated"
assert updated["body"] == "Branchless updated body"
assert updated.get("branch") is None
PY

printf 'Alpha project\n' | uv run --frozen --no-sync bd create project Alpha >/dev/null
printf 'Beta project\n' | uv run --frozen --no-sync bd create project Beta >/dev/null
printf 'Alpha feature body\n' | uv run --frozen --no-sync bd create handoff 'Alpha feature' --project Alpha --branch feature/auth >/dev/null
printf 'Alpha release body\n' | uv run --frozen --no-sync bd create handoff 'Alpha release' --project Alpha --branch release/auth >/dev/null
printf 'Beta feature body\n' | uv run --frozen --no-sync bd create handoff 'Beta feature' --project Beta --branch feature/auth >/dev/null
printf 'Beta release body\n' | uv run --frozen --no-sync bd create handoff 'Beta release' --project Beta --branch release/auth >/dev/null

uv run --frozen --no-sync bd project focus Alpha >/dev/null
uv run --frozen --no-sync bd list handoff --branch feature/auth --json | tee "$qa_root/alpha-feature.jsonl"
test "$(wc -l < "$qa_root/alpha-feature.jsonl" | tr -d ' ')" = 1
grep -q 'Alpha feature' "$qa_root/alpha-feature.jsonl"
! grep -q 'Beta feature' "$qa_root/alpha-feature.jsonl"
uv run --frozen --no-sync bd list handoff --branch release/auth --json | tee "$qa_root/alpha-release.jsonl"
test "$(wc -l < "$qa_root/alpha-release.jsonl" | tr -d ' ')" = 1
grep -q 'Alpha release' "$qa_root/alpha-release.jsonl"
! grep -q 'Beta release' "$qa_root/alpha-release.jsonl"

uv run --frozen --no-sync bd project focus Beta >/dev/null
uv run --frozen --no-sync bd list handoff --branch feature/auth --json | tee "$qa_root/beta-feature.jsonl"
test "$(wc -l < "$qa_root/beta-feature.jsonl" | tr -d ' ')" = 1
grep -q 'Beta feature' "$qa_root/beta-feature.jsonl"
! grep -q 'Alpha feature' "$qa_root/beta-feature.jsonl"
uv run --frozen --no-sync bd project focus --clear >/dev/null

old_line="$(printf 'Older explicit-ID body\n' | uv run --frozen --no-sync bd create handoff 'Older explicit ID' --project Alpha --branch feature/limit)"
old_id="${old_line#*#}"
old_id="${old_id%% *}"
sleep 1
printf 'Newer limited body\n' | uv run --frozen --no-sync bd create handoff 'Newer limited' --project Alpha --branch feature/limit >/dev/null
uv run --frozen --no-sync bd list handoff --project Alpha --branch feature/limit --limit 1 --json | tee "$qa_root/limited.jsonl"
test "$(wc -l < "$qa_root/limited.jsonl" | tr -d ' ')" = 1
grep -q 'Newer limited' "$qa_root/limited.jsonl"
! grep -q 'Older explicit ID' "$qa_root/limited.jsonl"
uv run --frozen --no-sync bd show --json "$old_id" | grep -q 'Older explicit-ID body'

uv run --frozen --no-sync python - "$handoff_id" <<'PY'
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
        blank_branch = await client.get(
            "/entries",
            params={"type": "handoff", "branch": "", "all": "1"},
        )
        assert blank_branch.status_code == 200
        assert "Branchless session updated" in blank_branch.text
        assert "Alpha feature" in blank_branch.text

        filtered = await client.get(
            "/entries",
            params={
                "type": "handoff",
                "project": "Alpha",
                "branch": "release/auth",
            },
        )
        assert filtered.status_code == 200
        assert "Alpha release" in filtered.text
        assert "Alpha feature" not in filtered.text
        assert "Beta release" not in filtered.text

        viewed = await client.get(f"/entries/{entry_id}")
        assert viewed.status_code == 200
        assert "Auth session" in viewed.text
        assert "branch release/auth" in viewed.text

        assert (index_path.read_bytes(), markdown_path.read_bytes()) == before


asyncio.run(main())
PY

uv run --frozen --no-sync python <<'PY'
import asyncio
import json
import time

from braindump.mcp import mcp


def call(name: str, arguments: dict):
    _content, structured = asyncio.run(mcp.call_tool(name, arguments))
    if isinstance(structured, dict):
        return structured.get("result", structured)
    return structured


target = call(
    "create",
    {
        "entry_type": "handoff",
        "title": "MCP target",
        "body": "MCP initial body",
        "project": "Alpha",
        "branch": "feature/mcp",
    },
)
target_id = target["entry"]["id"]

# These newer records would win limit=1 if project/branch filtering happened late.
time.sleep(1)
call(
    "create",
    {
        "entry_type": "handoff",
        "title": "MCP wrong branch",
        "body": "MCP branch decoy",
        "project": "Alpha",
        "branch": "release/mcp",
    },
)
call(
    "create",
    {
        "entry_type": "handoff",
        "title": "MCP wrong project",
        "body": "MCP project decoy",
        "project": "Beta",
        "branch": "feature/mcp",
    },
)

filters = {
    "types": ["handoff"],
    "project": "Alpha",
    "branch": "feature/mcp",
    "limit": 1,
}
listed = call("list", filters)
assert [hit["entry"]["id"] for hit in listed] == [target_id]

searched = call("search", {"query": "MCP", **filters})
assert [hit["entry"]["id"] for hit in searched] == [target_id]

shown = call("show", {"ids": [target_id]})
assert shown["missing_ids"] == []
assert shown["entries"][0]["body"] == "MCP initial body"
assert shown["entries"][0]["entry"]["branch"] == "feature/mcp"

updated = call(
    "update",
    {
        "entry_id": target_id,
        "patch": {"branch": None},
        "body": "MCP updated body",
    },
)
assert updated.get("branch") is None

shown_after_update = call("show", {"ids": [target_id]})
updated_view = shown_after_update["entries"][0]
assert updated_view["body"] == "MCP updated body"
assert updated_view["entry"].get("branch") is None

print(
    json.dumps(
        {
            "target_id": target_id,
            "list_ids": [hit["entry"]["id"] for hit in listed],
            "search_ids": [hit["entry"]["id"] for hit in searched],
            "shown_before_update": shown,
            "shown_after_update": shown_after_update,
        },
        indent=2,
        sort_keys=True,
    )
)
PY
```

The Python httpx ASGI and in-process MCP sections above are unit/in-process
coverage, not a browser, native, or stdio consumer journey.

Expected evidence: a `handoffs/index.jsonl` record, authored bodies in their
Markdown files, exact branch filtering, a branchless CLI create/show/list/
search/update round trip, and public MCP create/list/search/show/update calls
using the same isolated store. Automated generic web list/view/edit coverage
is included here:

```bash
uv run --frozen --no-sync pytest -q tests/test_entries.py tests/test_query.py tests/test_cli.py \
  tests/test_service.py tests/test_mcp.py tests/test_web_graph.py
```
