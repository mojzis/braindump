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


@pytest.mark.anyio
async def test_base_layout_offers_entry_id_jump(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)

    r = await _get("/entries")

    assert r.status_code == 200
    assert '<form class="entry-jump" id="entry-jump-form">' in r.text
    assert '<label for="entry-jump-id">jump to:</label>' in r.text
    assert '<input id="entry-jump-id" type="number"' in r.text
    assert '<button type="submit">go</button>' in r.text
    assert "<li><kbd>g i</kbd> focus entry ID</li>" in r.text
    assert '<a href="/tils" data-shortcut="g l">TILs</a>' in r.text
    assert "<li><kbd>g l</kbd> TILs</li>" in r.text
    assert 'l: "/tils"' in r.text
