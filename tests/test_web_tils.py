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


def _til(cfg, title, *, project=None, tags=None, category=None, source=None, minute=0):
    return entries.create_entry(
        cfg,
        "til",
        title,
        "body",
        tags=tags or [],
        project=project,
        type_fields={"category": category, "source": source},
        now=datetime(2026, 4, 11, 14, minute),
    )


async def _get(url):
    async with app.router.lifespan_context(app), _client() as client:
        return await client.get(url)


@pytest.mark.anyio
async def test_tils_default_lists_only_tils_across_projects(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    _til(cfg, "python fact", project="alpha", minute=1)
    _til(cfg, "docs fact", project="beta", minute=2)
    entries.create_entry(
        cfg, "todo", "not a TIL", "body", now=datetime(2026, 4, 11, 14, 3)
    )

    r = await _get("/tils")
    assert r.status_code == 200
    assert "python fact" in r.text
    assert "docs fact" in r.text
    assert "not a TIL" not in r.text


@pytest.mark.anyio
async def test_tils_project_and_tag_filters(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    _til(cfg, "in alpha", project="alpha", tags=["urgent"])
    _til(cfg, "in beta", project="beta", tags=["urgent"])
    _til(cfg, "plain", project="alpha")

    assert "in alpha" in (await _get("/tils?project=alpha")).text
    assert "in beta" not in (await _get("/tils?project=alpha")).text
    r = await _get("/tils?tag=urgent")
    assert "in alpha" in r.text
    assert "in beta" in r.text
    assert "plain" not in r.text


@pytest.mark.anyio
async def test_tils_has_grouping_metadata_and_edit_link(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    result = _til(cfg, "editable", project="alpha", category="python", source="docs")

    r = await _get("/tils")
    assert "alpha" in r.text
    assert "python" in r.text
    assert "docs" in r.text
    assert f"/entries/{result.entry.id}" in r.text
    assert f"/entries/{result.entry.id}/edit" in r.text
    assert "status" not in r.text


@pytest.mark.anyio
async def test_tils_search_and_bad_sort_fall_back(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    _til(cfg, "python search", category="python")
    _til(cfg, "other fact", category="other")

    r = await _get("/tils?q=python&sort=bogus&dir=garbage")
    assert r.status_code == 200
    assert "python search" in r.text
    assert "other fact" not in r.text


@pytest.mark.anyio
async def test_tils_ignores_active_project_focus(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    _til(cfg, "in alpha", project="alpha")
    _til(cfg, "in beta", project="beta")
    from braindump.core import config

    config.set_active_project(cfg, "alpha")

    r = await _get("/tils")
    assert "in alpha" in r.text
    assert "in beta" in r.text
