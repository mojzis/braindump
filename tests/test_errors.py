"""Braindump reports expected failures as messages, not tracebacks.

The motivating case: running `bd done` inside a sandbox (codex, a container)
that hands the process a `~/braindump` it isn't allowed to write to. That's a
normal thing to run into, so every surface should say so plainly.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from braindump.cli.main import app as cli_app
from braindump.core import entries, journal, projects, query, store
from braindump.core.errors import (
    EntryNotFoundError,
    ReadOnlyStoreError,
    StorageError,
    storage_error,
)
from braindump.web.app import app as web_app

runner = CliRunner()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _deny_writes(monkeypatch) -> None:
    """Fail every write the way a sandbox does, leaving reads working.

    Three chokepoints cover the store: `tempfile.mkstemp` backs every markdown
    and index write, `Path.touch` backs index creation and the lock files, and
    `Path.write_text` backs the active-project state file.
    """

    def denied(*_args, **_kwargs):
        raise PermissionError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(store.tempfile, "mkstemp", denied)
    monkeypatch.setattr(Path, "touch", denied)
    monkeypatch.setattr(Path, "write_text", denied)


def _todo(cfg, title: str = "Fix auth bug"):
    return entries.create_entry(
        cfg, "todo", title, "body", type_fields={"status": "pending"}
    )


# --- errno translation -----------------------------------------------------


@pytest.mark.parametrize("code", [errno.EACCES, errno.EPERM, errno.EROFS])
def test_denied_errnos_become_read_only_errors(code):
    exc = storage_error(OSError(code, "Permission denied"), Path("/x/y.md"), "write")
    assert isinstance(exc, ReadOnlyStoreError)
    assert "/x/y.md" in str(exc)
    assert exc.hint is not None
    assert "BRAINDUMP_DIR" in exc.hint


def test_full_disk_gets_its_own_hint():
    exc = storage_error(OSError(errno.ENOSPC, "No space left on device"), Path("/x"))
    assert isinstance(exc, StorageError)
    assert not isinstance(exc, ReadOnlyStoreError)
    assert exc.hint is not None
    assert "full" in exc.hint


def test_unclassified_errno_carries_no_hint():
    exc = storage_error(OSError(errno.EIO, "I/O error"), Path("/x"))
    assert isinstance(exc, StorageError)
    assert exc.hint is None
    assert "i/o error" in str(exc)


def test_error_falls_back_to_the_errnos_own_filename():
    exc = storage_error(FileNotFoundError(errno.ENOENT, "No such file", "/nope.md"))
    assert "/nope.md" in str(exc)


# --- core ------------------------------------------------------------------


def test_write_to_unwritable_store_raises_storage_error(cfg, monkeypatch):
    result = _todo(cfg)
    _deny_writes(monkeypatch)

    with pytest.raises(ReadOnlyStoreError) as excinfo:
        entries.mark_done(cfg, result.entry.id)
    assert str(result.entry.file_path) in str(excinfo.value)


def test_journal_append_to_unwritable_store_raises_storage_error(cfg, monkeypatch):
    _deny_writes(monkeypatch)
    with pytest.raises(ReadOnlyStoreError):
        journal.append_text(cfg, journal.current_day(cfg), "a thought")


def test_project_focus_on_unwritable_store_raises_storage_error(cfg, monkeypatch):
    _deny_writes(monkeypatch)
    with pytest.raises(ReadOnlyStoreError):
        projects.set_active_project(cfg, "braindump")


def test_missing_id_raises_entry_not_found(cfg):
    with pytest.raises(EntryNotFoundError) as excinfo:
        entries.update_entry(cfg, 9999, {"title": "x"})
    assert "#9999" in str(excinfo.value)
    assert excinfo.value.entry_id == 9999


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes through the mode bits")
def test_a_genuinely_read_only_directory_still_reads(cfg):
    """The real thing, not a stubbed one: chmod the store and confirm the split.

    Reads keep working — a sandbox is no reason to stop being able to look
    things up — and only the write fails, with a message.
    """
    result = _todo(cfg)
    paths = [cfg.home, *(p for p in cfg.home.rglob("*") if p.is_dir())]
    modes = {p: p.stat().st_mode for p in paths}
    for p in paths:
        p.chmod(0o555)
    try:
        assert [h.entry.id for h in query.search(cfg, query.SearchFilters())] == [
            result.entry.id
        ]
        with pytest.raises(ReadOnlyStoreError):
            entries.mark_done(cfg, result.entry.id)
    finally:
        for p, mode in modes.items():
            p.chmod(mode)


def test_write_probe_reports_an_unwritable_store(cfg, monkeypatch):
    assert store.writable_error(cfg) is None
    _deny_writes(monkeypatch)
    problem = store.writable_error(cfg)
    assert isinstance(problem, ReadOnlyStoreError)


# --- CLI -------------------------------------------------------------------


def test_cli_done_on_unwritable_store_explains_itself(cfg, monkeypatch):
    result = _todo(cfg)
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    _deny_writes(monkeypatch)

    res = runner.invoke(cli_app, ["done", str(result.entry.id)])
    assert res.exit_code == 1
    assert "Traceback" not in res.output
    assert "PermissionError" not in res.output
    assert "error: cannot write" in res.output
    assert "hint:" in res.output


def test_cli_done_unknown_id_explains_itself(cfg, monkeypatch):
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    res = runner.invoke(cli_app, ["done", "9999"])
    assert res.exit_code == 1
    assert "Traceback" not in res.output
    assert "error: entry #9999 not found" in res.output


def test_cli_reports_a_missing_input_file(cfg, monkeypatch):
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    res = runner.invoke(
        cli_app, ["create", "todo", "x", "--body-file", str(cfg.home / "nope.md")]
    )
    assert res.exit_code == 1
    assert "Traceback" not in res.output
    assert "nope.md" in res.output


def test_cli_doctor_flags_an_unwritable_store(cfg, monkeypatch):
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    _deny_writes(monkeypatch)

    res = runner.invoke(cli_app, ["doctor"])
    assert res.exit_code == 1
    assert "NOT WRITABLE" in res.output


# --- web -------------------------------------------------------------------


async def _post(url: str, data: dict[str, str]):
    transport = httpx.ASGITransport(app=web_app)
    async with (
        web_app.router.lifespan_context(web_app),
        httpx.AsyncClient(transport=transport, base_url="http://t") as client,
    ):
        return await client.post(url, data=data)


@pytest.mark.anyio
async def test_web_unwritable_store_answers_403(cfg, monkeypatch):
    result = _todo(cfg)
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    _deny_writes(monkeypatch)

    r = await _post(f"/api/entries/{result.entry.id}/done", {})
    assert r.status_code == 403
    assert "cannot write" in r.text


@pytest.mark.anyio
async def test_web_unknown_entry_answers_404(cfg, monkeypatch):
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    r = await _post("/api/entries/9999/done", {})
    assert r.status_code == 404
