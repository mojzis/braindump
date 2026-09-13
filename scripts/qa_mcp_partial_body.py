# ruff: noqa: S101, T201
"""Functional QA consumer for partial authored-body edits over MCP stdio."""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import shutil
import tempfile
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import TextContent

EDIT_COUNT = 3
CONTENTION_OBSERVATION_SECONDS = 1.0


def _text(result) -> str:
    if result.content and isinstance(result.content[0], TextContent):
        return result.content[0].text
    return "MCP tool error"


def _payload(result):
    if result.isError:
        text = result.content[0].text if result.content else "MCP tool error"
        raise AssertionError(text)
    structured = result.structuredContent
    if isinstance(structured, dict) and "result" in structured:
        return structured["result"]
    if structured:
        return structured
    return json.loads(result.content[0].text)


async def journey(store_dir: Path) -> dict[str, object]:  # noqa: PLR0915
    env = {**os.environ, "BRAINDUMP_DIR": str(store_dir)}
    params = StdioServerParameters(
        command="uv",
        args=["run", "--frozen", "--no-sync", "bd-mcp"],
        env=env,
    )
    captured: list[dict[str, object]] = []
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        tool_list = await session.list_tools()
        tool_names = {tool.name for tool in tool_list.tools}
        assert {"create", "show", "update"} <= tool_names
        update_tool = next(tool for tool in tool_list.tools if tool.name == "update")
        assert "edits" in json.dumps(update_tool.inputSchema)
        assert "body_revision" in json.dumps(update_tool.inputSchema)

        async def call(name: str, arguments: dict[str, object]):
            if name == "update":
                captured.append(dict(arguments))
            return _payload(await session.call_tool(name, arguments))

        created = await call(
            "create",
            {
                "entry_type": "todo",
                "title": "MCP partial QA",
                "body": "first line\nsecond line\n😀 keep\nsecond line",
                "original_input": "long original input stays indexed",
                "type_fields": {"status": "pending"},
            },
        )
        entry_id = created["entry"]["id"]
        before = await call("show", {"ids": [entry_id]})
        item = before["entries"][0]
        revision = item["body_revision"]
        original_body = item["body"]
        assert item["entry"]["input"] == "long original input stays indexed"

        receipt = await call(
            "update",
            {
                "entry_id": entry_id,
                "patch": {},
                "body_revision": revision,
                "edits": [
                    {"match": "first line", "replacement": "FIRST line"},
                    {"match": "😀 keep\n", "replacement": ""},
                    {
                        "match": "second line\nsecond line",
                        "replacement": "second line\ninserted\nsecond line",
                    },
                ],
            },
        )
        assert receipt["edits_applied"] == EDIT_COUNT
        after = await call("show", {"ids": [entry_id]})
        assert after["entries"][0]["body"] == (
            "FIRST line\nsecond line\ninserted\nsecond line"
        )
        assert after["entries"][0]["body_revision"] == receipt["body_revision"]
        assert after["entries"][0]["entry"]["input"] == item["entry"]["input"]
        assert "body" not in receipt
        assert original_body != after["entries"][0]["body"]

        stale = await session.call_tool(
            "update",
            {
                "entry_id": entry_id,
                "patch": {},
                "body_revision": revision,
                "edits": [{"match": "FIRST", "replacement": "stale"}],
            },
        )
        assert stale.isError and "stale body revision" in _text(stale)

        current = after["entries"][0]["body_revision"]
        intervening = await call(
            "update",
            {
                "entry_id": entry_id,
                "patch": {},
                "body_revision": current,
                "edits": [{"match": "FIRST", "replacement": "current"}],
            },
        )
        stale_after_intervening = await session.call_tool(
            "update",
            {
                "entry_id": entry_id,
                "patch": {},
                "body_revision": current,
                "edits": [{"match": "second line", "replacement": "stale"}],
            },
        )
        assert stale_after_intervening.isError
        assert "stale body revision" in _text(stale_after_intervening)

        params_for_clients = StdioServerParameters(
            command="uv",
            args=["run", "--frozen", "--no-sync", "bd-mcp"],
            env=env,
        )
        async with AsyncExitStack() as clients:
            concurrent_sessions = []
            for _ in range(2):
                client_read, client_write = await clients.enter_async_context(
                    stdio_client(params_for_clients)
                )
                client = await clients.enter_async_context(
                    ClientSession(client_read, client_write)
                )
                await client.initialize()
                concurrent_sessions.append(client)

            concurrent_views = await asyncio.gather(
                *(
                    client.call_tool("show", {"ids": [entry_id]})
                    for client in concurrent_sessions
                )
            )
            concurrent_revision = _payload(concurrent_views[0])["entries"][0][
                "body_revision"
            ]
            concurrent_updates = await asyncio.gather(
                *(
                    client.call_tool(
                        "update",
                        {
                            "entry_id": entry_id,
                            "patch": {},
                            "body_revision": concurrent_revision,
                            "edits": [
                                {
                                    "match": "current line",
                                    "replacement": "parallel line",
                                }
                            ],
                        },
                    )
                    for client in concurrent_sessions
                )
            )
            assert sum(not result.isError for result in concurrent_updates) == 1
            assert sum(result.isError for result in concurrent_updates) == 1
            assert any(
                result.isError and "stale body revision" in _text(result)
                for result in concurrent_updates
            )

            after_concurrent = await call("show", {"ids": [entry_id]})
            latest_revision = after_concurrent["entries"][0]["body_revision"]
            lock_path = store_dir / ".mutation.lock"
            lock_file = lock_path.open("a+")
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                requests_ready = [asyncio.Event(), asyncio.Event()]
                start_requests = asyncio.Event()

                async def call_after_start(client, name, arguments, ready):
                    ready.set()
                    await start_requests.wait()
                    return await client.call_tool(name, arguments)

                blocked_update = asyncio.create_task(
                    call_after_start(
                        concurrent_sessions[0],
                        "update",
                        {
                            "entry_id": entry_id,
                            "patch": {},
                            "body_revision": latest_revision,
                            "edits": [
                                {
                                    "match": "parallel line",
                                    "replacement": "serialized line",
                                }
                            ],
                        },
                        requests_ready[0],
                    )
                )
                blocked_create = asyncio.create_task(
                    call_after_start(
                        concurrent_sessions[1],
                        "create",
                        {
                            "entry_type": "todo",
                            "title": "Concurrent unrelated row",
                            "body": "must survive",
                        },
                        requests_ready[1],
                    )
                )
                await asyncio.gather(*(ready.wait() for ready in requests_ready))
                start_requests.set()
                done, pending = await asyncio.wait(
                    {blocked_update, blocked_create},
                    timeout=CONTENTION_OBSERVATION_SECONDS,
                )
                assert not done, "mutation completed while external lock was held"
                assert pending == {blocked_update, blocked_create}
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()
            update_result, create_result = await asyncio.gather(
                blocked_update, blocked_create
            )
            assert not update_result.isError
            assert not create_result.isError
            unrelated_id = _payload(create_result)["entry"]["id"]
            preserved = await call("show", {"ids": [entry_id, unrelated_id]})
            assert {item["entry"]["id"] for item in preserved["entries"]} == {
                entry_id,
                unrelated_id,
            }

        async def expected_error(arguments: dict[str, object], text: str) -> None:
            failed = await session.call_tool("update", arguments)
            assert failed.isError and text in _text(failed)

        final_state = await call("show", {"ids": [entry_id]})
        current = final_state["entries"][0]["body_revision"]
        await expected_error(
            {
                "entry_id": entry_id,
                "patch": {},
                "body_revision": current,
                "edits": [{"match": "absent", "replacement": "x"}],
            },
            "edit 1: exact match not found",
        )
        await expected_error(
            {
                "entry_id": entry_id,
                "patch": {},
                "body_revision": current,
                "edits": [{"match": "second line", "replacement": "x"}],
            },
            "edit 1: exact match is ambiguous",
        )
        await expected_error(
            {
                "entry_id": entry_id,
                "patch": {},
                "body": "whole body",
                "body_revision": current,
                "edits": [{"match": "serialized", "replacement": "x"}],
            },
            "mutually exclusive",
        )
        unchanged = await call("show", {"ids": [entry_id]})
        assert (
            unchanged["entries"][0]["body"]
            == "serialized line\nsecond line\ninserted\nsecond line"
        )

        legacy = await call(
            "update",
            {
                "entry_id": entry_id,
                "patch": {"title": "MCP legacy"},
                "body": "legacy body",
            },
        )
        assert legacy["id"] == entry_id and legacy["title"] == "MCP legacy"
        assert (await call("show", {"ids": [entry_id]}))["entries"][0][
            "body"
        ] == "legacy body"

        pitch = await call(
            "create",
            {
                "entry_type": "pitch",
                "title": "Long pitch",
                "body": "PITCH-" + ("x" * 12000),
                "type_fields": {"priority": "high"},
            },
        )
        pitch_id = pitch["entry"]["id"]
        pitch_show = await call("show", {"ids": [pitch_id]})
        long_body = pitch_show["entries"][0]["body"]
        long_args = {
            "entry_id": pitch_id,
            "patch": {},
            "body_revision": pitch_show["entries"][0]["body_revision"],
            "edits": [{"match": "PITCH-", "replacement": "PITCH-EDITED-"}],
        }
        long_receipt = await call("update", long_args)
        assert "body" not in captured[-1]
        assert len(json.dumps(long_args)) < len(long_body) // 10
        assert "body" not in long_receipt

        return {
            "status": "pass",
            "transport": "stdio",
            "tools": sorted(tool_names),
            "entry_id": entry_id,
            "pitch_id": pitch_id,
            "receipts": [receipt, intervening, long_receipt],
            "contention_observed_while_external_lock_held": True,
            "body_present_in_long_partial_arguments": "body" in captured[-1],
        }


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="braindump-mcp-partial-qa-"))
    store_dir = root / "store"
    try:
        print(json.dumps(asyncio.run(journey(store_dir)), sort_keys=True))
    finally:
        shutil.rmtree(root)


if __name__ == "__main__":
    main()
