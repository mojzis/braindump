from __future__ import annotations

import asyncio
from collections import Counter
from datetime import date, timedelta

import httpx
import pytest

from braindump.core import digest, journal
from braindump.web.app import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _set_home(monkeypatch, cfg) -> None:
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    monkeypatch.setenv("BRAINDUMP_DAY_CUTOFF", str(cfg.day_cutoff_hour))


def _client(app_instance=app):
    """Return an httpx AsyncClient bound to the ASGI app (caller enters lifespan)."""
    transport = httpx.ASGITransport(app=app_instance)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


# --- POST /api/journal/{day}/parse -------------------------------------------


@pytest.mark.anyio
async def test_parse_post_returns_409_when_job_already_running(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    day = date(2026, 6, 1)
    journal.replace_body(cfg, day, "some notes")

    gate = asyncio.Event()

    async def fake_run_parse(cfg_arg, day_arg, *, progress=None):
        if progress:
            progress("demo-project", "queued")
        await gate.wait()
        return digest.ParseResult(day=day_arg)

    monkeypatch.setattr(digest, "run_parse", fake_run_parse)

    async with app.router.lifespan_context(app), _client() as client:
        first = await client.post(
            f"/api/journal/{day.isoformat()}/parse", data={"body": "some notes"}
        )
        assert first.status_code == 200
        assert "parse-running" in first.text

        second = await client.post(
            f"/api/journal/{day.isoformat()}/parse", data={"body": "some notes"}
        )
        assert second.status_code == 409

        gate.set()
        await app.state.parse_task


@pytest.mark.anyio
async def test_parse_post_409_does_not_clobber_day_file(monkeypatch, cfg):
    """A rejected (409) double-submit must not overwrite the running job's snapshot."""
    _set_home(monkeypatch, cfg)
    day = date(2026, 6, 8)
    journal.replace_body(cfg, day, "some notes")

    gate = asyncio.Event()

    async def fake_run_parse(cfg_arg, day_arg, *, progress=None):
        await gate.wait()
        return digest.ParseResult(day=day_arg)

    monkeypatch.setattr(digest, "run_parse", fake_run_parse)

    async with app.router.lifespan_context(app), _client() as client:
        first = await client.post(
            f"/api/journal/{day.isoformat()}/parse", data={"body": "some notes"}
        )
        assert first.status_code == 200

        second = await client.post(
            f"/api/journal/{day.isoformat()}/parse",
            data={"body": "unsaved edits from a stale second tab"},
        )
        assert second.status_code == 409
        assert journal.read_body(cfg, day) == "some notes"

        gate.set()
        await app.state.parse_task


@pytest.mark.anyio
async def test_parse_post_flushes_editor_body_before_parsing(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    day = date(2026, 6, 4)
    journal.replace_body(cfg, day, "stale content")

    async def fake_run_parse(cfg_arg, day_arg, *, progress=None):
        return digest.ParseResult(day=day_arg)

    monkeypatch.setattr(digest, "run_parse", fake_run_parse)

    async with app.router.lifespan_context(app), _client() as client:
        resp = await client.post(
            f"/api/journal/{day.isoformat()}/parse",
            data={"body": "fresh unsaved content"},
        )
        assert resp.status_code == 200
        await app.state.parse_task

    assert journal.read_body(cfg, day) == "fresh unsaved content"


@pytest.mark.anyio
async def test_parse_post_returns_friendly_error_when_claude_missing(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    monkeypatch.setenv(
        "BRAINDUMP_CLAUDE_BIN", "definitely-not-a-real-claude-binary-xyz"
    )
    day = date(2026, 6, 3)
    journal.replace_body(cfg, day, "notes")

    async with app.router.lifespan_context(app), _client() as client:
        resp = await client.post(
            f"/api/journal/{day.isoformat()}/parse", data={"body": "notes"}
        )
        assert resp.status_code == 200
        assert "claude CLI not found" in resp.text
        assert "parse-error" in resp.text
        assert app.state.parse_job.status == "error"


# --- GET /journal/{day}/parse-status ------------------------------------------


@pytest.mark.anyio
async def test_parse_status_returns_286_and_trigger_header_when_done(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    day = date(2026, 6, 2)
    journal.replace_body(cfg, day, "notes")

    async def fake_run_parse(cfg_arg, day_arg, *, progress=None):
        if progress:
            progress("demo", "done")
        return digest.ParseResult(
            day=day_arg,
            sections=[
                digest.SectionResult(
                    project="demo", entry_ids=[1], counts=Counter({"todo": 1})
                )
            ],
        )

    monkeypatch.setattr(digest, "run_parse", fake_run_parse)

    async with app.router.lifespan_context(app), _client() as client:
        post_resp = await client.post(
            f"/api/journal/{day.isoformat()}/parse", data={"body": "notes"}
        )
        assert post_resp.status_code == 200
        await app.state.parse_task

        status_resp = await client.get(f"/journal/{day.isoformat()}/parse-status")
        assert status_resp.status_code == 286
        assert status_resp.headers["hx-trigger"] == "parse-done"
        assert "demo" in status_resp.text


@pytest.mark.anyio
async def test_parse_status_stays_200_while_running(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    day = date(2026, 6, 5)
    journal.replace_body(cfg, day, "notes")
    gate = asyncio.Event()

    async def fake_run_parse(cfg_arg, day_arg, *, progress=None):
        await gate.wait()
        return digest.ParseResult(day=day_arg)

    monkeypatch.setattr(digest, "run_parse", fake_run_parse)

    async with app.router.lifespan_context(app), _client() as client:
        await client.post(
            f"/api/journal/{day.isoformat()}/parse", data={"body": "notes"}
        )
        status_resp = await client.get(f"/journal/{day.isoformat()}/parse-status")
        assert status_resp.status_code == 200
        assert "hx-trigger" not in status_resp.headers

        gate.set()
        await app.state.parse_task


@pytest.mark.anyio
async def test_lifespan_shutdown_cancels_in_flight_parse_task(monkeypatch, cfg):
    """The parse task must not be orphaned when the server shuts down mid-parse."""
    _set_home(monkeypatch, cfg)
    day = date(2026, 6, 7)
    journal.replace_body(cfg, day, "notes")

    started = asyncio.Event()

    async def fake_run_parse(cfg_arg, day_arg, *, progress=None):
        started.set()
        await asyncio.Event().wait()  # never completes on its own

    monkeypatch.setattr(digest, "run_parse", fake_run_parse)

    parse_task = None
    async with app.router.lifespan_context(app), _client() as client:
        resp = await client.post(
            f"/api/journal/{day.isoformat()}/parse", data={"body": "notes"}
        )
        assert resp.status_code == 200
        await asyncio.wait_for(started.wait(), timeout=2.0)
        parse_task = app.state.parse_task
        assert not parse_task.done()

    # Lifespan teardown (outside the `async with` above) must have cancelled
    # the still-running parse task rather than leaving it orphaned.
    assert parse_task is not None
    assert parse_task.cancelled()


# --- GET /journal/days (lazy-load pagination) --------------------------------


@pytest.mark.anyio
async def test_journal_days_pagination(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    anchor = date(2026, 5, 20)
    days = [anchor - timedelta(days=i) for i in range(1, 6)]  # 5 days with content
    for d in days:
        journal.append_text(cfg, d, f"content for {d.isoformat()}")

    async with app.router.lifespan_context(app), _client() as client:
        first_page = await client.get(
            "/journal/days", params={"before": anchor.isoformat(), "limit": 3}
        )
        assert first_page.status_code == 200
        for d in days[:3]:
            assert f"content for {d.isoformat()}" in first_page.text
        for d in days[3:]:
            assert f"content for {d.isoformat()}" not in first_page.text
        assert "loading earlier days" in first_page.text

        second_page = await client.get(
            "/journal/days", params={"before": days[2].isoformat(), "limit": 3}
        )
        assert second_page.status_code == 200
        assert "beginning of the journal" in second_page.text
        assert "loading earlier days" not in second_page.text


@pytest.mark.anyio
async def test_journal_days_with_no_earlier_content(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    today = date(2026, 5, 30)

    async with app.router.lifespan_context(app), _client() as client:
        resp = await client.get(
            "/journal/days", params={"before": today.isoformat(), "limit": 5}
        )
        assert resp.status_code == 200
        assert "loading earlier days" not in resp.text


# --- GET /journal (running doc) & permalink -----------------------------------


@pytest.mark.anyio
async def test_journal_root_renders_running_doc(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    today = journal.current_day(cfg)
    yesterday = today - timedelta(days=1)
    journal.append_text(cfg, yesterday, "yesterday's note")

    async with app.router.lifespan_context(app), _client() as client:
        resp = await client.get("/journal")
        assert resp.status_code == 200
        assert "journal-editor" in resp.text
        assert "yesterday" in resp.text.lower() or "yesterday's note" in resp.text


@pytest.mark.anyio
async def test_journal_permalink_redirects_today_to_running_doc(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    today = journal.current_day(cfg)

    async with app.router.lifespan_context(app), _client() as client:
        resp = await client.get(f"/journal/{today.isoformat()}", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/journal"


@pytest.mark.anyio
async def test_journal_permalink_renders_past_day_readonly(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    day = date(2026, 4, 2)
    journal.replace_body(cfg, day, "an old entry [→todo#7]")

    async with app.router.lifespan_context(app), _client() as client:
        resp = await client.get(f"/journal/{day.isoformat()}")
        assert resp.status_code == 200
        assert 'href="/entries/7"' in resp.text
        assert "ref-chip" in resp.text


# --- GET /api/journal/{day}/body ----------------------------------------------


@pytest.mark.anyio
async def test_api_journal_body_returns_plain_text(monkeypatch, cfg):
    _set_home(monkeypatch, cfg)
    day = date(2026, 6, 6)
    journal.replace_body(cfg, day, "plain text body")

    async with app.router.lifespan_context(app), _client() as client:
        resp = await client.get(f"/api/journal/{day.isoformat()}/body")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")
        assert resp.text == "plain text body"
