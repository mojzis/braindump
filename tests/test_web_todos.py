from __future__ import annotations

import re
from datetime import datetime, timedelta
from html import unescape

import httpx
import pytest

from braindump.core import entries, store
from braindump.core.schema import Entry
from braindump.web.app import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _set_home(monkeypatch, cfg) -> None:
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    monkeypatch.setenv("BRAINDUMP_DAY_CUTOFF", str(cfg.day_cutoff_hour))


def _client():
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _todo(cfg, title, *, project=None, status="pending", tags=None, minute=0):
    return entries.create_entry(
        cfg,
        "todos",
        title,
        "body",
        tags=tags or [],
        project=project,
        type_fields={"status": status},
        now=datetime(2026, 4, 11, 14, minute),
    )


async def _get(url):
    async with app.router.lifespan_context(app), _client() as client:
        return await client.get(url)


@pytest.mark.anyio
async def test_todos_default_lists_open_across_projects(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    _todo(cfg, "open a", project="alpha", minute=1)
    _todo(cfg, "open b", project="beta", minute=2)
    _todo(cfg, "finished", project="alpha", status="done", minute=3)

    r = await _get("/todos")
    assert r.status_code == 200
    assert "open a" in r.text
    assert "open b" in r.text  # cross-project by default
    assert "finished" not in r.text  # done hidden by default


@pytest.mark.anyio
async def test_todos_all_includes_done(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    _todo(cfg, "finished", status="done")

    assert "finished" not in (await _get("/todos")).text
    assert "finished" in (await _get("/todos?all=1")).text


@pytest.mark.anyio
async def test_todos_hides_cancelled_by_default(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    _todo(cfg, "cancelled item", status="cancelled")

    assert "cancelled item" not in (await _get("/todos")).text
    assert "cancelled item" in (await _get("/todos?all=1")).text


@pytest.mark.anyio
async def test_todos_hides_postponed_by_default(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    _todo(cfg, "active one", minute=1)
    _todo(cfg, "on hold", status="postponed", minute=2)

    r = await _get("/todos")
    assert "active one" in r.text
    assert "on hold" not in r.text  # postponed hidden by default

    r = await _get("/todos?postponed=1")
    assert "on hold" in r.text
    assert "active one" in r.text  # still open


@pytest.mark.anyio
async def test_todos_postponed_stays_hidden_with_all(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    _todo(cfg, "done one", status="done", minute=1)
    _todo(cfg, "on hold", status="postponed", minute=2)

    # show done, but postponed is an independent axis
    r = await _get("/todos?all=1")
    assert "done one" in r.text
    assert "on hold" not in r.text


@pytest.mark.anyio
async def test_todos_has_edit_link(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    result = _todo(cfg, "editable")
    r = await _get("/todos")
    assert f"/entries/{result.entry.id}/edit" in r.text


@pytest.mark.anyio
async def test_todos_project_filter(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    _todo(cfg, "in alpha", project="alpha")
    _todo(cfg, "in beta", project="beta")

    r = await _get("/todos?project=alpha")
    assert "in alpha" in r.text
    assert "in beta" not in r.text


@pytest.mark.anyio
async def test_todos_tag_filter(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    _todo(cfg, "tagged", tags=["urgent"])
    _todo(cfg, "plain")

    r = await _get("/todos?tag=urgent")
    assert "tagged" in r.text
    assert "plain" not in r.text


@pytest.mark.anyio
async def test_todos_priority_filter_and_sort(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    _todo(cfg, "low item", minute=1)
    high = entries.create_entry(
        cfg,
        "todo",
        "high item",
        "body",
        type_fields={"status": "pending", "priority": "high"},
        now=datetime(2026, 4, 11, 14, 2),
    )

    filtered = await _get("/todos?priority=high")
    assert "high item" in filtered.text
    assert "low item" not in filtered.text
    sorted_rows = await _get("/todos?sort=priority&dir=asc")
    assert sorted_rows.text.index("high item") < sorted_rows.text.index("low item")
    assert f"/entries/{high.entry.id}" in sorted_rows.text

    blank_filter = await _get("/todos?priority=")
    assert "high item" in blank_filter.text
    assert "low item" in blank_filter.text


@pytest.mark.anyio
async def test_todos_priority_sort_happens_before_500_row_limit(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    newer_unspecified = [
        Entry(
            id=entry_id,
            type="todo",
            title=f"overflow item {entry_id}",
            file_path=f"2026/04/overflow-{entry_id}.md",
            created_at="2026-04-12T12:00:00Z",
            status="pending",
        )
        for entry_id in range(1, 502)
    ]
    old_high = Entry(
        id=502,
        type="todo",
        title="old high priority",
        file_path="2026/04/old-high-priority.md",
        created_at="2026-04-11T12:00:00Z",
        status="pending",
        priority="high",
    )
    store.rewrite_index_atomic(cfg, "todos", [*newer_unspecified, old_high])

    response = await _get("/todos?sort=priority&dir=asc")

    assert response.status_code == 200
    assert "old high priority" in response.text
    assert "500 todos" in response.text


@pytest.mark.anyio
async def test_todos_local_sort_keeps_same_500_rows_across_directions(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    records = [
        Entry(
            id=entry_id,
            type="todo",
            title=f"item {503 - entry_id:03d}",
            file_path=f"2026/04/item-{entry_id}.md",
            created_at=(datetime(2026, 4, 1) + timedelta(minutes=entry_id)).isoformat(),
            status="pending",
        )
        for entry_id in range(1, 503)
    ]
    store.rewrite_index_atomic(cfg, "todos", records)

    ascending = await _get("/todos?sort=title&dir=asc")
    descending = await _get("/todos?sort=title&dir=desc")

    ascending_ids = set(re.findall(r">#(\d+)</a>", ascending.text))
    descending_ids = set(re.findall(r">#(\d+)</a>", descending.text))
    assert ascending.status_code == descending.status_code == 200
    assert len(ascending_ids) == 500
    assert ascending_ids == descending_ids == {str(i) for i in range(3, 503)}


@pytest.mark.anyio
async def test_todos_descending_priority_keeps_noncanonical_values_last(
    monkeypatch, cfg
):
    _set_home(monkeypatch, cfg)
    priorities = ("high", "medium", "low", None, "urgent")
    records = [
        Entry(
            id=entry_id,
            type="todo",
            title=f"priority {priority or 'unspecified'}",
            file_path=f"2026/04/priority-{entry_id}.md",
            created_at=f"2026-04-11T14:0{entry_id}:00Z",
            status="pending",
            priority=priority,
        )
        for entry_id, priority in enumerate(priorities, start=1)
    ]
    store.rewrite_index_atomic(cfg, "todos", records)

    response = await _get("/todos?sort=priority&dir=desc")

    body = response.text
    assert response.status_code == 200
    assert body.index("priority low") < body.index("priority medium")
    assert body.index("priority medium") < body.index("priority high")
    assert body.index("priority high") < body.index("priority urgent")
    assert body.index("priority high") < body.index("priority unspecified")


@pytest.mark.anyio
async def test_todos_links_preserve_priority_filter(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    entries.create_entry(
        cfg,
        "todo",
        "urgent item",
        "body",
        tags=["urgent", "reference"],
        project="alpha",
        type_fields={"status": "pending", "priority": "high"},
        now=datetime(2026, 4, 11, 14, 2),
    )

    response = await _get(
        "/todos?q=urgent+item&project=alpha&tag=urgent&priority=high"
        "&sort=priority&dir=asc"
    )
    body = unescape(response.text)

    assert (
        'href="/todos?q=urgent%20item&project=alpha&tag=urgent&priority=high'
        '&sort=priority&dir=desc"' in body
    )
    assert (
        'href="/todos?q=urgent%20item&project=alpha&tag=reference&priority=high'
        '&sort=priority&dir=asc"' in body
    )


@pytest.mark.anyio
async def test_todos_bad_sort_and_dir_fall_back(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    _todo(cfg, "only one")
    # unknown sort key and garbage dir must not error
    r = await _get("/todos?sort=bogus&dir=garbage")
    assert r.status_code == 200
    assert "only one" in r.text


@pytest.mark.anyio
async def test_todos_ignores_active_project_focus(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    _todo(cfg, "in alpha", project="alpha")
    _todo(cfg, "in beta", project="beta")
    from braindump.core import config

    config.set_active_project(cfg, "alpha")

    r = await _get("/todos")
    assert "in alpha" in r.text
    assert "in beta" in r.text  # focus must not narrow the cross-project view
