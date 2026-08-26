"""The copy affordances the desktop window depends on (see web/desktop.py).

`bd app` has no browser chrome to copy from, so the pages themselves have to
offer it: a button per entry and per journal day, plus the script that drives
them.
"""

from __future__ import annotations

from datetime import date, datetime

import httpx
import pytest

from braindump.core import entries, journal
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
async def test_every_page_loads_the_clipboard_script(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)

    r = await _get("/entries")

    assert r.status_code == 200
    assert "/static/clipboard.js" in r.text


@pytest.mark.anyio
async def test_entry_page_offers_its_markdown_to_the_copy_button(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    created = entries.create_entry(
        cfg,
        "thoughts",
        "a thought",
        "- one\n- two",
        now=datetime(2026, 4, 11, 14, 15),
    )

    r = await _get(f"/entries/{created.entry.id}")

    assert r.status_code == 200
    assert 'data-copy-from="#entry-source"' in r.text
    # The button copies the markdown source, not the rendered HTML, so the
    # page has to carry both.
    assert '<script type="application/json" id="entry-source">' in r.text
    assert "- one\\n- two" in r.text


@pytest.mark.anyio
async def test_past_journal_days_each_get_a_copy_button(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    day = date(2026, 6, 1)
    journal.replace_body(cfg, day, "yesterday's notes")

    r = await _get(f"/journal/{day.isoformat()}")

    assert r.status_code == 200
    assert 'data-copy-url="/api/journal/2026-06-01/body"' in r.text
