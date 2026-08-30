from __future__ import annotations

from datetime import datetime

import httpx
import pytest

from braindump.core import entries, store
from braindump.web.app import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _set_home(monkeypatch, cfg) -> None:
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    monkeypatch.setenv("BRAINDUMP_DAY_CUTOFF", str(cfg.day_cutoff_hour))


async def _request(monkeypatch, cfg, method: str, url: str, **kwargs):
    _set_home(monkeypatch, cfg)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        return await client.request(method, url, **kwargs)


@pytest.mark.anyio
async def test_graph_capture_edit_and_details(monkeypatch, cfg):
    project = entries.create_entry(
        cfg, "project", "Alpha", "body", now=datetime(2026, 4, 11, 10)
    )
    initiative = entries.create_entry(
        cfg,
        "initiative",
        "Launch",
        "body",
        type_fields={"status": "active", "project_ids": [project.entry.id]},
        now=datetime(2026, 4, 11, 11),
    )
    pitch = entries.create_entry(
        cfg,
        "pitch",
        "Pitch",
        "body",
        type_fields={
            "status": "active",
            "project_ids": [project.entry.id],
            "initiative_ids": [initiative.entry.id],
        },
        now=datetime(2026, 4, 11, 12),
    )

    capture = await _request(
        monkeypatch,
        cfg,
        "GET",
        "/capture?type=pitch",
    )
    assert capture.status_code == 200
    assert f'value="{initiative.entry.id}"' in capture.text
    assert (
        f'value="{pitch.entry.id}"' in capture.text or "active_pitches" in capture.text
    )

    todo = entries.create_entry(
        cfg,
        "todo",
        "Implement",
        "body",
        type_fields={"initiative_id": initiative.entry.id, "pitch_id": pitch.entry.id},
        now=datetime(2026, 4, 11, 13),
    )
    detail = await _request(monkeypatch, cfg, "GET", f"/entries/{todo.entry.id}")
    assert detail.status_code == 200
    assert f'href="/entries/{initiative.entry.id}"' in detail.text
    assert f'href="/entries/{pitch.entry.id}"' in detail.text

    edit = await _request(monkeypatch, cfg, "GET", f"/entries/{pitch.entry.id}/edit")
    assert edit.status_code == 200
    assert "project_ids" in edit.text
    assert "initiative_ids" in edit.text

    updated = await _request(
        monkeypatch,
        cfg,
        "POST",
        f"/api/entries/{todo.entry.id}",
        data={"initiative_id": str(initiative.entry.id), "pitch_id": ""},
    )
    assert updated.status_code == 200
    assert entries.find_by_id(cfg, todo.entry.id)[1].pitch_id is None

    initiative_index = await _request(monkeypatch, cfg, "GET", "/initiatives")
    assert "Launch" in initiative_index.text
    done_initiative = entries.update_entry(cfg, initiative.entry.id, {"status": "done"})
    assert done_initiative.status == "done"
    initiative_index = await _request(monkeypatch, cfg, "GET", "/initiatives")
    assert "Launch" not in initiative_index.text

    project_page = await _request(monkeypatch, cfg, "GET", "/projects/Alpha")
    assert project_page.status_code == 200
    assert f"/entries/{initiative.entry.id}" in project_page.text
    assert f"/entries/{pitch.entry.id}" in project_page.text


@pytest.mark.anyio
async def test_graph_missing_relation_is_a_warning(monkeypatch, cfg):
    todo = entries.create_entry(
        cfg,
        "todo",
        "Stale link",
        "body",
        type_fields={"status": "pending"},
        now=datetime(2026, 4, 11, 13),
    )
    # Simulate an old/deleted target without using a second storage path.
    index = cfg.home / "todos" / "index.jsonl"
    text = index.read_text().replace(
        '"status": "pending"',
        '"status": "pending", "initiative_id": 999',
    )
    index.write_text(text)
    detail = await _request(monkeypatch, cfg, "GET", f"/entries/{todo.entry.id}")
    assert detail.status_code == 200
    assert "missing initiative #999" in detail.text
    assert "/entries/999" not in detail.text


@pytest.mark.anyio
async def test_initiative_parse_route_creates_linked_todos_once(monkeypatch, cfg):
    project = entries.create_entry(cfg, "project", "Alpha", "body")
    initiative = entries.create_entry(
        cfg,
        "initiative",
        "Launch",
        "- [ ] ship it",
        type_fields={"project_ids": [project.entry.id]},
    )

    detail = await _request(monkeypatch, cfg, "GET", f"/entries/{initiative.entry.id}")
    assert "parse todos" in detail.text

    parsed = await _request(
        monkeypatch,
        cfg,
        "POST",
        f"/api/initiatives/{initiative.entry.id}/parse",
    )
    assert parsed.status_code == 200
    assert parsed.headers["hx-redirect"] == f"/entries/{initiative.entry.id}"
    assert len(store.read_index(cfg, "todos")) == 1

    await _request(
        monkeypatch,
        cfg,
        "POST",
        f"/api/initiatives/{initiative.entry.id}/parse",
    )
    assert len(store.read_index(cfg, "todos")) == 1
