"""MCP adapter integration tests against the CLI's shared service contract."""

from __future__ import annotations

import asyncio
import json

import pytest
from mcp.types import CallToolResult
from typer.testing import CliRunner

from braindump.cli.main import app
from braindump.mcp import mcp


def call_tool(name, arguments):
    result = asyncio.run(mcp.call_tool(name, arguments))
    assert isinstance(result, CallToolResult)
    structured = result.structured_content
    return (
        structured.get("result", structured)
        if isinstance(structured, dict)
        else structured
    )


def test_mcp_handoff_create_search_show_and_update(cfg, monkeypatch):
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    created = call_tool(
        "create",
        {
            "entry_type": "handoff",
            "title": "MCP session",
            "body": "MCP body",
            "branch": "feature/mcp",
        },
    )
    entry_id = created["entry"]["id"]

    searched = call_tool("search", {"types": ["handoff"], "branch": "feature/mcp"})
    assert [hit["entry"]["id"] for hit in searched] == [entry_id]
    shown = call_tool("show", {"ids": [entry_id]})
    assert (
        shown["entries"][0]["body"],
        len(shown["entries"][0]["body_revision"]),
        shown["entries"][0]["entry"]["branch"],
    ) == ("MCP body", 64, "feature/mcp")

    updated = call_tool(
        "update", {"entry_id": entry_id, "patch": {"branch": "release/mcp"}}
    )
    assert updated["branch"] == "release/mcp"


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("search", {"status": "invalid"}),
        ("search", {"sort": "invalid"}),
        ("list", {"since": "not-a-date"}),
    ],
)
def test_mcp_rejects_invalid_search_filters(name, arguments):
    with pytest.raises(Exception, match=r"(status|sort|since)"):
        call_tool(name, arguments)


@pytest.fixture
def mcp_todo(cfg, monkeypatch):
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

    return runner, entry_id


def test_mcp_todo_show_matches_cli(mcp_todo):
    runner, entry_id = mcp_todo
    cli_show = runner.invoke(app, ["show", "--json", str(entry_id)])
    assert cli_show.exit_code == 0
    shown = call_tool("show", {"ids": [entry_id]})
    assert json.loads(cli_show.stdout)["body"] == shown["entries"][0]["body"]


def test_mcp_todo_search_matches_cli(mcp_todo):
    runner, entry_id = mcp_todo
    cli_search = runner.invoke(app, ["search", "MCP", "contract"])
    assert cli_search.exit_code == 0
    cli_ids = {json.loads(line)["id"] for line in cli_search.stdout.splitlines()}
    mcp_ids = {
        hit["entry"]["id"] for hit in call_tool("search", {"query": "MCP contract"})
    }
    assert mcp_ids == cli_ids == {entry_id}


def test_mcp_todo_update_and_cli_done(mcp_todo):
    runner, entry_id = mcp_todo
    updated = call_tool(
        "update",
        {
            "entry_id": entry_id,
            "patch": {"title": "Updated MCP todo"},
            "body": "updated body",
        },
    )
    assert updated["title"] == "Updated MCP todo"
    assert (
        call_tool("show", {"ids": [entry_id]})["entries"][0]["body"] == "updated body"
    )
    cli_done = runner.invoke(app, ["done", str(entry_id)])
    assert cli_done.exit_code == 0
    assert call_tool("done", {"arg": entry_id})["status"] == "done"


def test_mcp_partial_update_returns_compact_receipt(mcp_todo):
    _runner, entry_id = mcp_todo
    shown = call_tool("show", {"ids": [entry_id]})
    receipt = call_tool(
        "update",
        {
            "entry_id": entry_id,
            "patch": {},
            "body_revision": shown["entries"][0]["body_revision"],
            "edits": [{"match": "body from MCP", "replacement": "new body"}],
        },
    )
    assert set(receipt) == {"entry_id", "body_revision", "edits_applied"}
    assert call_tool("show", {"ids": [entry_id]})["entries"][0]["body"] == "new body"


def test_mcp_partial_update_rejects_identity_and_unsupported_relation(mcp_todo):
    _runner, entry_id = mcp_todo
    shown = call_tool("show", {"ids": [entry_id]})
    revision = shown["entries"][0]["body_revision"]
    for patch, message in (
        ({"id": 999}, "cannot patch immutable fields"),
        ({"project_ids": [1]}, "not valid for todo"),
    ):
        with pytest.raises(Exception, match=message):
            call_tool(
                "update",
                {
                    "entry_id": entry_id,
                    "patch": patch,
                    "body_revision": revision,
                    "edits": [{"match": "body from MCP", "replacement": "new"}],
                },
            )
    assert call_tool("show", {"ids": [entry_id]})["entries"][0]["body"] == (
        "body from MCP"
    )


@pytest.fixture
def mcp_pitches(cfg, monkeypatch):
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    for title, priority, coverage in (
        ("Low unaudited", "low", None),
        ("Medium covered", "medium", "covered"),
        ("High unaudited", "high", None),
    ):
        type_fields = {"priority": priority}
        if coverage is not None:
            type_fields["coverage"] = coverage
        call_tool(
            "create",
            {
                "entry_type": "pitch",
                "title": title,
                "type_fields": type_fields,
            },
        )


def test_mcp_preserves_priority_coverage_filtering_and_sorting(mcp_pitches):
    covered = call_tool("search", {"coverage": "covered"})
    assert [hit["entry"]["title"] for hit in covered] == ["Medium covered"]

    unaudited = call_tool(
        "list",
        {
            "types": ["pitch"],
            "coverage": "unaudited",
            "sort": "priority",
            "direction": "asc",
        },
    )
    assert [hit["entry"]["title"] for hit in unaudited] == [
        "High unaudited",
        "Low unaudited",
    ]
