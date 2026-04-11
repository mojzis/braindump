from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.responses import StreamingResponse
from watchfiles import Change

from braindump.web.app import _watch_filter, app, events


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/home/u/braindump/thoughts/2026/04/foo.md", True),
        ("/home/u/braindump/todos/index.jsonl", True),
        ("/home/u/braindump/journal/2026/04/2026-04-11.md", True),
        ("/home/u/braindump/.state.json", False),
        ("/home/u/braindump/.git/HEAD", False),
        ("/home/u/braindump/thoughts/foo.swp", False),
        ("/home/u/braindump/thoughts/.foo.md.swp", False),
        ("/home/u/braindump/thoughts/foo.md~", False),
        ("/home/u/braindump/thoughts/foo.tmp", False),
        ("/home/u/braindump/.DS_Store", False),
        ("/home/u/braindump/thoughts/notes.txt", False),
    ],
)
def test_watch_filter(path: str, expected: bool):
    assert _watch_filter(Change.modified, path) is expected


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_lifespan_initializes_subscribers_and_cleans_up():
    async with app.router.lifespan_context(app):
        assert isinstance(app.state.subscribers, set)
        assert len(app.state.subscribers) == 0
        assert app.state.watch_stop is not None
    assert app.state.watch_stop.is_set()


@pytest.mark.anyio
async def test_events_endpoint_returns_sse_stream_and_registers_subscriber():
    async with app.router.lifespan_context(app):
        request = SimpleNamespace(app=app)
        response = await events(request)
        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"
        assert response.headers["cache-control"] == "no-cache"

        body_iter = response.body_iterator
        first = await asyncio.wait_for(body_iter.__anext__(), timeout=2.0)
        assert "retry: 2000" in first
        assert len(app.state.subscribers) == 1

        await body_iter.aclose()
        assert len(app.state.subscribers) == 0
