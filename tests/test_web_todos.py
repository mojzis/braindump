from __future__ import annotations

from datetime import datetime

import httpx
import pytest

from braindump.core import entries
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
