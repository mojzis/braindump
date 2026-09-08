from __future__ import annotations

import httpx
import pytest

from braindump.web.app import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _set_home(monkeypatch, cfg) -> None:
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    monkeypatch.setenv("BRAINDUMP_DAY_CUTOFF", str(cfg.day_cutoff_hour))


async def _get(url):
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        return await client.get(url)


@pytest.fixture
async def entries_page(monkeypatch, cfg, anyio_backend):
    _set_home(monkeypatch, cfg)
    return await _get("/entries")


@pytest.mark.anyio
async def test_base_layout_offers_entry_id_jump(entries_page):
    r = entries_page
    assert r.status_code == 200
    assert '<form class="entry-jump" id="entry-jump-form">' in r.text
    assert '<label for="entry-jump-id">jump to entry ID:</label>' in r.text
    assert '<input id="entry-jump-id" type="number"' in r.text


@pytest.mark.anyio
async def test_entry_jump_submission_and_shortcut(entries_page):
    r = entries_page
    assert 'placeholder="entry ID" required' in r.text
    assert '<button type="submit">go</button>' in r.text
    assert '<script src="/static/shortcuts.js"></script>' in r.text
    assert "<li><kbd>g i</kbd> focus entry ID</li>" in r.text


@pytest.mark.anyio
async def test_til_navigation_shortcut(entries_page):
    r = entries_page
    assert '<a href="/tils" data-shortcut="g l">TILs</a>' in r.text
    assert "<li><kbd>g l</kbd> TILs</li>" in r.text
