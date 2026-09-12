from __future__ import annotations

from datetime import datetime

import httpx
import pytest

from braindump.core import entries
from braindump.web.app import _render_markdown, app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _set_home(monkeypatch, cfg) -> None:
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    monkeypatch.setenv("BRAINDUMP_DAY_CUTOFF", str(cfg.day_cutoff_hour))


def test_mermaid_fence_keeps_only_its_renderer_class() -> None:
    rendered = str(
        _render_markdown(
            "```mermaid\nflowchart LR\nA[<script>unsafe</script>] --> B\n```"
        )
    )

    assert '<code class="language-mermaid">' in rendered
    assert "<script>" not in rendered
    assert "&lt;script&gt;unsafe&lt;/script&gt;" in rendered


def test_ordinary_fence_remains_code_without_renderer_class() -> None:
    rendered = str(_render_markdown('```python\nprint("still code")\n```'))

    assert rendered.startswith("<pre><code")
    assert "language-mermaid" not in rendered
    assert 'print("still code")' in rendered


@pytest.mark.anyio
async def test_entry_loads_renderer_and_editing_retains_mermaid_source(
    monkeypatch, cfg
) -> None:
    _set_home(monkeypatch, cfg)
    source = "```mermaid\nflowchart LR\nA --> B\n```"
    created = entries.create_entry(
        cfg,
        "til",
        "diagram",
        source,
        now=datetime(2026, 4, 11, 14, 15),
    )
    transport = httpx.ASGITransport(app=app)

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=transport, base_url=httpx.URL(scheme="http", host="test")
        ) as client,
    ):
        view = await client.get(f"/entries/{created.entry.id}")
        edit = await client.get(f"/entries/{created.entry.id}/edit")

    assert view.status_code == 200, "entry view should load"
    assert "/static/mermaid-renderer.js" in view.text, "renderer script is missing"
    assert '<code class="language-mermaid">' in view.text, "fence marker was stripped"
    assert edit.status_code == 200, "entry edit should load"
    assert "```mermaid" in edit.text, "edit page lost the fence"
    assert "A --&gt; B" in edit.text, "edit page lost the diagram source"
