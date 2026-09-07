from __future__ import annotations

import asyncio

from braindump.mcp import mcp


def _call(name: str, arguments: dict):
    _content, structured = asyncio.run(mcp.call_tool(name, arguments))
    return (
        structured.get("result", structured)
        if isinstance(structured, dict)
        else structured
    )


def test_mcp_handoff_create_search_show_and_update(cfg, monkeypatch):
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    created = _call(
        "create",
        {
            "entry_type": "handoff",
            "title": "MCP session",
            "body": "MCP body",
            "branch": "feature/mcp",
        },
    )
    entry_id = created["entry"]["id"]

    searched = _call("search", {"types": ["handoff"], "branch": "feature/mcp"})
    assert [hit["entry"]["id"] for hit in searched] == [entry_id]
    shown = _call("show", {"ids": [entry_id]})
    assert shown["entries"][0]["body"] == "MCP body"
    assert shown["entries"][0]["entry"]["branch"] == "feature/mcp"

    updated = _call(
        "update", {"entry_id": entry_id, "patch": {"branch": "release/mcp"}}
    )
    assert updated["branch"] == "release/mcp"
