from __future__ import annotations

import asyncio
import json
from datetime import datetime

import httpx
import pytest
from mcp.types import CallToolResult
from typer.testing import CliRunner

from braindump.cli.main import app
from braindump.core import entries, query, store
from braindump.mcp import mcp
from braindump.service import (
    BraindumpService,
    CreateRequest,
    SearchRequest,
    UpdateRequest,
)
from braindump.web.app import app as web_app


def _todo(cfg, title, *, presence=None, status="pending", minute=0):
    fields = {"status": status}
    if presence is not None:
        fields["presence"] = presence
    return entries.create_entry(
        cfg,
        "todo",
        title,
        "body",
        tags=["presence"],
        project="alpha",
        type_fields=fields,
        now=datetime(2026, 4, 11, 14, minute),
    )


def _entry(cfg, entry_id):
    found = entries.find_by_id(cfg, entry_id)
    if found is None:
        raise AssertionError(f"entry {entry_id} not found")
    return found[1]


def test_presence_persists_updates_and_clears_without_body_changes(cfg):
    created = _todo(cfg, "classify me", presence="agent")
    original = _entry(cfg, created.entry.id)

    updated = entries.update_entry(cfg, created.entry.id, {"presence": "together"})
    assert (updated.presence, updated.status, updated.tags) == (
        "together",
        original.status,
        original.tags,
    )
    assert _entry(cfg, created.entry.id).project == "alpha"
    assert store.read_markdown(store.full_path_for(cfg, "todos", updated.file_path))[
        1
    ].endswith("body\n")

    cleared = entries.update_entry(cfg, created.entry.id, {"presence": None})
    assert (
        cleared.presence,
        "presence"
        in store.read_markdown(store.full_path_for(cfg, "todos", cleared.file_path))[0],
    ) == (None, False)


@pytest.mark.parametrize(
    ("entry_type", "fields", "message"),
    [
        ("til", {"presence": "agent"}, "only valid for todos"),
        ("todo", {"presence": "later"}, "todo presence"),
    ],
)
def test_presence_validation(cfg, entry_type, fields, message):
    with pytest.raises(ValueError, match=message):
        entries.create_entry(
            cfg, entry_type, "invalid", type_fields=fields, body="body"
        )


def test_presence_filters_include_unclassified_and_needs_my_time_union(cfg):
    agent = _todo(cfg, "agent", presence="agent", minute=1)
    together = _todo(cfg, "together", presence="together", minute=2)
    personal = _todo(cfg, "personal", presence="personal", minute=3)
    unset = _todo(cfg, "unset", minute=4)
    assert {h.entry.id for h in query.search(cfg, query.SearchFilters())} == {
        agent.entry.id,
        together.entry.id,
        personal.entry.id,
        unset.entry.id,
    }
    assert [
        h.entry.id for h in query.search(cfg, query.SearchFilters(presence="agent"))
    ] == [agent.entry.id]
    assert {
        h.entry.id
        for h in query.search(cfg, query.SearchFilters(presence="unclassified"))
    } == {unset.entry.id}
    assert {
        h.entry.id
        for h in query.search(cfg, query.SearchFilters(presence="needs-my-time"))
    } == {together.entry.id, personal.entry.id}


def test_service_cli_and_mcp_presence_contract(cfg, monkeypatch):
    service = BraindumpService(cfg)
    created = service.create(
        CreateRequest(
            entry_type="todo",
            title="adapter todo",
            body="body",
            type_fields={"presence": "agent"},
        )
    )
    updated = service.update(UpdateRequest(created.entry.id, {"presence": "personal"}))
    assert (
        [h.entry.id for h in service.list_entries(SearchRequest(presence="personal"))],
        updated.presence,
    ) == ([created.entry.id], "personal")

    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    runner = CliRunner()
    cli_result = runner.invoke(
        app, ["update", str(created.entry.id), "--clear-presence"]
    )
    assert cli_result.exit_code == 0
    cli_show = runner.invoke(app, ["show", "--json", str(created.entry.id)])
    assert "presence" not in json.loads(cli_show.stdout)

    async def call(name, arguments):
        result = await mcp.call_tool(name, arguments)
        if not isinstance(result, CallToolResult):
            raise TypeError(f"unexpected MCP result: {result!r}")
        structured = result.structured_content
        return (
            structured.get("result", structured)
            if isinstance(structured, dict)
            else structured
        )

    mcp_created = asyncio.run(
        call(
            "create",
            {"entry_type": "todo", "title": "mcp todo", "presence": "together"},
        )
    )
    mcp_id = mcp_created["entry"]["id"]
    search_result = asyncio.run(call("search", {"presence": "together"}))
    asyncio.run(call("clear_presence", {"entry_id": mcp_id}))
    assert (
        search_result[0]["entry"]["id"],
        "presence"
        in asyncio.run(call("show", {"ids": [mcp_id]}))["entries"][0]["entry"],
    ) == (mcp_id, False)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_web_presence_selection_badge_and_unclassified_filter(monkeypatch, cfg):
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    classified = _todo(cfg, "web classified", presence="agent")
    _todo(cfg, "web unclassified", minute=1)
    transport = httpx.ASGITransport(app=web_app)
    async with (
        web_app.router.lifespan_context(web_app),
        httpx.AsyncClient(
            transport=transport,
            base_url=str(httpx.URL(scheme="http", host="presence-test")),
        ) as client,
    ):
        view = await client.get(f"/entries/{classified.entry.id}")
        assert "Agent can handle" in view.text
        filtered = await client.get("/todos?presence=unclassified")
        assert "web unclassified" in filtered.text
        assert "web classified" not in filtered.text


@pytest.mark.anyio
async def test_web_presence_filter_survives_project_and_sort_links(monkeypatch, cfg):
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    _todo(cfg, "web classified", presence="agent")
    transport = httpx.ASGITransport(app=web_app)
    async with (
        web_app.router.lifespan_context(web_app),
        httpx.AsyncClient(
            transport=transport,
            base_url=str(httpx.URL(scheme="http", host="presence-test")),
        ) as client,
    ):
        composed = await client.get(
            "/todos?presence=agent&project=alpha&tag=presence&sort=presence&dir=asc"
        )
        assert composed.status_code == 200
        assert "sort=presence" in composed.text
        assert "presence=agent" in composed.text
