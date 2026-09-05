"""MCP adapter integration tests against the CLI's shared service contract."""

from __future__ import annotations

import asyncio
import json

from typer.testing import CliRunner

from braindump.cli.main import app
from braindump.mcp import mcp


def call_tool(name, arguments):
    _content, structured = asyncio.run(mcp.call_tool(name, arguments))
    return (
        structured.get("result", structured)
        if isinstance(structured, dict)
        else structured
    )


def test_mcp_todo_round_trip_matches_cli(cfg, monkeypatch):
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    runner = CliRunner()

    created = call_tool(
        "create",
        {
            "entry_type": "todo",
            "title": "MCP contract todo",
            "body": "body from MCP",
            "tags": ["contract"],
            "project": "braindump",
            "type_fields": {"status": "pending"},
        },
    )
    entry = created["entry"]
    entry_id = entry["id"]

    cli_show = runner.invoke(app, ["show", "--json", str(entry_id)])
    assert cli_show.exit_code == 0
    shown = call_tool("show", {"ids": [entry_id]})
    assert json.loads(cli_show.stdout)["body"] == shown["entries"][0]["body"]

    cli_search = runner.invoke(app, ["search", "MCP", "contract"])
    assert cli_search.exit_code == 0
    cli_ids = {json.loads(line)["id"] for line in cli_search.stdout.splitlines()}
    mcp_ids = {
        hit["entry"]["id"] for hit in call_tool("search", {"query": "MCP contract"})
    }
    assert mcp_ids == cli_ids == {entry_id}

    updated = call_tool(
        "update",
        {
            "entry_id": entry_id,
            "patch": {"title": "Updated MCP todo"},
            "body": "updated body",
        },
    )
    assert updated["title"] == "Updated MCP todo"
    assert call_tool("show", {"ids": [entry_id]})["entries"][0]["body"] == (
        "updated body"
    )

    cli_done = runner.invoke(app, ["done", str(entry_id)])
    assert cli_done.exit_code == 0
    assert call_tool("done", {"arg": entry_id})["status"] == "done"
