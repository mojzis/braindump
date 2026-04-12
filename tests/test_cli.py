"""Tests for the bd show command."""
from __future__ import annotations

import json
from datetime import datetime

from typer.testing import CliRunner

from braindump.cli.main import app
from braindump.core import entries
from braindump.core.config import Config
from braindump.core.store import ensure_type_dirs

runner = CliRunner()


def _make_cfg(tmp_path):
    home = tmp_path / "braindump"
    home.mkdir()
    cfg = Config(home=home, day_cutoff_hour=4)
    ensure_type_dirs(cfg)
    return cfg


def _create_todo(cfg: Config, title: str = "Fix auth bug", **kwargs):
    return entries.create_entry(
        cfg,
        "todo",
        title,
        "Body of the todo.",
        tags=kwargs.get("tags", ["auth", "bug"]),
        project=kwargs.get("project", "braindump"),
        type_fields=kwargs.get("type_fields", {"status": "pending"}),
        now=kwargs.get("now", datetime(2026, 4, 11, 14, 15, 2)),
    )


def _create_til(cfg: Config, title: str = "Python walrus operator"):
    return entries.create_entry(
        cfg,
        "til",
        title,
        "You can use := in Python 3.8+.",
        tags=["python"],
        type_fields={"category": "python", "source": "docs"},
        now=datetime(2026, 4, 11, 10, 0, 0),
    )


def test_show_single_entry(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    result = _create_todo(cfg)
    eid = result.entry.id

    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    res = runner.invoke(app, ["show", str(eid)])
    assert res.exit_code == 0
    assert f"#{eid} todo" in res.output
    assert "Fix auth bug" in res.output
    assert "created: 2026-04-11" in res.output
    assert "project: braindump" in res.output
    assert "tags: auth, bug" in res.output
    assert "status: pending" in res.output
    assert "Body of the todo." in res.output


def test_show_multiple_entries(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    r1 = _create_todo(cfg)
    r2 = _create_til(cfg)

    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    res = runner.invoke(app, ["show", str(r1.entry.id), str(r2.entry.id)])
    assert res.exit_code == 0
    assert "Fix auth bug" in res.output
    assert "Python walrus operator" in res.output
    assert "---" in res.output


def test_show_unknown_id(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    res = runner.invoke(app, ["show", "9999"])
    assert res.exit_code == 1
    assert "not found" in res.output


def test_show_mixed_known_unknown(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    r1 = _create_todo(cfg)

    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    res = runner.invoke(app, ["show", str(r1.entry.id), "9999"])
    # At least one succeeded, so exit code should be 0
    assert res.exit_code == 0
    assert "Fix auth bug" in res.output
    assert "not found" in res.output


def test_show_all_unknown(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    res = runner.invoke(app, ["show", "9998", "9999"])
    assert res.exit_code == 1


def test_show_json(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    r1 = _create_todo(cfg)

    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    res = runner.invoke(app, ["show", "--json", str(r1.entry.id)])
    assert res.exit_code == 0
    data = json.loads(res.output.strip())
    assert data["id"] == r1.entry.id
    assert data["type"] == "todo"
    assert data["title"] == "Fix auth bug"
    assert "body" in data
    assert "Body of the todo." in data["body"]


def test_show_json_unknown(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    res = runner.invoke(app, ["show", "--json", "9999"])
    assert res.exit_code == 1


def test_show_type_specific_fields(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    r1 = _create_til(cfg)

    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    res = runner.invoke(app, ["show", str(r1.entry.id)])
    assert res.exit_code == 0
    assert "category: python" in res.output
    assert "source: docs" in res.output


def test_show_no_tables(tmp_path, monkeypatch):
    """Ensure output never contains markdown table syntax."""
    cfg = _make_cfg(tmp_path)
    r1 = _create_todo(cfg)

    monkeypatch.setenv("BRAINDUMP_DIR", str(cfg.home))
    res = runner.invoke(app, ["show", str(r1.entry.id)])
    assert res.exit_code == 0
    # No table borders
    assert "|" not in res.output
